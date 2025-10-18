"""
Django models for django_googler.

This module defines the database models for storing Google OAuth tokens
and related user information.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class GoogleOAuthToken(models.Model):
    """
    Stores Google OAuth tokens for authenticated users.

    This model persists access tokens, refresh tokens, and associated
    metadata for users who have authenticated via Google OAuth.

    Attributes:
        user: Foreign key to the Django user model
        access_token: Google OAuth access token (encrypted in production)
        refresh_token: Google OAuth refresh token (encrypted in production)
        token_expiry: When the access token expires
        scopes: Comma-separated list of granted OAuth scopes
        id_token: Google ID token (JWT)
        google_id: Google's unique user identifier (sub claim)
        created_at: When the token was first created
        updated_at: When the token was last updated

    Example:
        # Get user's token
        token = GoogleOAuthToken.objects.get(user=request.user)

        # Check if token is expired
        if token.is_expired():
            # Refresh the token
            from django_googler.services import GoogleOAuthService
            GoogleOAuthService.refresh_user_token(token)

        # Use the token
        headers = {'Authorization': f'Bearer {token.access_token}'}
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

    def __str__(self):
        return f"Google OAuth Token for {self.user.email}"

    def is_expired(self) -> bool:
        """
        Check if the access token is expired.

        Returns:
            True if token is expired or expiry is unknown, False otherwise
        """
        if not self.token_expiry:
            return True
        return timezone.now() >= self.token_expiry

    def has_scope(self, scope: str) -> bool:
        """
        Check if this token has a specific OAuth scope.

        Args:
            scope: The scope to check for (e.g., 'email', 'profile')

        Returns:
            True if the scope is granted, False otherwise
        """
        if not self.scopes:
            return False
        scope_list = [s.strip() for s in self.scopes.split(",")]
        return scope in scope_list

    def get_scopes_list(self) -> list[str]:
        """
        Get the list of OAuth scopes.

        Returns:
            List of scope strings
        """
        if not self.scopes:
            return []
        return [s.strip() for s in self.scopes.split(",") if s.strip()]

    def set_scopes_list(self, scopes: list[str]) -> None:
        """
        Set the OAuth scopes from a list.

        Args:
            scopes: List of scope strings
        """
        self.scopes = ",".join(scopes)

    @property
    def is_valid(self) -> bool:
        """
        Check if the token is valid (not expired and has required data).

        Returns:
            True if token is valid and not expired, False otherwise
        """
        return bool(self.access_token and not self.is_expired())

    @property
    def can_refresh(self) -> bool:
        """
        Check if this token can be refreshed.

        Returns:
            True if a refresh token is available, False otherwise
        """
        return bool(self.refresh_token)
