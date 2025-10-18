import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views import View

from django_googler.mixins import OAuthCallbackProcessingMixin, OAuthFlowInitMixin
from django_googler.services import OAuthFlowService

logger = logging.getLogger(__name__)


# ============================================================================
# Regular Django Views
# ============================================================================


class GoogleOAuthLoginView(OAuthFlowInitMixin, View):
    """
    Regular Django view to initiate Google OAuth flow.

    Redirects the user to Google's OAuth consent screen.
    """

    def get_redirect_uri_name(self) -> str:
        """Get the URL name for the OAuth callback."""
        return "django_googler:google-callback"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle GET request to start OAuth flow."""
        try:
            # Store the next URL if provided
            next_url = request.GET.get("next", "/")
            OAuthFlowService.store_next_url(request, next_url)

            # Initialize OAuth flow using mixin
            authorization_url, state = self.init_oauth_flow(request)

            # Redirect to Google's OAuth page
            return redirect(authorization_url)

        except Exception as e:
            logger.error(f"Error initiating OAuth flow: {str(e)}", exc_info=True)
            # Redirect to login with error message
            error_params = urlencode({"error": "oauth_init_failed"})
            login_url = getattr(settings, "LOGIN_URL", "/login/")
            return redirect(f"{login_url}?{error_params}")


class GoogleOAuthCallbackView(OAuthCallbackProcessingMixin, View):
    """
    Regular Django view to handle Google OAuth callback.

    Processes the OAuth callback, creates/authenticates the user,
    and logs them into Django.
    """

    def get_redirect_uri_name(self) -> str:
        """Get the URL name for the OAuth callback."""
        return "django_googler:google-callback"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle GET request from OAuth callback."""
        try:
            # Check for errors from Google
            error = request.GET.get("error")
            if error:
                logger.warning(f"OAuth error from Google: {error}")
                return self._redirect_with_error(error)

            # Get authorization code
            code = request.GET.get("code")
            if not code:
                return self._redirect_with_error("missing_code")

            # Get state parameter
            state = request.GET.get("state")

            # Process OAuth callback using mixin
            user, user_info, credentials = self.process_oauth_callback(
                request, code, state
            )

            # Log the user in
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")

            # Redirect to next URL or default
            next_url = OAuthFlowService.get_next_url(request, default="/")
            return redirect(next_url)

        except ValueError as e:
            # Handle validation errors (state mismatch, missing email, etc.)
            logger.warning(f"Validation error in OAuth callback: {str(e)}")
            if "state" in str(e).lower():
                return self._redirect_with_error("invalid_state")
            elif "email" in str(e).lower():
                return self._redirect_with_error("no_email")
            return self._redirect_with_error("oauth_callback_failed")
        except Exception as e:
            logger.error(f"Error processing OAuth callback: {str(e)}", exc_info=True)
            return self._redirect_with_error("oauth_callback_failed")

    def _redirect_with_error(self, error: str) -> HttpResponse:
        """
        Redirect to login page with error parameter.

        Args:
            error: Error code to include in redirect

        Returns:
            HttpResponse redirect
        """
        error_params = urlencode({"error": error})
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?{error_params}")
