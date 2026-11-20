"""
Mixins for django_googler OAuth views.

This module provides reusable mixins that encapsulate common OAuth flow logic
for session-based Django views and shared token response helpers.
"""

import logging
from typing import Any, Optional

from django.urls import reverse
from google.oauth2.credentials import Credentials

from django_googler.defaults import get_django_google_setting
from django_googler.models import get_user_identifier
from django_googler.platform_client import get_google_auth_flow, get_google_auth_url
from django_googler.services import GoogleOAuthService, OAuthFlowService, UserService

logger = logging.getLogger(__name__)


class OAuthFlowInitMixin:
    """
    Mixin for initializing a session-based Google OAuth flow.

    Provides common logic for:
    - Building redirect URIs
    - Parsing custom scopes from request
    - Creating OAuth flows (with optional PKCE)
    - Generating authorization URLs and state
    - Storing state, scopes, and PKCE verifier in session
    """

    def get_redirect_uri_name(self) -> str:
        """
        Get the URL name for the OAuth callback.

        Must be overridden by subclasses to specify which callback URL to use.
        """
        raise NotImplementedError("Subclasses must implement get_redirect_uri_name()")

    def build_redirect_uri(self, request) -> str:
        """Build the full absolute redirect URI for OAuth callback."""
        callback_url_name = self.get_redirect_uri_name()
        return request.build_absolute_uri(reverse(callback_url_name))

    def parse_scopes(self, request) -> Optional[list[str]]:
        """Parse comma-separated custom scopes from request query parameters."""
        query_params = getattr(request, "query_params", request.GET)
        raw_scopes = query_params.get("scopes")
        if not raw_scopes:
            return None
        cleaned = [s.strip() for s in raw_scopes.split(",") if s.strip()]
        return cleaned or None

    def init_oauth_flow(
        self, request, redirect_uri: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Initialize OAuth flow and generate authorization URL.

        Args:
            request: HTTP request object (Django or DRF)
            redirect_uri: Optional explicit redirect URI override

        Returns:
            Tuple of ``(authorization_url, state)``
        """
        redirect_uri = redirect_uri or self.build_redirect_uri(request)
        scopes = self.parse_scopes(request)
        use_pkce = bool(get_django_google_setting("GOOGLE_OAUTH_USE_PKCE"))

        flow = get_google_auth_flow(
            redirect_uri=[redirect_uri],
            scopes=scopes,
            autogenerate_code_verifier=use_pkce,
        )

        authorization_url, state = get_google_auth_url(flow)

        OAuthFlowService.store_state(request, state)
        OAuthFlowService.store_scopes(request, scopes)
        OAuthFlowService.store_code_verifier(
            request, getattr(flow, "code_verifier", None) if use_pkce else None
        )

        return authorization_url, state


class OAuthCallbackProcessingMixin:
    """
    Mixin for processing a session-based Google OAuth callback.

    Provides common logic for:
    - Verifying state (CSRF protection)
    - Exchanging authorization code for tokens (including stored scopes & PKCE)
    - Verifying ID token
    - Extracting user information
    - Creating/retrieving user
    - Storing tokens (session and database)
    """

    def get_redirect_uri_name(self) -> str:
        """Get the URL name for the OAuth callback."""
        raise NotImplementedError("Subclasses must implement get_redirect_uri_name()")

    def build_redirect_uri(self, request, redirect_uri: Optional[str] = None) -> str:
        """Build the full absolute redirect URI for OAuth callback."""
        if redirect_uri:
            return redirect_uri

        callback_url_name = self.get_redirect_uri_name()
        return request.build_absolute_uri(reverse(callback_url_name))

    def verify_oauth_state(self, request, state: str) -> bool:
        """Verify OAuth state for CSRF protection."""
        return OAuthFlowService.verify_state(request, state)

    def exchange_code_for_credentials(
        self,
        code: str,
        redirect_uri: str,
        state: str,
        scopes: Optional[list[str]] = None,
        code_verifier: Optional[str] = None,
    ) -> Credentials:
        """
        Exchange authorization code for Google credentials.

        Args:
            code: Authorization code from Google
            redirect_uri: Redirect URI used in OAuth flow
            state: State parameter for flow recreation
            scopes: Optional OAuth scopes requested during login
            code_verifier: Optional PKCE code verifier stored during login

        Returns:
            Google OAuth ``Credentials`` instance
        """
        flow = get_google_auth_flow(
            redirect_uri=[redirect_uri],
            state=state,
            scopes=scopes,
            code_verifier=code_verifier,
        )
        flow.fetch_token(code=code)
        return flow.credentials

    def extract_user_data(self, credentials: Credentials) -> dict[str, Any]:
        """Verify ID token and extract standardized user information."""
        id_info = GoogleOAuthService.verify_id_token(credentials)
        return GoogleOAuthService.extract_user_info(id_info)

    def create_or_get_user(self, user_info: dict[str, Any]):
        """Create or retrieve user based on Google account information."""
        email = user_info.get("email")
        if not email:
            raise ValueError("No email provided by Google")

        return UserService.get_or_create_user(
            email=email,
            name=user_info.get("name"),
            google_id=user_info.get("google_id"),
            picture=user_info.get("picture"),
            given_name=user_info.get("given_name"),
            family_name=user_info.get("family_name"),
            email_verified=user_info.get("email_verified"),
        )

    def store_user_tokens(
        self, request, user, credentials: Credentials, user_info: dict[str, Any]
    ) -> None:
        """Store OAuth tokens in session and optionally in database."""
        GoogleOAuthService.store_tokens_in_session(request, credentials)

        if get_django_google_setting("GOOGLE_OAUTH_SAVE_TOKENS_TO_DB"):
            GoogleOAuthService.save_user_token(
                user=user,
                credentials=credentials,
                google_id=user_info.get("google_id"),
                scopes=(
                    list(credentials.scopes)
                    if getattr(credentials, "scopes", None)
                    else None
                ),
            )

    def cleanup_oauth_state(self, request) -> None:
        """Clean up OAuth state, scopes, and PKCE verifier from session."""
        OAuthFlowService.clear_state(request)

    def process_oauth_callback(
        self, request, code: str, state: str, redirect_uri: Optional[str] = None
    ) -> tuple[Any, dict[str, Any], Credentials, bool]:
        """
        Process the complete session-based OAuth callback flow.

        Args:
            request: HTTP request object
            code: Authorization code from Google
            state: State parameter for CSRF protection
            redirect_uri: Optional pre-built redirect URI

        Returns:
            Tuple of ``(user, user_info, credentials, user_created)``

        Raises:
            ValueError: If state verification fails, email is missing, or
                email is unverified when required
        """
        if not self.verify_oauth_state(request, state):
            raise ValueError("Invalid state parameter - CSRF verification failed")

        final_redirect_uri = self.build_redirect_uri(request, redirect_uri)
        stored_scopes = OAuthFlowService.get_scopes(request)
        code_verifier = OAuthFlowService.get_code_verifier(request)

        # Build kwargs so subclasses overriding with 3 positional args still work
        exchange_kwargs: dict[str, Any] = {}
        if stored_scopes is not None:
            exchange_kwargs["scopes"] = stored_scopes
        if code_verifier is not None:
            exchange_kwargs["code_verifier"] = code_verifier

        credentials = self.exchange_code_for_credentials(
            code, final_redirect_uri, state, **exchange_kwargs
        )

        user_info = self.extract_user_data(credentials)
        user, user_created = self.create_or_get_user(user_info)
        self.store_user_tokens(request, user, credentials, user_info)
        self.cleanup_oauth_state(request)

        logger.info("User %s authenticated via Google OAuth", get_user_identifier(user))

        from django_googler.signals import google_oauth_success

        granted_scopes = (
            list(credentials.scopes)
            if getattr(credentials, "scopes", None)
            else stored_scopes or []
        )
        google_oauth_success.send(
            sender=self.__class__,
            user=user,
            scopes=granted_scopes,
            credentials=credentials,
            user_created=user_created,
            user_info=user_info,
        )

        return user, user_info, credentials, user_created


class TokenResponseMixin:
    """
    Mixin for building token response data.

    Respects ``GOOGLE_OAUTH_RETURN_TOKENS`` dynamically.
    """

    def build_google_tokens_response(self, credentials: Credentials) -> dict[str, Any]:
        """Build Google tokens response dictionary."""
        tokens_data: dict[str, Any] = {
            "access_token": credentials.token,
            "expires_in": (
                credentials.expiry.isoformat() if credentials.expiry else None
            ),
        }

        if credentials.refresh_token:
            tokens_data["refresh_token"] = credentials.refresh_token

        return tokens_data

    def should_return_google_tokens(self) -> bool:
        """Check if Google tokens should be included in the API response."""
        return bool(get_django_google_setting("GOOGLE_OAUTH_RETURN_TOKENS"))
