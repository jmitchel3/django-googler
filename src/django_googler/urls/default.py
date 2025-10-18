from django.urls import path

from django_googler.views_default import GoogleOAuthCallbackView, GoogleOAuthLoginView

app_name = "django_googler"
urlpatterns = [
    path("google/login/", GoogleOAuthLoginView.as_view(), name="google-login"),
    path("google/callback/", GoogleOAuthCallbackView.as_view(), name="google-callback"),
]
