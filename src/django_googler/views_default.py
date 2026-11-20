"""
Standard Django session-based Google OAuth views.
"""

import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, resolve_url
from django.views import View

from django_googler.defaults import get_django_google_setting
from django_googler.mixins import OAuthCallbackProcessingMixin, OAuthFlowInitMixin
from django_googler.security import is_safe_next_url
from django_googler.services import OAuthFlowService
from django_googler.signals import google_oauth_failed

logger = logging.getLogger(__name__)


def _get_login_url() -> str:
    """Resolve Django's configured LOGIN_URL dynamically."""
    return resolve_url(getattr(settings, "LOGIN_URL", "/login/"))


def _get_login_redirect_url() -> str:
    """Resolve Django's configured LOGIN_REDIRECT_URL dynamically."""
    return resolve_url(getattr(settings, "LOGIN_REDIRECT_URL", "/"))


def _get_auth_backend() -> str:
    """Resolve the authentication backend to pass to ``django.contrib.auth.login``."""
    configured = get_django_google_setting("GOOGLE_OAUTH_AUTH_BACKEND")
    if configured:
        return configured
    backends = getattr(settings, "AUTHENTICATION_BACKENDS", None)
    if backends:
        return backends[0]
    return "django.contrib.auth.backends.ModelBackend"


def _append_query_params(url: str, params: dict[str, str]) -> str:
    """Safely append query parameters to a URL that may already have a query string."""
    parsed = urlparse(url)
    existing = parse_qsl(parsed.query, keep_blank_values=True)
    existing.extend(params.items())
    new_query = urlencode(existing)
    return urlunparse(parsed._replace(query=new_query))


class GoogleOAuthLoginView(OAuthFlowInitMixin, View):
    """
    Regular Django view to initiate Google OAuth flow.

    Redirects the user to Google's OAuth consent screen and safely stores
    validated ``next`` redirect URLs in the session.
    """

    def get_redirect_uri_name(self) -> str:
        """Get the URL name for the OAuth callback."""
        return "django_googler:google-callback"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle GET request to start OAuth flow."""
        try:
            default_next = _get_login_redirect_url()
            raw_next = request.GET.get("next")
            next_url = raw_next if is_safe_next_url(request, raw_next) else default_next
            OAuthFlowService.store_next_url(request, next_url)

            authorization_url, _state = self.init_oauth_flow(request)
            return redirect(authorization_url)

        except Exception as e:
            logger.error("Error initiating OAuth flow: %s", e, exc_info=True)
            return redirect(
                _append_query_params(_get_login_url(), {"error": "oauth_init_failed"})
            )


class GoogleOAuthCallbackView(OAuthCallbackProcessingMixin, View):
    """
    Regular Django view to handle Google OAuth callback.

    Processes the OAuth callback, creates/authenticates the user,
    and logs them into Django's session.
    """

    def get_redirect_uri_name(self) -> str:
        """Get the URL name for the OAuth callback."""
        return "django_googler:google-callback"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle GET request from OAuth callback."""
        try:
            error = request.GET.get("error")
            if error:
                logger.warning("OAuth error from Google: %s", error)
                return self._fail_and_redirect(request, error)

            code = request.GET.get("code")
            if not code:
                return self._fail_and_redirect(request, "missing_code")

            state = request.GET.get("state")

            user, _user_info, _credentials, _user_created = self.process_oauth_callback(
                request, code, state
            )

            login(request, user, backend=_get_auth_backend())

            default_next = _get_login_redirect_url()
            next_url = OAuthFlowService.get_next_url(request, default=default_next)
            if not is_safe_next_url(request, next_url):
                next_url = default_next
            return redirect(next_url)

        except ValueError as e:
            logger.warning("Validation error in OAuth callback: %s", e)
            msg = str(e).lower()
            if "state" in msg:
                error_code = "invalid_state"
            elif "verified" in msg:
                error_code = "email_not_verified"
            elif "email" in msg:
                error_code = "no_email"
            else:
                error_code = "oauth_callback_failed"
            return self._fail_and_redirect(request, error_code, exception=e)

        except Exception as e:
            logger.error("Error processing OAuth callback: %s", e, exc_info=True)
            return self._fail_and_redirect(
                request, "oauth_callback_failed", exception=e
            )

    def _fail_and_redirect(
        self,
        request: HttpRequest,
        error: str,
        exception: Exception | None = None,
    ) -> HttpResponse:
        """Emit failure signal and redirect to LOGIN_URL with error query param."""
        google_oauth_failed.send(
            sender=self.__class__,
            error=error,
            request=request,
            exception=exception,
        )
        return self._redirect_with_error(error)

    def _redirect_with_error(self, error: str) -> HttpResponse:
        """Redirect to login page with error parameter."""
        return redirect(_append_query_params(_get_login_url(), {"error": error}))
