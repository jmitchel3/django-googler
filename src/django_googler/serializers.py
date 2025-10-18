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


class UserSerializer(serializers.ModelSerializer):
    """User information serializer."""

    def __init__(self, *args, **kwargs):
        from django.contrib.auth import get_user_model

        self.Meta.model = get_user_model()
        super().__init__(*args, **kwargs)

    class Meta:
        model = None  # Will be set in __init__
        fields = ["id", "email", "username", "first_name", "last_name"]


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
    """Response serializer for OAuth callback endpoint with JWT tokens."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Define user field here to avoid AppRegistryNotReady when module loads
        if "user" not in self.fields:
            self.fields["user"] = UserSerializer(
                help_text="Authenticated user information"
            )

    access = serializers.CharField(help_text="JWT access token for backend API calls")
    refresh = serializers.CharField(
        help_text="JWT refresh token to obtain new access tokens when they expire"
    )
    google_tokens = GoogleTokensSerializer(
        required=False,
        help_text=("Google OAuth tokens " "(only if GOOGLE_OAUTH_RETURN_TOKENS=True)"),
    )
