from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-googler")
except PackageNotFoundError:
    # Package is not installed
    __version__ = "unknown"

_LAZY_IMPORTS = {
    "app_settings": ("django_googler.defaults", "app_settings"),
    "GoogleOAuthService": ("django_googler.services", "GoogleOAuthService"),
    "OAuthFlowService": ("django_googler.services", "OAuthFlowService"),
    "UserService": ("django_googler.services", "UserService"),
    "GoogleOAuthLoginView": ("django_googler.views_default", "GoogleOAuthLoginView"),
    "GoogleOAuthCallbackView": (
        "django_googler.views_default",
        "GoogleOAuthCallbackView",
    ),
    "GoogleOAuthLoginAPIView": ("django_googler.views_api", "GoogleOAuthLoginAPIView"),
    "GoogleOAuthCallbackAPIView": (
        "django_googler.views_api",
        "GoogleOAuthCallbackAPIView",
    ),
    "CurrentUserAPIView": ("django_googler.views_api", "CurrentUserAPIView"),
    "GoogleOAuthLogoutAPIView": (
        "django_googler.views_api",
        "GoogleOAuthLogoutAPIView",
    ),
    "google_oauth_success": ("django_googler.signals", "google_oauth_success"),
    "google_oauth_failed": ("django_googler.signals", "google_oauth_failed"),
    "google_oauth_token_refreshed": (
        "django_googler.signals",
        "google_oauth_token_refreshed",
    ),
    "google_oauth_logout": ("django_googler.signals", "google_oauth_logout"),
}


def __getattr__(name: str):
    """Lazy import to avoid loading Django models before apps are ready."""
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        module = __import__(module_name, fromlist=[attr_name])
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
    "app_settings",
    # Services
    "GoogleOAuthService",
    "OAuthFlowService",
    "UserService",
    # Regular Django Views
    "GoogleOAuthLoginView",
    "GoogleOAuthCallbackView",
    # DRF Views
    "GoogleOAuthLoginAPIView",
    "GoogleOAuthCallbackAPIView",
    "CurrentUserAPIView",
    "GoogleOAuthLogoutAPIView",
    # Signals
    "google_oauth_success",
    "google_oauth_failed",
    "google_oauth_token_refreshed",
    "google_oauth_logout",
]
