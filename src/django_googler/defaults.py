"""
Configuration for django_googler OAuth integration.

This module provides a centralized, dynamic way to manage Google OAuth settings
with sensible defaults that can be overridden in Django settings (including at
runtime with ``@override_settings`` in tests).

To override any setting, add it to your Django ``settings.py``::

    GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    GOOGLE_OAUTH_REDIRECT_URIS = ["http://localhost:8000/api/auth/google/callback/"]
    GOOGLE_OAUTH_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]
"""

from typing import Any

from django.conf import settings

# Default settings
DEFAULTS: dict[str, Any] = {
    "GOOGLE_OAUTH_CLIENT_ID": "",
    "GOOGLE_OAUTH_CLIENT_SECRET": "",
    "GOOGLE_OAUTH_REDIRECT_URIS": ["http://localhost:8000/api/auth/google/callback/"],
    "GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS": None,
    "GOOGLE_OAUTH_SCOPES": [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    "GOOGLE_OAUTH_STATE": None,
    "GOOGLE_OAUTH_STATE_MAX_AGE": 600,
    "GOOGLE_OAUTH_AUTH_URI": "https://accounts.google.com/o/oauth2/auth",
    "GOOGLE_OAUTH_TOKEN_URI": "https://oauth2.googleapis.com/token",
    "GOOGLE_OAUTH_REVOKE_URI": "https://oauth2.googleapis.com/revoke",
    # Security & token handling settings
    "GOOGLE_OAUTH_REQUIRE_VERIFIED_EMAIL": True,
    "GOOGLE_OAUTH_USE_PKCE": True,
    "GOOGLE_OAUTH_RETURN_TOKENS": False,  # Return Google tokens in API response
    "GOOGLE_OAUTH_STORE_TOKENS": False,  # Store tokens in session
    "GOOGLE_OAUTH_SAVE_TOKENS_TO_DB": True,  # Save tokens to database
    "GOOGLE_OAUTH_REVOKE_ON_LOGOUT": False,  # Revoke tokens on logout
    "GOOGLE_OAUTH_TOKEN_REFRESH_LEEWAY": 60,  # Seconds before expiry to proactively refresh
    "GOOGLE_OAUTH_REQUEST_TIMEOUT": 10,  # Outbound HTTP request timeout in seconds
    # URL names for OAuth redirects
    "GOOGLE_OAUTH_LOGIN_REDIRECT_URI_NAME": "django_googler_api:google-login",
    "GOOGLE_OAUTH_CALLBACK_REDIRECT_URI_NAME": "django_googler_api:google-callback",
    "DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK": False,
    # Customization hooks
    "GOOGLE_OAUTH_USER_SERIALIZER": None,
    "GOOGLE_OAUTH_AUTH_BACKEND": None,
    # Throttle rates
    "GOOGLE_OAUTH_LOGIN_THROTTLE_RATE": "30/hour",
    "GOOGLE_OAUTH_CALLBACK_THROTTLE_RATE": "100/hour",
}


def get_django_google_setting(name: str) -> Any:
    """
    Get a django_googler setting from Django settings or return the default.

    Reads dynamically from ``django.conf.settings`` so runtime overrides
    (such as ``@override_settings`` in tests) are always respected.

    Args:
        name: The setting name (e.g., ``'GOOGLE_OAUTH_CLIENT_ID'``)

    Returns:
        The setting value from Django settings, or the default if not set.
    """
    default = DEFAULTS.get(name)
    value = getattr(settings, name, default)
    # Return a fresh copy for mutable defaults so callers cannot mutate DEFAULTS
    if value is default and isinstance(default, (list, dict)):
        return default.copy()
    return value


class GoogleOAuthSettings:
    """Dynamic settings accessor for django_googler."""

    def __getattr__(self, name: str) -> Any:
        if name not in DEFAULTS:
            raise AttributeError(f"Invalid django_googler setting: {name!r}")
        return get_django_google_setting(name)


app_settings = GoogleOAuthSettings()


def __getattr__(name: str) -> Any:
    """
    Module-level dynamic lookup for backwards compatibility.

    Allows ``from django_googler.defaults import GOOGLE_OAUTH_CLIENT_ID`` while
    still resolving the live value from Django settings at access time.
    """
    if name in DEFAULTS:
        return get_django_google_setting(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
