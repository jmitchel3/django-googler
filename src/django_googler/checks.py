"""
Django system checks for django_googler configuration.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register

from django_googler.defaults import get_django_google_setting


@register()
def check_google_oauth_settings(app_configs, **kwargs):
    """Check that required Google OAuth settings are properly configured."""
    client_id = get_django_google_setting("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = get_django_google_setting("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uris = get_django_google_setting("GOOGLE_OAUTH_REDIRECT_URIS")
    scopes = get_django_google_setting("GOOGLE_OAUTH_SCOPES")
    allow_get_callback = get_django_google_setting(
        "DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK"
    )

    errors = []

    if not client_id:
        errors.append(
            Error(
                "GOOGLE_OAUTH_CLIENT_ID is not configured",
                hint=(
                    "Set GOOGLE_OAUTH_CLIENT_ID in your Django settings. "
                    "Get it from https://console.cloud.google.com/apis/credentials"
                ),
                id="django_googler.E001",
            )
        )

    if not client_secret:
        errors.append(
            Error(
                "GOOGLE_OAUTH_CLIENT_SECRET is not configured",
                hint=(
                    "Set GOOGLE_OAUTH_CLIENT_SECRET in your Django settings. "
                    "Get it from https://console.cloud.google.com/apis/credentials"
                ),
                id="django_googler.E002",
            )
        )

    if not isinstance(redirect_uris, (list, tuple)):
        errors.append(
            Error(
                "GOOGLE_OAUTH_REDIRECT_URIS must be a list or tuple of URL strings",
                hint='Example: GOOGLE_OAUTH_REDIRECT_URIS = ["https://example.com/api/auth/google/callback/"]',
                id="django_googler.E003",
            )
        )
    elif not settings.DEBUG and any(
        "localhost" in uri or "127.0.0.1" in uri for uri in redirect_uris
    ):
        errors.append(
            Warning(
                "GOOGLE_OAUTH_REDIRECT_URIS contains localhost/127.0.0.1 while DEBUG=False.",
                hint="Set GOOGLE_OAUTH_REDIRECT_URIS to your production callback URLs.",
                id="django_googler.W001",
            )
        )

    if not isinstance(scopes, (list, tuple)):
        errors.append(
            Error(
                "GOOGLE_OAUTH_SCOPES must be a list or tuple of scope strings",
                hint='Example: GOOGLE_OAUTH_SCOPES = ["openid", "email", "profile"]',
                id="django_googler.E004",
            )
        )

    if not settings.DEBUG and allow_get_callback:
        errors.append(
            Warning(
                "DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK=True is not recommended in production.",
                hint=(
                    "Use POST from your frontend to exchange authorization codes so "
                    "OAuth codes are not exposed in browser history or server logs."
                ),
                id="django_googler.W002",
            )
        )

    return errors
