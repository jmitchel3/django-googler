"""
Custom Google OAuth views with signed state for cross-origin flows.

These views override django_googler's default behavior to use signed state tokens
instead of session-based state storage, which enables OAuth flows across different
domains (e.g., frontend on localhost:3000, backend on localhost:8000).
"""

import logging
from typing import Any

from google.oauth2.credentials import Credentials
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django_googler.mixins import TokenResponseMixin
from django_googler.platform_client import get_google_auth_flow
from django_googler.security import SignedStateOAuthMixin
from django_googler.serializers import GoogleOAuthCallbackRequestSerializer
from django_googler.services import GoogleOAuthService, UserService
from django_googler.throttling import (
    GoogleOAuthCallbackThrottle,
    GoogleOAuthLoginThrottle,
)

logger = logging.getLogger(__name__)


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


class GoogleOAuthLoginAPIView(SignedStateOAuthMixin, APIView):
    """
    API View to initiate Google OAuth flow with signed state.

    Returns the authorization URL and signed state that can be safely
    passed to the frontend without relying on session storage.

    Query Parameters:
        redirect_uri: Optional custom redirect URI
        scopes: Optional comma-separated list of additional OAuth scopes

    Returns:
        JSON response with authorization URL and signed state

    Example Response:
        {
            "authorization_url": "https://accounts.google.com/o/oauth2/auth?...",
            "state": "eyJhbGc...:original_state_value"
        }
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [GoogleOAuthLoginThrottle]

    def get_scopes(self, request: Request) -> list[str]:
        """Get custom scopes from request query parameters."""
        scopes = request.query_params.get("scopes")
        if scopes:
            return scopes.split(",")
        return None

    def get_include_granted_scopes(self) -> bool:
        """
        Whether to include previously granted scopes in the OAuth flow without stating
        the scopes again. Recommended when adding new scopes for a user.
        """
        return False

    def get_prompt_type(self) -> str:
        """
        Get the prompt type for the OAuth flow within Google.
        Optional values: None, "consent", "select_account"
        """
        return "select_account"

    def get_redirect_uri(self, request: Request) -> str | None:
        """
        Get the redirect URI for the OAuth flow which can
        be used to redirect to a frontend for handling the OAuth callback.
        """
        return request.query_params.get("redirect_uri")

    ALLOWED_PROMPT_TYPES = [None, "consent", "select_account"]

    def get(self, request: Request) -> Response:
        """Handle GET request to initiate OAuth flow."""
        try:
            # Get custom redirect URI if provided
            redirect_uri = self.get_redirect_uri(request)
            # Build redirect URIs list
            redirect_uris = []
            if redirect_uri:
                redirect_uris.append(redirect_uri)

            scopes = self.get_scopes(request)

            _include_granted_scopes = self.get_include_granted_scopes()
            prompt_type = self.get_prompt_type()
            if prompt_type not in self.ALLOWED_PROMPT_TYPES:
                prompt_type = "consent"
            auth_include_granted_scopes = "true"
            if isinstance(_include_granted_scopes, bool):
                auth_include_granted_scopes = (
                    "true" if _include_granted_scopes else "false"
                )
            # Create OAuth flow
            flow = get_google_auth_flow(
                redirect_uri=redirect_uris if redirect_uris else None, scopes=scopes
            )

            # Generate authorization URL and state
            authorization_url, state = flow.authorization_url(
                access_type="offline",
                prompt=prompt_type,
                include_granted_scopes=auth_include_granted_scopes,
            )

            # Sign the state for verification later, including scopes
            signed_state = self.sign_state(state, scopes=scopes)

            # Replace the state parameter in the URL with the signed state
            # so Google will redirect back with the signed state
            from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

            parsed_url = urlparse(authorization_url)
            query_params = parse_qs(parsed_url.query)
            query_params["state"] = [signed_state]  # Replace with signed state
            new_query = urlencode(query_params, doseq=True)
            authorization_url = urlunparse(
                (
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    new_query,
                    parsed_url.fragment,
                )
            )

            logger.info("OAuth flow initiated successfully")

            return Response(
                {
                    "authorization_url": authorization_url,
                    "state": signed_state,
                }
            )

        except Exception as e:
            logger.error(f"Error initiating OAuth flow: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to initiate OAuth flow", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GoogleOAuthCallbackAPIView(SignedStateOAuthMixin, TokenResponseMixin, APIView):
    """
    API View to handle Google OAuth callback with signed state verification.

    This endpoint receives the authorization code and signed state from the client,
    verifies the signature, exchanges it for Google tokens, creates/authenticates
    the user, and returns JWT tokens.

    Request Body (POST):
        code: Authorization code from Google (required)
        state: Signed state parameter from login endpoint (required)
        redirect_uri: The redirect URI used in the OAuth flow (optional)

    Returns:
        JSON response with JWT tokens, user info, and optionally Google tokens

    Example Request:
        POST /api/auth/google/callback/
        {
            "code": "4/0AY0e-g...",
            "state": "eyJhbGc...:original_state_value",
            "redirect_uri": "http://localhost:3000/auth/google/callback"
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
            }
        }
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [GoogleOAuthCallbackThrottle]

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
            signed_state = request_serializer.validated_data["state"]
            redirect_uri = request_serializer.validated_data.get("redirect_uri")

            # Verify the signed state and extract metadata (scopes, etc.)
            is_valid, original_state, metadata = self.verify_signed_state(signed_state)
            if not is_valid:
                logger.warning("Invalid signed state in OAuth callback")
                return Response(
                    {"error": "Invalid or expired state parameter"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Extract scopes from metadata if present
            scopes = metadata.get("scopes") if metadata else None

            # Process the OAuth callback
            user, user_info, credentials, user_created = self.process_oauth_callback(
                code, original_state, redirect_uri, scopes
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
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
            }

            # Optionally include Google tokens if configured
            if self.should_return_google_tokens():
                response_data["google_tokens"] = self.build_google_tokens_response(
                    credentials
                )

            response_status = (
                status.HTTP_201_CREATED if user_created else status.HTTP_200_OK
            )

            logger.info(f"OAuth callback processed successfully for user: {user.email}")

            return Response(response_data, status=response_status)

        except ValueError as e:
            # Handle validation errors (state mismatch, missing email, etc.)
            logger.warning(f"Validation error in OAuth callback: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            # Handle any other errors
            logger.error(f"Error in OAuth callback: {str(e)}", exc_info=True)
            return Response(
                {"error": "Authentication failed", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def process_oauth_callback(
        self,
        code: str,
        state: str,
        redirect_uri: str | None = None,
        scopes: list[str] | None = None,
    ) -> tuple[Any, dict[str, Any], Credentials, bool]:
        """
        Process the complete OAuth callback flow without session dependency.

        Args:
            code: Authorization code from Google
            state: Original (unsigned) state parameter
            redirect_uri: Optional pre-built redirect URI
            scopes: Optional list of OAuth scopes used in the original request

        Returns:
            tuple: (user, user_info, credentials, user_created)

        Raises:
            ValueError: If email is missing
            Exception: If any step in the OAuth process fails
        """
        # Build redirect URIs list
        redirect_uris = []
        if redirect_uri:
            redirect_uris.append(redirect_uri)

        # Exchange code for credentials
        credentials = self.exchange_code_for_credentials(
            code, redirect_uris if redirect_uris else None, state, scopes
        )

        # Extract user information
        user_info = self.extract_user_data(credentials)

        # Create or get user
        user, user_created = self.create_or_get_user(user_info)

        # Save tokens to database if configured
        from django_googler.defaults import GOOGLE_OAUTH_SAVE_TOKENS_TO_DB

        if GOOGLE_OAUTH_SAVE_TOKENS_TO_DB:
            GoogleOAuthService.save_user_token(
                user=user,
                credentials=credentials,
                google_id=user_info.get("google_id"),
                scopes=(
                    list(credentials.scopes) if hasattr(credentials, "scopes") else None
                ),
            )

        logger.info(f"User {user.email} authenticated via Google OAuth")

        return user, user_info, credentials, user_created

    def exchange_code_for_credentials(
        self,
        code: str,
        redirect_uris: list[str] | None,
        state: str,
        scopes: list[str] | None = None,
    ) -> Credentials:
        """
        Exchange authorization code for Google credentials.

        Args:
            code: Authorization code from Google
            redirect_uris: List of redirect URIs used in OAuth flow
            state: State parameter for flow recreation
            scopes: Optional list of OAuth scopes used in the original request

        Returns:
            Credentials: Google OAuth credentials

        Raises:
            Exception: If token exchange fails
        """
        # Create flow with same parameters as login (including scopes)
        flow = get_google_auth_flow(
            redirect_uri=redirect_uris, state=state, scopes=scopes
        )

        # Exchange authorization code for tokens
        flow.fetch_token(code=code)

        return flow.credentials

    def extract_user_data(self, credentials: Credentials) -> dict[str, Any]:
        """
        Extract user information from credentials.

        Args:
            credentials: Google OAuth credentials

        Returns:
            dict: User information extracted from ID token
        """
        # Verify ID token and extract user info
        id_info = GoogleOAuthService.verify_id_token(credentials)
        user_info = GoogleOAuthService.extract_user_info(id_info)
        return user_info

    def create_or_get_user(self, user_info: dict[str, Any]) -> tuple[Any, bool]:
        """
        Create or retrieve user based on Google account information.

        Args:
            user_info: Dictionary with user information from Google

        Returns:
            tuple: (User instance, created boolean)

        Raises:
            ValueError: If email is missing from user_info
        """
        email = user_info.get("email")
        if not email:
            raise ValueError("No email provided by Google")

        return UserService.get_or_create_user(
            email=email,
            name=user_info.get("name"),
            google_id=user_info.get("google_id"),
            picture=user_info.get("picture"),
            given_name=user_info.get("given_name"),
            family_name=user_info.get("family_name"),
        )


class GoogleOAuthLogoutAPIView(APIView):
    """
    Logout and clear authentication tokens.

    Blacklists the user's JWT refresh token and optionally revokes Google OAuth access.

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
