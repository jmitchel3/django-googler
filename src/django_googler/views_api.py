import logging

from oauthlib.oauth2.rfc6749.errors import InvalidGrantError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django_googler.mixins import (
    OAuthCallbackProcessingMixin,
    OAuthFlowInitMixin,
    TokenResponseMixin,
)
from django_googler.serializers import (
    GoogleOAuthCallbackRequestSerializer,
    GoogleOAuthCallbackResponseSerializer,
    GoogleOAuthLoginResponseSerializer,
)
from django_googler.services import GoogleOAuthService
from django_googler.throttling import (
    GoogleOAuthCallbackThrottle,
    GoogleOAuthLoginThrottle,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Django Rest Framework Views
# ============================================================================


class GoogleOAuthLoginAPIView(OAuthFlowInitMixin, APIView):
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

    def get_redirect_uri_name(self) -> str:
        """Get the URL name for the OAuth callback."""
        from django_googler.defaults import GOOGLE_OAUTH_CALLBACK_REDIRECT_URI_NAME

        return GOOGLE_OAUTH_CALLBACK_REDIRECT_URI_NAME

    def get(self, request: Request) -> Response:
        """Handle GET request to start OAuth flow."""
        try:
            # Initialize OAuth flow using mixin
            redirect_uri = request.GET.get("redirect_uri") or self.build_redirect_uri(
                request
            )
            authorization_url, state = self.init_oauth_flow(request, redirect_uri)

            # Validate and return using serializer
            serializer = GoogleOAuthLoginResponseSerializer(
                data={
                    "authorization_url": authorization_url,
                    "state": state,
                    "redirect_uri": redirect_uri,
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


class GoogleOAuthCallbackAPIView(
    OAuthCallbackProcessingMixin, TokenResponseMixin, APIView
):
    """
    API View to handle Google OAuth callback via POST.

    This endpoint receives the authorization code from the client,
    exchanges it for Google tokens, creates/authenticates the user,
    and returns JWT tokens for subsequent authenticated requests.

    Request Body (POST):
        code: Authorization code from Google (required)
        state: State parameter for CSRF protection (required)
        redirect_uri: The redirect URI used in the OAuth flow (optional)

    Returns:
        JSON response with JWT tokens, user info, and Google tokens

    Example Request:
        POST /api/auth/google/callback/
        {
            "code": "4/0AY0e-g...",
            "state": "random-state-string",
            "redirect_uri": "http://localhost:3000/auth/callback"
        }

    Example Response:
        {
            "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
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
        - JWT access and refresh tokens are always returned for backend authentication
        - Use the access token in Authorization header: "Bearer <access_token>"
        - Use the refresh token to get a new access token when it expires
        - Google tokens are only included if GOOGLE_OAUTH_RETURN_TOKENS = True
        - Set GOOGLE_OAUTH_RETURN_TOKENS = True if your frontend needs to
          call Google APIs directly (Calendar, Drive, Gmail, etc.)
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [GoogleOAuthCallbackThrottle]

    def get_redirect_uri_name(self) -> str:
        """Get the URL name for the OAuth callback."""
        from django_googler.defaults import GOOGLE_OAUTH_CALLBACK_REDIRECT_URI_NAME

        return GOOGLE_OAUTH_CALLBACK_REDIRECT_URI_NAME

    def get(self, request: Request) -> Response:
        """Handle GET request with OAuth callback data from client."""
        from django_googler.defaults import DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK

        if not DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK:
            return Response(
                {"error": "GET requests are not allowed on this endpoint"},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )

        data = request.query_params
        return self.post(request, data=data)

    def post(self, request: Request, data: dict = None) -> Response:
        """Handle POST request with OAuth callback data from client."""
        try:
            # Validate request data
            request_serializer = GoogleOAuthCallbackRequestSerializer(
                data=request.data or data
            )
            request_serializer.is_valid(raise_exception=True)

            code = request_serializer.validated_data["code"]
            state = request_serializer.validated_data["state"]
            redirect_uri = request_serializer.validated_data.get("redirect_uri")

            # Process OAuth callback using mixin
            user, user_info, credentials, user_created = self.process_oauth_callback(
                request, code, state, redirect_uri
            )

            # Generate JWT tokens for the user
            from rest_framework_simplejwt.tokens import RefreshToken

            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)

            # Build response
            response_data = {
                "access": access_token,
                "refresh": refresh_token,
                "user": user,
            }

            # Optionally include Google tokens if configured
            if self.should_return_google_tokens():
                response_data["google_tokens"] = self.build_google_tokens_response(
                    credentials
                )

            response_status = (
                status.HTTP_200_OK if user_created else status.HTTP_201_CREATED
            )
            # Return response
            response_serializer = GoogleOAuthCallbackResponseSerializer(response_data)
            return Response(response_serializer.data, status=response_status)

        except ValueError as e:
            # Handle validation errors (state mismatch, missing email, etc.)
            logger.warning(f"Validation error in OAuth callback: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InvalidGrantError as e:
            logger.error(
                f"Invalid grant error in OAuth callback: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Invalid grant error", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
    Requires authentication via JWT Bearer token.

    Example:
        GET /api/auth/me/
        Headers: Authorization: Bearer <access_token>
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

    Blacklists the user's JWT refresh token and clears session data.
    Optionally can revoke Google OAuth access.

    Request Body:
        refresh: The refresh token to blacklist (required)

    Example:
        POST /api/auth/logout/
        {
            "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
        }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Handle logout request."""
        try:
            # Blacklist the refresh token
            from rest_framework_simplejwt.tokens import RefreshToken

            refresh_token = request.data.get("refresh")
            if refresh_token:
                try:
                    token = RefreshToken(refresh_token)
                    token.blacklist()
                except Exception as e:
                    logger.warning(f"Failed to blacklist token: {str(e)}")
        except Exception as e:
            logger.warning(f"Error processing token blacklist: {str(e)}")

        # Clear OAuth session data
        request.session.pop("google_access_token", None)
        request.session.pop("google_refresh_token", None)
        request.session.pop("google_token_expiry", None)
        request.session.pop("oauth_state", None)
        request.session.pop("oauth_next", None)

        # Optionally revoke Google OAuth token
        from django_googler.defaults import GOOGLE_OAUTH_REVOKE_ON_LOGOUT

        if GOOGLE_OAUTH_REVOKE_ON_LOGOUT:
            try:
                GoogleOAuthService.revoke_user_token(request.user)
            except Exception as e:
                logger.warning(f"Failed to revoke token on logout: {str(e)}")

        logger.info(f"User {request.user.email} logged out")

        return Response(
            {"message": "Logged out successfully"}, status=status.HTTP_200_OK
        )
