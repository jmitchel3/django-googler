from django.urls import path

from django_googler.views_api import (
    CurrentUserAPIView,
    GoogleOAuthCallbackAPIView,
    GoogleOAuthLoginAPIView,
    GoogleOAuthLogoutAPIView,
)

app_name = "django_googler_api"
urlpatterns = [
    path("google/login/", GoogleOAuthLoginAPIView.as_view(), name="google-login"),
    path(
        "google/callback/", GoogleOAuthCallbackAPIView.as_view(), name="google-callback"
    ),
    path("google/logout/", GoogleOAuthLogoutAPIView.as_view(), name="google-logout"),
    path("me/", CurrentUserAPIView.as_view(), name="current-user"),
]
