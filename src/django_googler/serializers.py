"""
Serializers for django_googler DRF views.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.utils.module_loading import import_string
from rest_framework import serializers

from django_googler.defaults import get_django_google_setting


def _get_user_serializer_fields(User) -> list[str]:
    """Compute available default fields for any custom Django User model."""
    pk_name = User._meta.pk.name if User._meta.pk else "id"
    available_fields = [pk_name]
    for field_name in ("email", "username", "first_name", "last_name"):
        if field_name in available_fields:
            continue
        try:
            User._meta.get_field(field_name)
            available_fields.append(field_name)
        except FieldDoesNotExist:
            pass
    return available_fields


class GoogleOAuthLoginResponseSerializer(serializers.Serializer):
    """Response serializer for OAuth login endpoint."""

    authorization_url = serializers.URLField(
        help_text="URL to redirect user to for Google OAuth"
    )
    state = serializers.CharField(help_text="Signed state token for CSRF protection")


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
    code_verifier = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional PKCE code verifier if client-side PKCE was used",
    )


class UserSerializer(serializers.ModelSerializer):
    """
    User information serializer that adapts safely to any custom user model.

    Creates a per-instance ``Meta`` class so concurrent requests or schema
    generators never mutate shared class state.
    """

    class Meta:
        model = None
        fields: list[str] = []

    def __init__(self, *args, **kwargs):
        User = get_user_model()
        available_fields = _get_user_serializer_fields(User)

        class _InstanceMeta:
            model = User
            fields = available_fields

        self.Meta = _InstanceMeta
        super().__init__(*args, **kwargs)


def get_user_serializer_class():
    """
    Return the configured user serializer class.

    Respects ``GOOGLE_OAUTH_USER_SERIALIZER`` (dotted Python path or serializer
    class) and defaults to :class:`UserSerializer`.
    """
    configured = get_django_google_setting("GOOGLE_OAUTH_USER_SERIALIZER")
    if not configured:
        return UserSerializer
    if isinstance(configured, str):
        return import_string(configured)
    return configured


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
            user_serializer_cls = get_user_serializer_class()
            self.fields["user"] = user_serializer_cls(
                help_text="Authenticated user information"
            )

    access = serializers.CharField(help_text="JWT access token for backend API calls")
    refresh = serializers.CharField(
        help_text="JWT refresh token to obtain new access tokens when they expire"
    )
    google_tokens = GoogleTokensSerializer(
        required=False,
        help_text="Google OAuth tokens (only if GOOGLE_OAUTH_RETURN_TOKENS=True)",
    )
