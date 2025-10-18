"""
Serializers for django_googler DRF views.
"""

from rest_framework import serializers


class GoogleOAuthLoginResponseSerializer(serializers.Serializer):
    """Response serializer for OAuth login endpoint."""

    authorization_url = serializers.URLField(
        help_text="URL to redirect user to for Google OAuth"
    )
    state = serializers.CharField(help_text="CSRF state token for security")


class GoogleOAuthCallbackRequestSerializer(serializers.Serializer):
    """Request serializer for OAuth callback endpoint."""

    code = serializers.CharField(
        required=True, help_text="Authorization code from Google"
    )
    state = serializers.CharField(
        required=True, help_text="State parameter for CSRF protection"
    )
    redirect_uri = serializers.URLField(
        required=False,
        allow_blank=True,
        help_text="Optional redirect URI used in OAuth flow",
    )


class UserSerializer(serializers.Serializer):
    """User information serializer."""

    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)


class GoogleTokensSerializer(serializers.Serializer):
    """Google OAuth tokens serializer."""

    access_token = serializers.CharField(help_text="Google access token for API calls")
    refresh_token = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Google refresh token for getting new access tokens",
    )
    expires_in = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Token expiration time (ISO format)",
    )


class GoogleOAuthCallbackResponseSerializer(serializers.Serializer):
    """Response serializer for OAuth callback endpoint."""

    token = serializers.CharField(
        help_text="DRF authentication token for backend API calls"
    )
    user = UserSerializer(help_text="Authenticated user information")
    google_tokens = GoogleTokensSerializer(
        required=False,
        help_text=("Google OAuth tokens " "(only if GOOGLE_OAUTH_RETURN_TOKENS=True)"),
    )
