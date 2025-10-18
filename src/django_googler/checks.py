"""
Django system checks for django_googler configuration.
"""

from django.core.checks import Error, Warning, register


@register()
def check_google_oauth_settings(app_configs, **kwargs):
    """Check that required Google OAuth settings are configured."""
    from django_googler.defaults import (
        GOOGLE_OAUTH_CLIENT_ID,
        GOOGLE_OAUTH_CLIENT_SECRET,
        GOOGLE_OAUTH_REDIRECT_URIS,
    )

    errors = []

    # Check CLIENT_ID
    if not GOOGLE_OAUTH_CLIENT_ID:
        errors.append(
            Error(
                "GOOGLE_OAUTH_CLIENT_ID is not configured",
                hint=(
                    "Set GOOGLE_OAUTH_CLIENT_ID in your Django settings. "
                    "Get it from "
                    "https://console.cloud.google.com/apis/credentials"
                ),
                id="django_googler.E001",
            )
        )

    # Check CLIENT_SECRET
    if not GOOGLE_OAUTH_CLIENT_SECRET:
        errors.append(
            Error(
                "GOOGLE_OAUTH_CLIENT_SECRET is not configured",
                hint=(
                    "Set GOOGLE_OAUTH_CLIENT_SECRET in your Django settings. "
                    "Get it from "
                    "https://console.cloud.google.com/apis/credentials"
                ),
                id="django_googler.E002",
            )
        )

    # Warn if using default redirect URIs
    default_uri = "http://localhost:8000/api/googler/callback"
    if GOOGLE_OAUTH_REDIRECT_URIS == [default_uri]:
        errors.append(
            Warning(
                "Using default GOOGLE_OAUTH_REDIRECT_URIS",
                hint=(
                    "Set GOOGLE_OAUTH_REDIRECT_URIS to match " "your application URLs"
                ),
                id="django_googler.W001",
            )
        )

    return errors
