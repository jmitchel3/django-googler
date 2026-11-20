"""
Django models for django_googler.

This module defines the database models for storing Google OAuth tokens
and related user information.
"""

from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import models
from django.utils import timezone

from django_googler.defaults import get_django_google_setting


def get_user_identifier(user) -> str:
    """
    Return a human-readable identifier for any Django User model.

    Safely supports custom user models that may not define ``email`` or
    ``username`` fields.
    """
    email = getattr(user, "email", None)
    if email:
        return str(email)
    get_username = getattr(user, "get_username", None)
    if callable(get_username):
        username = get_username()
        if username:
            return str(username)
    return str(user)


class GoogleOAuthToken(models.Model):
    """
    Stores Google OAuth tokens for authenticated users.

    This model persists access tokens, refresh tokens, and associated
    metadata for users who have authenticated via Google OAuth.

    Note:
        Tokens are stored as text in the database. In high-security production
        environments, ensure database-level encryption at rest (e.g., encrypted
        volumes/TDE) or use an encrypted database layer.

    Example::

        token = GoogleOAuthToken.objects.get(user=request.user)
        if token.is_expired(leeway=60):
            from django_googler.services import GoogleOAuthService
            token = GoogleOAuthService.refresh_user_token(token)

        credentials = token.to_credentials()
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="google_oauth_token",
        help_text="The user this token belongs to",
    )

    access_token = models.TextField(
        help_text="Google OAuth access token (used for API requests)"
    )

    refresh_token = models.TextField(
        blank=True,
        null=True,
        help_text="Google OAuth refresh token (used to get new access tokens)",
    )

    token_expiry = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the access token expires",
    )

    scopes = models.TextField(
        blank=True,
        default="",
        help_text="Comma-separated list of OAuth scopes granted",
    )

    id_token = models.TextField(
        blank=True,
        null=True,
        help_text="Google ID token (JWT containing user info)",
    )

    google_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Google's unique user identifier (sub claim from ID token)",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this token was first created",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this token was last updated",
    )

    class Meta:
        verbose_name = "Google OAuth Token"
        verbose_name_plural = "Google OAuth Tokens"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["google_id"]),
            models.Index(fields=["token_expiry"]),
        ]

    def __str__(self) -> str:
        return f"Google OAuth Token for {get_user_identifier(self.user)}"

    def is_expired(self, leeway: int = 0) -> bool:
        """
        Check if the access token is expired.

        Args:
            leeway: Optional buffer in seconds before actual expiry to consider
                the token expired (helps avoid race-condition 401s).

        Returns:
            True if token is expired or expiry is unknown, False otherwise.
        """
        if not self.token_expiry:
            return True
        threshold = self.token_expiry - timedelta(seconds=leeway)
        return timezone.now() >= threshold

    def has_scope(self, scope: str) -> bool:
        """
        Check if this token has a specific OAuth scope.

        Args:
            scope: The scope to check for (e.g., ``'email'``, ``'profile'``)

        Returns:
            True if the scope is granted, False otherwise.
        """
        return scope in self.get_scopes_list()

    def get_scopes_list(self) -> list[str]:
        """
        Get the list of OAuth scopes.

        Returns:
            List of scope strings.
        """
        if not self.scopes:
            return []
        return [s.strip() for s in self.scopes.split(",") if s.strip()]

    def set_scopes_list(self, scopes: list[str]) -> None:
        """
        Set the OAuth scopes from a list.

        Args:
            scopes: List of scope strings.
        """
        cleaned = [s.strip() for s in scopes if s and s.strip()]
        self.scopes = ",".join(dict.fromkeys(cleaned))

    def to_credentials(self):
        """
        Build a ``google.oauth2.credentials.Credentials`` instance from this token.

        Compatible with ``google-api-python-client`` (e.g. ``build("calendar", "v3",
        credentials=token.to_credentials())``).

        Returns:
            ``google.oauth2.credentials.Credentials`` instance.
        """
        from google.oauth2.credentials import Credentials

        # google-auth compares expiry against naive UTC datetimes
        expiry = self.token_expiry
        if expiry is not None and timezone.is_aware(expiry):
            expiry = expiry.astimezone(dt_timezone.utc).replace(tzinfo=None)

        return Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            id_token=self.id_token,
            token_uri=get_django_google_setting("GOOGLE_OAUTH_TOKEN_URI"),
            client_id=get_django_google_setting("GOOGLE_OAUTH_CLIENT_ID") or None,
            client_secret=(
                get_django_google_setting("GOOGLE_OAUTH_CLIENT_SECRET") or None
            ),
            scopes=self.get_scopes_list() or None,
            expiry=expiry,
        )

    @property
    def is_valid(self) -> bool:
        """
        Check if the token is valid (not expired and has an access token).

        Returns:
            True if token is valid and not expired, False otherwise.
        """
        return bool(self.access_token and not self.is_expired())

    @property
    def can_refresh(self) -> bool:
        """
        Check if this token can be refreshed.

        Returns:
            True if a refresh token is available, False otherwise.
        """
        return bool(self.refresh_token)
