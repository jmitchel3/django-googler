from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-googler")
except PackageNotFoundError:
    # Package is not installed
    __version__ = "unknown"


def __getattr__(name):
    """Lazy import to avoid loading Django models before apps are ready."""
    if name == "GoogleOAuthService":
        from django_googler.services import GoogleOAuthService

        return GoogleOAuthService
    elif name == "OAuthFlowService":
        from django_googler.services import OAuthFlowService

        return OAuthFlowService
    elif name == "UserService":
        from django_googler.services import UserService

        return UserService
    elif name == "GoogleOAuthLoginView":
        from django_googler.views_default import GoogleOAuthLoginView

        return GoogleOAuthLoginView
    elif name == "GoogleOAuthCallbackView":
        from django_googler.views_default import GoogleOAuthCallbackView

        return GoogleOAuthCallbackView
    elif name == "GoogleOAuthLoginAPIView":
        from django_googler.views_api import GoogleOAuthLoginAPIView

        return GoogleOAuthLoginAPIView
    elif name == "GoogleOAuthCallbackAPIView":
        from django_googler.views_api import GoogleOAuthCallbackAPIView

        return GoogleOAuthCallbackAPIView
    elif name == "CurrentUserAPIView":
        from django_googler.views_api import CurrentUserAPIView

        return CurrentUserAPIView
    elif name == "GoogleOAuthLogoutAPIView":
        from django_googler.views_api import GoogleOAuthLogoutAPIView

        return GoogleOAuthLogoutAPIView
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
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
]
