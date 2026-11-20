"""
Security utilities for django_googler.

Provides cryptographic state signing for stateless/cross-origin OAuth flows,
redirect URI validation, and safe post-login redirect URL checking.
"""

import logging
from typing import Any
from urllib.parse import urlparse

from django.core import signing
from django.utils.http import url_has_allowed_host_and_scheme

from django_googler.defaults import get_django_google_setting

logger = logging.getLogger(__name__)


def is_safe_next_url(request, next_url: str | None) -> bool:
    """
    Verify that a ``next`` redirect URL is safe (prevents open redirects).

    Args:
        request: Django HTTP request object
        next_url: Candidate redirect URL

    Returns:
        True if the URL is a relative path or matches the current request host
        with an allowed scheme, False otherwise.
    """
    if not next_url:
        return False
    return url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )


def validate_redirect_uri(redirect_uri: str | None) -> str | None:
    """
    Validate an OAuth ``redirect_uri`` value.

    Checks that:
    1. The URI uses an ``http`` or ``https`` scheme and includes a network host.
    2. If ``GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS`` is configured, the URI is in
       that allowlist.

    Args:
        redirect_uri: Candidate redirect URI string, or None

    Returns:
        The validated redirect URI string, or None if not provided.

    Raises:
        ValueError: If the redirect URI is malformed or not allowed.
    """
    if not redirect_uri:
        return None

    parsed = urlparse(redirect_uri)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid redirect_uri: must be a valid http(s) URL")

    allowed_uris = get_django_google_setting("GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS")
    if allowed_uris is not None and redirect_uri not in allowed_uris:
        raise ValueError("redirect_uri is not in GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS")

    return redirect_uri


class SignedStateOAuthMixin:
    """
    Mixin for handling OAuth state with cryptographic signing instead of sessions.

    This allows state verification to work across different domains without
    relying on session cookies.

    The state data is serialized, compressed, HMAC-signed with a dedicated salt,
    and base64-encoded, making it opaque and tamper-resistant.
    """

    # Default state token lifetime (seconds); overridden by GOOGLE_OAUTH_STATE_MAX_AGE
    STATE_MAX_AGE: int | None = None
    STATE_SALT = "django_googler.oauth_state"

    @classmethod
    def get_state_max_age(cls) -> int:
        """Return state token max age in seconds."""
        if cls.STATE_MAX_AGE is not None:
            return cls.STATE_MAX_AGE
        return int(get_django_google_setting("GOOGLE_OAUTH_STATE_MAX_AGE"))

    @classmethod
    def sign_state(
        cls,
        state: str,
        scopes: list[str] | None = None,
        extra_metadata: dict[str, Any] | None = None,
        redirect_uri: str | None = None,
    ) -> str:
        """
        Sign and encode the OAuth state using Django's signing framework.

        Args:
            state: The state string to sign
            scopes: Optional list of OAuth scopes to encode in the state
            extra_metadata: Optional custom metadata dictionary
            redirect_uri: Optional redirect URI bound to this OAuth flow

        Returns:
            Opaque signed state string containing state and optional metadata
        """
        state_data: dict[str, Any] = {
            "state": state,
            "extra_metadata": extra_metadata,
        }
        if scopes is not None:
            state_data["scopes"] = scopes
        if redirect_uri is not None:
            state_data["redirect_uri"] = redirect_uri

        return signing.dumps(
            state_data,
            salt=cls.STATE_SALT,
            compress=True,
        )

    @classmethod
    def verify_signed_state(
        cls, signed_state: str
    ) -> tuple[bool, str | None, dict[str, Any] | None]:
        """
        Verify and extract the original state and metadata from a signed state.

        Args:
            signed_state: The opaque signed state string to verify

        Returns:
            Tuple of ``(is_valid, original_state, metadata)``:
            - ``is_valid``: True if signature is valid and not expired
            - ``original_state``: Original state string if valid, None otherwise
            - ``metadata``: Dict containing additional data (e.g., scopes,
              redirect_uri, extra_metadata) if valid, None otherwise
        """
        if not signed_state or not isinstance(signed_state, str):
            return False, None, None

        try:
            state_data = signing.loads(
                signed_state,
                salt=cls.STATE_SALT,
                max_age=cls.get_state_max_age(),
            )

            # Handle dict format with state and metadata
            if isinstance(state_data, dict) and "state" in state_data:
                original_state = state_data["state"]
                metadata = {k: v for k, v in state_data.items() if k != "state"}
                return True, original_state, metadata

            # Handle legacy plain string format for backwards compatibility
            if isinstance(state_data, str):
                return True, state_data, {}

            logger.warning("OAuth state has unexpected format")
            return False, None, None

        except signing.SignatureExpired:
            logger.warning("OAuth state signature expired")
            return False, None, None
        except signing.BadSignature:
            logger.warning("OAuth state signature invalid")
            return False, None, None
        except Exception as e:
            logger.error("Error verifying OAuth state: %s", e)
            return False, None, None
