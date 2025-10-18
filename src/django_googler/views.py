"""
OAuth views for django_googler.

This module provides both Django Rest Framework and regular Django views
for handling Google OAuth authentication flows.

Usage:
    In your urls.py:

    # For Django Rest Framework:
    from django_googler.views import (
        GoogleOAuthLoginAPIView,
        GoogleOAuthCallbackAPIView,
    )

    urlpatterns = [
        path(
            'api/auth/google/login/',
            GoogleOAuthLoginAPIView.as_view(),
            name='google-login-api',
        ),
        path(
            'api/auth/google/callback/',
            GoogleOAuthCallbackAPIView.as_view(),
            name='google-callback-api',
        ),
    ]

    # For regular Django views:
    from django_googler.views import (
        GoogleOAuthLoginView,
        GoogleOAuthCallbackView,
    )

    urlpatterns = [
        path(
            'auth/google/login/',
            GoogleOAuthLoginView.as_view(),
            name='google-login',
        ),
        path(
            'auth/google/callback/',
            GoogleOAuthCallbackView.as_view(),
            name='google-callback',
        ),
    ]
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from django_googler.platform_client import get_google_auth_flow, get_google_auth_url
from django_googler.serializers import (
    GoogleOAuthCallbackRequestSerializer,
    GoogleOAuthCallbackResponseSerializer,
    GoogleOAuthLoginResponseSerializer,
)
from django_googler.services import GoogleOAuthService, OAuthFlowService, UserService

logger = logging.getLogger(__name__)


# ============================================================================
# Throttle Classes
# ============================================================================


class GoogleOAuthLoginThrottle(AnonRateThrottle):
    """Throttle for OAuth login endpoint - 10 requests per hour."""

    rate = "10/hour"


class GoogleOAuthCallbackThrottle(AnonRateThrottle):
    """Throttle for OAuth callback endpoint - 20 requests per hour."""

    rate = "20/hour"


# ============================================================================
# Django Rest Framework Views
# ============================================================================


class GoogleOAuthLoginAPIView(APIView):
    """
    API View to initiate Google OAuth flow.

    Returns:
        JSON response with authorization URL and state

    Example Response:
        {
            "authorization_url": "https://accounts.google.com/o/oauth2/auth?...",
            "state": "random-state-string"
        }
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [GoogleOAuthLoginThrottle]

    def get(self, request: Request) -> Response:
        """Handle GET request to start OAuth flow."""
        try:
            # Build the full redirect URI
            redirect_uri = request.build_absolute_uri(
                reverse("django_googler_api:google-callback-api")
            )

            # Get custom scopes from query params if provided
            scopes = request.query_params.get("scopes")
            if scopes:
                scopes = scopes.split(",")
            else:
                scopes = None

            # Create the OAuth flow
            flow = get_google_auth_flow(redirect_uri=[redirect_uri], scopes=scopes)

            # Generate authorization URL
            authorization_url, state = get_google_auth_url(flow)

            # Store state in session for CSRF protection
            OAuthFlowService.store_state(request, state)

            # Validate and return using serializer
            serializer = GoogleOAuthLoginResponseSerializer(
                data={
                    "authorization_url": authorization_url,
                    "state": state,
                }
            )
            serializer.is_valid(raise_exception=True)

            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error initiating OAuth flow: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to initiate OAuth flow", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GoogleOAuthCallbackAPIView(APIView):
    """
    API View to handle Google OAuth callback via POST.

    This endpoint receives the authorization code from the client,
    exchanges it for Google tokens, creates/authenticates the user,
    and returns a DRF API token for subsequent authenticated requests.

    Request Body (POST):
        code: Authorization code from Google (required)
        state: State parameter for CSRF protection (required)
        redirect_uri: The redirect URI used in the OAuth flow (optional)

    Returns:
        JSON response with DRF token, user info, and Google tokens

    Example Request:
        POST /api/auth/google/callback/
        {
            "code": "4/0AY0e-g...",
            "state": "random-state-string",
            "redirect_uri": "http://localhost:3000/auth/callback"
        }

    Example Response:
        {
            "token": "drf_api_token_abc123...",
            "user": {
                "id": 1,
                "email": "user@example.com",
                "username": "user",
                "first_name": "John",
                "last_name": "Doe"
            },
            "google_tokens": {  # Only if GOOGLE_OAUTH_RETURN_TOKENS = True
                "access_token": "ya29...",
                "refresh_token": "1//...",
                "expires_in": "2024-10-18T12:00:00"
            }
        }

    Note:
        - The DRF token is always returned for backend authentication
        - Google tokens are only included if GOOGLE_OAUTH_RETURN_TOKENS = True
        - Set GOOGLE_OAUTH_RETURN_TOKENS = True if your frontend needs to
          call Google APIs directly (Calendar, Drive, Gmail, etc.)
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [GoogleOAuthCallbackThrottle]

    def post(self, request: Request) -> Response:
        """Handle POST request with OAuth callback data from client."""
        try:
            # Validate request data
            request_serializer = GoogleOAuthCallbackRequestSerializer(data=request.data)
            request_serializer.is_valid(raise_exception=True)

            code = request_serializer.validated_data["code"]
            state = request_serializer.validated_data["state"]
            redirect_uri = request_serializer.validated_data.get("redirect_uri")

            # Verify state for CSRF protection
            if not OAuthFlowService.verify_state(request, state):
                logger.warning("State mismatch in OAuth callback")
                return Response(
                    {
                        "error": "Invalid state parameter",
                        "detail": "CSRF verification failed",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Use provided redirect_uri or build default
            if not redirect_uri:
                redirect_uri = request.build_absolute_uri(
                    reverse("django_googler_api:google-callback-api")
                )

            # Create flow and fetch token
            flow = get_google_auth_flow(redirect_uri=[redirect_uri], state=state)

            # Exchange authorization code for tokens
            flow.fetch_token(code=code)

            # Get credentials and verify ID token
            credentials = flow.credentials
            id_info = GoogleOAuthService.verify_id_token(credentials)

            # Extract user information
            user_info = GoogleOAuthService.extract_user_info(id_info)

            if not user_info.get("email"):
                logger.error("No email provided by Google")
                return Response(
                    {"error": "No email provided by Google"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get or create user
            user = UserService.get_or_create_user(
                email=user_info["email"],
                name=user_info.get("name"),
                google_id=user_info.get("google_id"),
                picture=user_info.get("picture"),
                given_name=user_info.get("given_name"),
                family_name=user_info.get("family_name"),
            )

            # Generate or get API token for the user
            from rest_framework.authtoken.models import Token

            token, created = Token.objects.get_or_create(user=user)

            # Store OAuth tokens in session if configured
            GoogleOAuthService.store_tokens_in_session(request, credentials)

            # Clean up OAuth state
            OAuthFlowService.clear_state(request)

            # Build response
            response_data = {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
            }

            # Optionally include Google tokens if configured
            from django_googler.defaults import GOOGLE_OAUTH_RETURN_TOKENS

            if GOOGLE_OAUTH_RETURN_TOKENS:
                response_data["google_tokens"] = {
                    "access_token": credentials.token,
                    "expires_in": (
                        credentials.expiry.isoformat() if credentials.expiry else None
                    ),
                }
                # Include refresh token if available
                if credentials.refresh_token:
                    response_data["google_tokens"][
                        "refresh_token"
                    ] = credentials.refresh_token

            logger.info(f"User {user.email} authenticated via Google OAuth")

            # Validate and return response
            response_serializer = GoogleOAuthCallbackResponseSerializer(
                data=response_data
            )
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error processing OAuth callback: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to process OAuth callback", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentUserAPIView(APIView):
    """
    Get current authenticated user information.

    Returns user details for the authenticated user.
    Requires authentication via DRF Token.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Get current user info."""
        from django_googler.serializers import UserSerializer

        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GoogleOAuthLogoutAPIView(APIView):
    """
    Logout and clear authentication tokens.

    Deletes the user's DRF token and clears session data.
    Optionally can revoke Google OAuth access.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Handle logout request."""
        # Delete DRF token
        try:
            request.user.auth_token.delete()
        except AttributeError:
            pass  # User might not have a token

        # Clear OAuth session data
        request.session.pop("google_access_token", None)
        request.session.pop("google_refresh_token", None)
        request.session.pop("google_token_expiry", None)
        request.session.pop("oauth_state", None)
        request.session.pop("oauth_next", None)

        logger.info(f"User {request.user.email} logged out")

        return Response(
            {"message": "Logged out successfully"}, status=status.HTTP_200_OK
        )


# ============================================================================
# Regular Django Views
# ============================================================================


class GoogleOAuthLoginView(View):
    """
    Regular Django view to initiate Google OAuth flow.

    Redirects the user to Google's OAuth consent screen.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle GET request to start OAuth flow."""
        try:
            # Build the full redirect URI
            redirect_uri = request.build_absolute_uri(
                reverse("django_googler:google-callback")
            )

            # Get custom scopes from query params if provided
            scopes = request.GET.get("scopes")
            if scopes:
                scopes = scopes.split(",")
            else:
                scopes = None

            # Store the next URL if provided
            next_url = request.GET.get("next", "/")
            OAuthFlowService.store_next_url(request, next_url)

            # Create the OAuth flow
            flow = get_google_auth_flow(redirect_uri=[redirect_uri], scopes=scopes)

            # Generate authorization URL
            authorization_url, state = get_google_auth_url(flow)

            # Store state in session for CSRF protection
            OAuthFlowService.store_state(request, state)

            # Redirect to Google's OAuth page
            return redirect(authorization_url)

        except Exception as e:
            logger.error(f"Error initiating OAuth flow: {str(e)}", exc_info=True)
            # Redirect to login with error message
            error_params = urlencode({"error": "oauth_init_failed"})
            login_url = getattr(settings, "LOGIN_URL", "/login/")
            return redirect(f"{login_url}?{error_params}")


class GoogleOAuthCallbackView(View):
    """
    Regular Django view to handle Google OAuth callback.

    Processes the OAuth callback, creates/authenticates the user,
    and logs them into Django.
    """

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

            # Verify state for CSRF protection
            state = request.GET.get("state")
            if not OAuthFlowService.verify_state(request, state):
                logger.warning("State mismatch in OAuth callback")
                return self._redirect_with_error("invalid_state")

            # Build the full redirect URI (must match the one used in login)
            redirect_uri = request.build_absolute_uri(
                reverse("django_googler:google-callback")
            )

            # Create flow and fetch token
            flow = get_google_auth_flow(redirect_uri=[redirect_uri], state=state)

            # Exchange authorization code for tokens
            flow.fetch_token(code=code)

            # Get credentials and verify ID token
            credentials = flow.credentials
            id_info = GoogleOAuthService.verify_id_token(credentials)

            # Extract user information
            user_info = GoogleOAuthService.extract_user_info(id_info)

            if not user_info.get("email"):
                logger.error("No email provided by Google")
                return self._redirect_with_error("no_email")

            # Get or create user
            user = UserService.get_or_create_user(
                email=user_info["email"],
                name=user_info.get("name"),
                google_id=user_info.get("google_id"),
                picture=user_info.get("picture"),
                given_name=user_info.get("given_name"),
                family_name=user_info.get("family_name"),
            )

            # Store OAuth tokens in session if configured
            GoogleOAuthService.store_tokens_in_session(request, credentials)

            # Log the user in
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")

            # Clean up session state
            OAuthFlowService.clear_state(request)

            # Redirect to next URL or default
            next_url = OAuthFlowService.get_next_url(request, default="/")
            return redirect(next_url)

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
