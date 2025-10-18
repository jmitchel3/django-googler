from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-googler")
except PackageNotFoundError:
    # Package is not installed
    __version__ = "unknown"

# Import services
from django_googler.services import GoogleOAuthService, OAuthFlowService, UserService

# Import views
from django_googler.views import (
    CurrentUserAPIView,
    GoogleOAuthCallbackAPIView,
    GoogleOAuthCallbackView,
    GoogleOAuthLoginAPIView,
    GoogleOAuthLoginView,
    GoogleOAuthLogoutAPIView,
)

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
