"""
Service layer for django_googler OAuth operations.

This module contains the business logic for handling Google OAuth authentication,
token processing, and user management.
"""

import logging
import re
import secrets
from datetime import timezone as dt_timezone
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.utils import timezone

from django_googler.defaults import get_django_google_setting
from django_googler.models import get_user_identifier

logger = logging.getLogger(__name__)

_INVALID_USERNAME_CHARS_RE = re.compile(r"[^\w.@+-]+")


def _user_model_has_field(field_name: str) -> bool:
    """Return True if the active Django User model defines ``field_name``."""
    User = get_user_model()
    try:
        return User._meta.get_field(field_name) is not None
    except FieldDoesNotExist:
        return False


def _get_email_field_name(User) -> str:
    """Return the email field name on ``User`` (respecting custom User models)."""
    get_email_field = getattr(User, "get_email_field_name", None)
    if callable(get_email_field):
        return get_email_field()
    return "email"


def _make_aware(dt):
    """
    Ensure a datetime from Google OAuth credentials is timezone-aware UTC.

    Google OAuth libraries return naive UTC datetimes; making them aware in UTC
    avoids incorrect timezone conversion when ``TIME_ZONE != 'UTC'``.

    Args:
        dt: datetime object or None

    Returns:
        Timezone-aware datetime or None
    """
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, dt_timezone.utc)


class GoogleOAuthService:
    """Service class for handling Google OAuth operations."""

    @staticmethod
    def process_credentials(credentials) -> dict[str, Any]:
        """
        Process Google OAuth credentials and extract user information.

        Args:
            credentials: Google OAuth credentials object

        Returns:
            Dictionary containing tokens and user info

        Raises:
            Exception: If token verification fails
        """
        id_info = GoogleOAuthService.verify_id_token(credentials)

        response_data: dict[str, Any] = {
            "access_token": credentials.token,
            "token_type": "Bearer",
            "expires_in": (
                credentials.expiry.isoformat() if credentials.expiry else None
            ),
            "id_token": credentials.id_token,
            "user_info": {
                "email": id_info.get("email"),
                "name": id_info.get("name"),
                "picture": id_info.get("picture"),
                "email_verified": bool(id_info.get("email_verified", False)),
                "sub": id_info.get("sub"),
                "given_name": id_info.get("given_name"),
                "family_name": id_info.get("family_name"),
            },
        }

        if credentials.refresh_token:
            response_data["refresh_token"] = credentials.refresh_token

        return response_data

    @staticmethod
    def extract_user_info(id_info: dict[str, Any]) -> dict[str, Any]:
        """
        Extract user information from ID token info.

        Args:
            id_info: Decoded ID token information

        Returns:
            Dictionary with standardized user fields
        """
        return {
            "email": id_info.get("email", ""),
            "name": id_info.get("name", ""),
            "given_name": id_info.get("given_name", ""),
            "family_name": id_info.get("family_name", ""),
            "picture": id_info.get("picture", ""),
            "google_id": id_info.get("sub", ""),
            "email_verified": bool(id_info.get("email_verified", False)),
        }

    @staticmethod
    def verify_id_token(credentials) -> dict[str, Any]:
        """
        Verify and decode Google ID token.

        Args:
            credentials: Google OAuth credentials object

        Returns:
            Decoded ID token information
        """
        import google.auth.transport.requests
        from google.oauth2 import id_token

        request_adapter = google.auth.transport.requests.Request()
        return id_token.verify_oauth2_token(
            credentials.id_token, request_adapter, credentials.client_id
        )

    @staticmethod
    def store_tokens_in_session(request, credentials) -> None:
        """
        Store OAuth tokens in session if configured to do so.

        Args:
            request: Django request object
            credentials: Google OAuth credentials object
        """
        if get_django_google_setting("GOOGLE_OAUTH_STORE_TOKENS"):
            request.session["google_access_token"] = credentials.token
            if credentials.refresh_token:
                request.session["google_refresh_token"] = credentials.refresh_token
            if credentials.expiry:
                request.session["google_token_expiry"] = credentials.expiry.isoformat()

    @staticmethod
    def save_user_token(
        user,
        credentials,
        google_id: Optional[str] = None,
        scopes: Optional[list[str]] = None,
    ):
        """
        Save or update Google OAuth tokens for a user in the database.

        Preserves any existing refresh token if Google does not return a new one.

        Args:
            user: Django user instance
            credentials: Google OAuth credentials object
            google_id: Google's unique user identifier (sub claim)
            scopes: List of OAuth scopes granted

        Returns:
            GoogleOAuthToken instance
        """
        from django_googler.models import GoogleOAuthToken

        with transaction.atomic():
            token, created = GoogleOAuthToken.objects.get_or_create(user=user)

            token.access_token = credentials.token
            token.token_expiry = _make_aware(credentials.expiry)

            if credentials.refresh_token:
                token.refresh_token = credentials.refresh_token

            if credentials.id_token:
                token.id_token = credentials.id_token

            if google_id:
                token.google_id = google_id

            if scopes:
                token.set_scopes_list(scopes)
            elif hasattr(credentials, "scopes") and credentials.scopes:
                token.set_scopes_list(list(credentials.scopes))

            token.save()

        action = "Created" if created else "Updated"
        logger.info("%s OAuth token for user: %s", action, get_user_identifier(user))

        return token

    @staticmethod
    def get_user_token(user):
        """
        Get the OAuth token for a user.

        Args:
            user: Django user instance

        Returns:
            GoogleOAuthToken instance or None
        """
        from django_googler.models import GoogleOAuthToken

        try:
            return GoogleOAuthToken.objects.get(user=user)
        except GoogleOAuthToken.DoesNotExist:
            return None

    @staticmethod
    def refresh_user_token(token_or_user):
        """
        Refresh an expired access token using the refresh token.

        Persists any rotated refresh token or updated ID token returned by
        Google and emits the ``google_oauth_token_refreshed`` signal.

        Args:
            token_or_user: Either a GoogleOAuthToken instance or User instance

        Returns:
            Updated GoogleOAuthToken instance

        Raises:
            ValueError: If no token or refresh token is available
            Exception: If token refresh fails
        """
        import google.auth.transport.requests

        from django_googler.models import GoogleOAuthToken
        from django_googler.signals import google_oauth_token_refreshed

        if isinstance(token_or_user, GoogleOAuthToken):
            token_pk = token_or_user.pk
        else:
            existing = GoogleOAuthService.get_user_token(token_or_user)
            if not existing:
                raise ValueError("No token found for user")
            token_pk = existing.pk

        with transaction.atomic():
            token = (
                GoogleOAuthToken.objects.select_for_update()
                .select_related("user")
                .get(pk=token_pk)
            )

            if not token.refresh_token:
                raise ValueError(
                    "No refresh token available. User must re-authenticate."
                )

            try:
                credentials = token.to_credentials()
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)

                token.access_token = credentials.token
                token.token_expiry = _make_aware(credentials.expiry)
                if credentials.refresh_token:
                    token.refresh_token = credentials.refresh_token
                if credentials.id_token:
                    token.id_token = credentials.id_token
                token.save()

            except Exception as e:
                logger.error(
                    "Failed to refresh token for %s: %s",
                    get_user_identifier(token.user),
                    e,
                    exc_info=True,
                )
                raise

        logger.info(
            "Refreshed OAuth token for user: %s", get_user_identifier(token.user)
        )

        google_oauth_token_refreshed.send(
            sender=GoogleOAuthService,
            user=token.user,
            token=token,
        )

        return token

    @staticmethod
    def revoke_user_token(user) -> bool:
        """
        Revoke a user's Google OAuth token and delete it from database.

        Sends the token in the POST body (never URL query parameters) with an
        explicit timeout. Prefers revoking the refresh token (which invalidates
        the entire grant) and falls back to the access token.

        Args:
            user: Django user instance

        Returns:
            True if a token existed and was deleted, False if no token existed
        """
        import requests

        token = GoogleOAuthService.get_user_token(user)
        if not token:
            return False

        user_id = get_user_identifier(user)
        token_to_revoke = token.refresh_token or token.access_token

        if token_to_revoke:
            try:
                revoke_url = get_django_google_setting("GOOGLE_OAUTH_REVOKE_URI")
                timeout = get_django_google_setting("GOOGLE_OAUTH_REQUEST_TIMEOUT")
                response = requests.post(
                    revoke_url,
                    data={"token": token_to_revoke},
                    headers={"content-type": "application/x-www-form-urlencoded"},
                    timeout=timeout,
                )

                if response.status_code == 200:
                    logger.info("Revoked Google token for user: %s", user_id)
                else:
                    logger.warning(
                        "Failed to revoke Google token for %s: %s",
                        user_id,
                        response.status_code,
                    )
            except Exception as e:
                logger.warning("Error revoking Google token for %s: %s", user_id, e)

        token.delete()
        logger.info("Deleted OAuth token for user: %s", user_id)

        return True

    @staticmethod
    def get_valid_token(user, leeway: Optional[int] = None):
        """
        Get a valid (non-expired) access token for a user.

        Automatically refreshes the token if it is expired (or within
        ``leeway`` seconds of expiring) and a refresh token is available.

        Args:
            user: Django user instance
            leeway: Optional expiry buffer in seconds (defaults to
                ``GOOGLE_OAUTH_TOKEN_REFRESH_LEEWAY``)

        Returns:
            Tuple of ``(access_token: str, token_expiry: datetime)`` or
            ``(None, None)``
        """
        token = GoogleOAuthService.get_user_token(user)
        if not token:
            return None, None

        if leeway is None:
            leeway = int(get_django_google_setting("GOOGLE_OAUTH_TOKEN_REFRESH_LEEWAY"))

        if token.is_expired(leeway=leeway) and token.can_refresh:
            try:
                token = GoogleOAuthService.refresh_user_token(token)
            except Exception as e:
                logger.error("Failed to refresh token: %s", e)
                return None, None

        if token.is_valid:
            return token.access_token, token.token_expiry

        return None, None

    @staticmethod
    def get_credentials(
        user,
        *,
        auto_refresh: bool = True,
        leeway: Optional[int] = None,
    ):
        """
        Get a ``google.oauth2.credentials.Credentials`` object for a user.

        Ideal for passing directly into ``google-api-python-client``::

            creds = GoogleOAuthService.get_credentials(request.user)
            if creds:
                service = build("calendar", "v3", credentials=creds)

        Args:
            user: Django user instance
            auto_refresh: Whether to automatically refresh expired tokens
            leeway: Optional expiry buffer in seconds (defaults to
                ``GOOGLE_OAUTH_TOKEN_REFRESH_LEEWAY``)

        Returns:
            ``Credentials`` instance, or ``None`` if no valid token exists.
        """
        token = GoogleOAuthService.get_user_token(user)
        if not token:
            return None

        if leeway is None:
            leeway = int(get_django_google_setting("GOOGLE_OAUTH_TOKEN_REFRESH_LEEWAY"))

        if auto_refresh and token.is_expired(leeway=leeway) and token.can_refresh:
            try:
                token = GoogleOAuthService.refresh_user_token(token)
            except Exception as e:
                logger.error("Failed to refresh credentials: %s", e)
                return None

        if not token.is_valid:
            return None

        return token.to_credentials()


class UserService:
    """Service class for user management operations."""

    @staticmethod
    def get_or_create_user(
        email: str,
        name: Optional[str] = None,
        google_id: Optional[str] = None,
        picture: Optional[str] = None,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
        email_verified: Optional[bool] = None,
    ):
        """
        Get or create a user from Google OAuth information.

        Looks up existing users first by ``google_id`` (via ``GoogleOAuthToken``)
        and then by case-insensitive email. When ``email_verified`` is explicitly
        ``False`` and ``GOOGLE_OAUTH_REQUIRE_VERIFIED_EMAIL`` is enabled, raises
        ``ValueError`` to prevent unverified-email account takeover.

        Args:
            email: User's email address (required)
            name: User's full name
            google_id: Google's unique user ID (sub claim)
            picture: URL to user's profile picture
            given_name: User's first name from Google
            family_name: User's last name from Google
            email_verified: Whether Google verified the email address

        Returns:
            Tuple of ``(user, created)``

        Raises:
            ValueError: If email is missing or email is unverified when required
        """
        from django_googler.models import GoogleOAuthToken

        User = get_user_model()

        if not email:
            raise ValueError("Email is required to get or create user")

        require_verified = get_django_google_setting(
            "GOOGLE_OAUTH_REQUIRE_VERIFIED_EMAIL"
        )
        if require_verified and email_verified is False:
            raise ValueError("Google account email is not verified")

        user = None

        # 1. Prefer matching by stable Google `sub` identifier if we have a token
        if google_id:
            existing_token = (
                GoogleOAuthToken.objects.select_related("user")
                .filter(google_id=google_id)
                .first()
            )
            if existing_token is not None:
                user = existing_token.user

        # 2. Fall back to case-insensitive email match
        if user is None:
            email_field = _get_email_field_name(User)
            if _user_model_has_field(email_field):
                matching_users = list(
                    User.objects.filter(**{f"{email_field}__iexact": email}).order_by(
                        "pk"
                    )[:2]
                )
                if len(matching_users) > 1:
                    logger.warning(
                        "Multiple users found with email %s; selecting earliest user",
                        email,
                    )
                if matching_users:
                    user = matching_users[0]

        if user is not None:
            logger.info("Found existing user: %s", get_user_identifier(user))
            updated = UserService._update_user_info(user, name, given_name, family_name)
            if updated:
                user.save()
                logger.info("Updated user info for: %s", get_user_identifier(user))
            return user, False

        logger.info("Creating new user: %s", email)
        user = UserService._create_new_user(
            email, name, given_name, family_name, google_id, picture
        )
        return user, True

    @staticmethod
    def _update_user_info(
        user,
        name: Optional[str] = None,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
    ) -> bool:
        """
        Update user information if name fields are missing.

        Args:
            user: User instance to update
            name: Full name to parse if given_name/family_name not provided
            given_name: First name
            family_name: Last name

        Returns:
            True if user was updated, False otherwise
        """
        updated = False

        if hasattr(user, "first_name") and not user.first_name:
            if given_name:
                user.first_name = given_name
                updated = True
            elif name:
                name_parts = name.split(maxsplit=1)
                user.first_name = name_parts[0]
                updated = True

        if hasattr(user, "last_name") and not user.last_name:
            if family_name:
                user.last_name = family_name
                updated = True
            elif name:
                name_parts = name.split(maxsplit=1)
                if len(name_parts) > 1:
                    user.last_name = name_parts[1]
                    updated = True

        return updated

    @staticmethod
    def _create_new_user(
        email: str,
        name: Optional[str] = None,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
        google_id: Optional[str] = None,
        picture: Optional[str] = None,
    ):
        """
        Create a new user from OAuth information.
        Works with any custom user model configuration.
        """
        User = get_user_model()

        # Determine first and last names cleanly even when only one is given
        name_parts = name.split(maxsplit=1) if name else []
        first_name = given_name or (name_parts[0] if name_parts else "")
        last_name = family_name or (name_parts[1] if len(name_parts) > 1 else "")

        username_field = User.USERNAME_FIELD
        email_field = _get_email_field_name(User)
        user_data: dict[str, Any] = {}

        if username_field == email_field:
            user_data[email_field] = email
        elif username_field == "username":
            user_data["username"] = UserService._generate_unique_username(email)
        else:
            user_data[username_field] = email

        for field in getattr(User, "REQUIRED_FIELDS", []):
            if field == email_field and email_field not in user_data:
                user_data[email_field] = email
            elif field == "username" and "username" not in user_data:
                user_data["username"] = UserService._generate_unique_username(email)
            elif field not in user_data:
                user_data[field] = ""

        optional_fields: dict[str, Any] = {
            email_field: email,
            "first_name": first_name,
            "last_name": last_name,
            "google_id": google_id,
            "picture": picture,
        }

        if _user_model_has_field("username") and "username" not in user_data:
            optional_fields["username"] = UserService._generate_unique_username(email)

        for field_name, field_value in optional_fields.items():
            if (
                field_value
                and field_name not in user_data
                and _user_model_has_field(field_name)
            ):
                user_data[field_name] = field_value

        try:
            user = User.objects.create_user(**user_data)
            user.set_unusable_password()
            user.save(update_fields=["password"])
        except TypeError as e:
            logger.warning(
                "create_user failed with kwargs, using direct instantiation: %s", e
            )
            user = User(**user_data)
            user.set_unusable_password()
            user.save()

        identifier = (
            user_data.get("username")
            or user_data.get(email_field)
            or user_data.get(username_field)
        )
        logger.info("Created new user: %s (identifier: %s)", email, identifier)

        # Store additional OAuth data on related profile if it exists and defines fields
        if hasattr(user, "profile"):
            profile = user.profile
            profile_updated = False
            if google_id and hasattr(profile, "google_id"):
                profile.google_id = google_id
                profile_updated = True
            if picture and hasattr(profile, "picture"):
                profile.picture = picture
                profile_updated = True
            if profile_updated:
                profile.save()

        return user

    @staticmethod
    def _generate_unique_username(email: str) -> str:
        """
        Generate a sanitized, unique username from an email address.

        Strips characters disallowed by Django's username validator and respects
        the model's ``username.max_length``.
        """
        User = get_user_model()

        raw_base = email.split("@")[0]
        base_username = _INVALID_USERNAME_CHARS_RE.sub("", raw_base) or "user"

        if not _user_model_has_field("username"):
            return base_username

        username_field = User._meta.get_field("username")
        max_length = getattr(username_field, "max_length", 150) or 150
        base_username = base_username[:max_length]

        if not User.objects.filter(username=base_username).exists():
            return base_username

        counter = 1
        while True:
            suffix = str(counter)
            candidate = f"{base_username[: max_length - len(suffix)]}{suffix}"
            if not User.objects.filter(username=candidate).exists():
                return candidate
            counter += 1


class OAuthFlowService:
    """Service class for managing session-based OAuth flow state and validation."""

    @staticmethod
    def store_state(request, state: str) -> None:
        """Store OAuth state in session for CSRF protection."""
        request.session["oauth_state"] = state

    @staticmethod
    def verify_state(request, state: Optional[str]) -> bool:
        """Verify OAuth state in constant time for CSRF protection."""
        session_state = request.session.get("oauth_state")
        if not state or not session_state:
            return False
        return secrets.compare_digest(str(state), str(session_state))

    @staticmethod
    def store_scopes(request, scopes: Optional[list[str]]) -> None:
        """Store requested OAuth scopes in session for callback verification."""
        if scopes is not None:
            request.session["oauth_scopes"] = list(scopes)
        else:
            request.session.pop("oauth_scopes", None)

    @staticmethod
    def get_scopes(request) -> Optional[list[str]]:
        """Retrieve requested OAuth scopes stored in session."""
        return request.session.get("oauth_scopes")

    @staticmethod
    def store_code_verifier(request, code_verifier: Optional[str]) -> None:
        """Store PKCE code verifier in session."""
        if code_verifier:
            request.session["oauth_code_verifier"] = code_verifier
        else:
            request.session.pop("oauth_code_verifier", None)

    @staticmethod
    def get_code_verifier(request) -> Optional[str]:
        """Retrieve PKCE code verifier from session."""
        return request.session.get("oauth_code_verifier")

    @staticmethod
    def clear_state(request) -> None:
        """Clear OAuth state, scopes, and PKCE verifier from session."""
        for key in ("oauth_state", "oauth_scopes", "oauth_code_verifier"):
            request.session.pop(key, None)

    @staticmethod
    def store_next_url(request, next_url: str) -> None:
        """Store the next URL for redirect after OAuth."""
        request.session["oauth_next"] = next_url

    @staticmethod
    def get_next_url(request, default: str = "/") -> str:
        """Get and clear the next URL from session."""
        return request.session.pop("oauth_next", default)
