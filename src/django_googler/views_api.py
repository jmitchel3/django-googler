"""
Django REST Framework Google OAuth views with signed state for cross-origin flows.

These views use cryptographically signed state tokens instead of session cookies,
enabling stateless OAuth flows across separate frontend and backend origins
(e.g., frontend on localhost:3000, backend on localhost:8000).
"""

import logging
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from django.conf import settings
from google.oauth2.credentials import Credentials
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django_googler.defaults import get_django_google_setting
from django_googler.mixins import TokenResponseMixin
from django_googler.models import get_user_identifier
from django_googler.platform_client import get_google_auth_flow
from django_googler.security import SignedStateOAuthMixin, validate_redirect_uri
from django_googler.serializers import (
    GoogleOAuthCallbackRequestSerializer,
    get_user_serializer_class,
)
from django_googler.services import GoogleOAuthService, UserService
from django_googler.signals import (
    google_oauth_failed,
    google_oauth_logout,
    google_oauth_success,
)
from django_googler.throttling import (
    GoogleOAuthCallbackThrottle,
    GoogleOAuthLoginThrottle,
)

logger = logging.getLogger(__name__)


class CurrentUserAPIView(APIView):
    """
    Get current authenticated user information.

    Returns serialized user details for the authenticated user.
    Respects ``GOOGLE_OAUTH_USER_SERIALIZER`` or subclass ``serializer_class``.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = None

    def get_serializer_class(self):
        """Return serializer class for the current user."""
        if self.serializer_class is not None:
            return self.serializer_class
        return get_user_serializer_class()

    def get(self, request: Request) -> Response:
        """Get current user info."""
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GoogleOAuthLoginBaseAPIView(SignedStateOAuthMixin, APIView):
    """
    API View to initiate Google OAuth flow with signed state.

    Returns the authorization URL and signed state that can be safely
    passed to the frontend without relying on session storage.

    Query Parameters:
        redirect_uri: Optional custom redirect URI
        scopes: Optional comma-separated list of OAuth scopes
        code_challenge: Optional PKCE S256 code challenge for client-side PKCE
        code_challenge_method: Optional PKCE method (only ``S256`` supported)
    """

    ALLOWED_PROMPT_TYPES = [None, "consent", "select_account"]

    def get_scopes(self, request: Request) -> list[str] | None:
        """Get custom scopes from request query parameters."""
        raw_scopes = request.query_params.get("scopes")
        if not raw_scopes:
            return None
        cleaned = [s.strip() for s in raw_scopes.split(",") if s.strip()]
        return cleaned or None

    def get_include_granted_scopes(self) -> bool:
        """Whether to include previously granted scopes in the OAuth flow."""
        return False

    def get_prompt_type(self) -> str | None:
        """
        Get the prompt type for Google's OAuth screen.

        Valid values: ``None``, ``"consent"``, ``"select_account"``.
        """
        return "select_account"

    def get_redirect_uri(self, request: Request) -> str | None:
        """Get the redirect URI for the OAuth flow."""
        return request.query_params.get("redirect_uri")

    def get_extra_metadata(self, request: Request) -> dict[str, Any] | None:
        """
        Optional hook for subclasses to embed custom metadata in the signed state.

        Metadata is returned on the ``google_oauth_success`` signal as
        ``extra_metadata``.
        """
        return None

    def get(self, request: Request) -> Response:
        """Handle GET request to initiate OAuth flow."""
        try:
            raw_redirect_uri = self.get_redirect_uri(request)
            try:
                redirect_uri = validate_redirect_uri(raw_redirect_uri)
            except ValueError as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            code_challenge = request.query_params.get("code_challenge")
            code_challenge_method = request.query_params.get(
                "code_challenge_method", "S256"
            )
            if code_challenge and code_challenge_method != "S256":
                return Response(
                    {
                        "error": "Unsupported code_challenge_method; only S256 is supported"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            redirect_uris = [redirect_uri] if redirect_uri else None
            scopes = self.get_scopes(request)
            extra_metadata = self.get_extra_metadata(request)

            include_granted = self.get_include_granted_scopes()
            prompt_type = self.get_prompt_type()
            if prompt_type not in self.ALLOWED_PROMPT_TYPES:
                prompt_type = "consent"

            auth_include_granted_scopes = "true" if include_granted else "false"

            flow = get_google_auth_flow(
                redirect_uri=redirect_uris,
                scopes=scopes,
            )

            auth_kwargs: dict[str, Any] = {
                "access_type": "offline",
                "include_granted_scopes": auth_include_granted_scopes,
            }
            if prompt_type is not None:
                auth_kwargs["prompt"] = prompt_type
            if code_challenge:
                auth_kwargs["code_challenge"] = code_challenge
                auth_kwargs["code_challenge_method"] = "S256"

            authorization_url, state = flow.authorization_url(**auth_kwargs)

            signed_state = self.sign_state(
                state,
                scopes=scopes,
                extra_metadata=extra_metadata,
                redirect_uri=redirect_uri,
            )

            parsed_url = urlparse(authorization_url)
            query_params = parse_qs(parsed_url.query)
            query_params["state"] = [signed_state]
            new_query = urlencode(query_params, doseq=True)
            authorization_url = urlunparse(parsed_url._replace(query=new_query))

            logger.info("OAuth flow initiated successfully")

            return Response(
                {
                    "authorization_url": authorization_url,
                    "state": signed_state,
                }
            )

        except Exception as e:
            logger.error("Error initiating OAuth flow: %s", e, exc_info=True)
            error_body: dict[str, Any] = {"error": "Failed to initiate OAuth flow"}
            if settings.DEBUG:
                error_body["detail"] = str(e)
            return Response(
                error_body,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GoogleOAuthLoginAPIView(GoogleOAuthLoginBaseAPIView):
    """Public throttled API endpoint to initiate Google OAuth."""

    permission_classes = []
    authentication_classes = []
    throttle_classes = [GoogleOAuthLoginThrottle]


class GoogleOAuthCallbackBaseAPIView(
    SignedStateOAuthMixin, TokenResponseMixin, APIView
):
    """
    Base API View to handle Google OAuth callbacks using signed state verification.
    """

    serializer_class = None

    def get_serializer_class(self):
        """Return serializer class used to serialize the authenticated user."""
        if self.serializer_class is not None:
            return self.serializer_class
        return get_user_serializer_class()

    def get(self, request: Request) -> Response:
        """Handle GET callback requests when explicitly enabled via settings."""
        if not get_django_google_setting("DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK"):
            return Response(
                {"error": "GET requests are not allowed on this endpoint"},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        return self._handle_callback(request, request.query_params)

    def post(self, request: Request) -> Response:
        """Handle POST request with OAuth callback data from client."""
        return self._handle_callback(request, request.data)

    def _handle_callback(self, request: Request, data: Any) -> Response:
        """Validate callback payload, exchange tokens, and issue JWTs."""
        try:
            request_serializer = GoogleOAuthCallbackRequestSerializer(data=data)
            request_serializer.is_valid(raise_exception=True)

            code = request_serializer.validated_data["code"]
            signed_state = request_serializer.validated_data["state"]
            request_redirect_uri = (
                request_serializer.validated_data.get("redirect_uri") or None
            )
            code_verifier = (
                request_serializer.validated_data.get("code_verifier") or None
            )

            is_valid, original_state, metadata = self.verify_signed_state(signed_state)
            if not is_valid:
                logger.warning("Invalid signed state in OAuth callback")
                google_oauth_failed.send(
                    sender=self.__class__,
                    error="invalid_state",
                    request=request,
                    exception=None,
                )
                return Response(
                    {"error": "Invalid or expired state parameter"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            metadata = metadata or {}
            scopes = metadata.get("scopes")
            extra_metadata = metadata.get("extra_metadata")
            state_redirect_uri = metadata.get("redirect_uri")

            if (
                request_redirect_uri
                and state_redirect_uri
                and request_redirect_uri != state_redirect_uri
            ):
                raise ValueError(
                    "redirect_uri does not match the initial OAuth request"
                )

            redirect_uri = validate_redirect_uri(
                request_redirect_uri or state_redirect_uri
            )

            user, _user_info, credentials, user_created = self.process_oauth_callback(
                code=code,
                state=original_state,
                redirect_uri=redirect_uri,
                scopes=scopes,
                extra_metadata=extra_metadata,
                code_verifier=code_verifier,
            )

            from rest_framework_simplejwt.tokens import RefreshToken

            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)

            user_serializer_cls = self.get_serializer_class()
            user_data = user_serializer_cls(user).data

            response_data: dict[str, Any] = {
                "access": access_token,
                "refresh": refresh_token,
                "user": user_data,
            }

            if self.should_return_google_tokens():
                response_data["google_tokens"] = self.build_google_tokens_response(
                    credentials
                )

            response_status = (
                status.HTTP_201_CREATED if user_created else status.HTTP_200_OK
            )

            logger.info(
                "OAuth callback processed successfully for user: %s",
                get_user_identifier(user),
            )

            return Response(response_data, status=response_status)

        except ValidationError:
            raise
        except ValueError as e:
            logger.warning("Validation error in OAuth callback: %s", e)
            google_oauth_failed.send(
                sender=self.__class__,
                error=str(e),
                request=request,
                exception=e,
            )
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error("Error in OAuth callback: %s", e, exc_info=True)
            google_oauth_failed.send(
                sender=self.__class__,
                error="authentication_failed",
                request=request,
                exception=e,
            )
            error_body: dict[str, Any] = {"error": "Authentication failed"}
            if settings.DEBUG:
                error_body["detail"] = str(e)
            return Response(
                error_body,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def process_oauth_callback(
        self,
        code: str,
        state: str,
        redirect_uri: str | None = None,
        scopes: list[str] | None = None,
        extra_metadata: dict[str, Any] | None = None,
        code_verifier: str | None = None,
    ) -> tuple[Any, dict[str, Any], Credentials, bool]:
        """
        Process the complete stateless OAuth callback flow.

        Args:
            code: Authorization code from Google
            state: Original (unsigned) state parameter
            redirect_uri: Optional redirect URI used in OAuth flow
            scopes: Optional list of OAuth scopes used in original request
            extra_metadata: Optional custom metadata extracted from signed state
            code_verifier: Optional PKCE code verifier

        Returns:
            Tuple of ``(user, user_info, credentials, user_created)``
        """
        redirect_uris = [redirect_uri] if redirect_uri else None

        exchange_kwargs: dict[str, Any] = {}
        if code_verifier is not None:
            exchange_kwargs["code_verifier"] = code_verifier

        credentials = self.exchange_code_for_credentials(
            code, redirect_uris, state, scopes, **exchange_kwargs
        )

        user_info = self.extract_user_data(credentials)
        user, user_created = self.create_or_get_user(user_info)

        if get_django_google_setting("GOOGLE_OAUTH_SAVE_TOKENS_TO_DB"):
            GoogleOAuthService.save_user_token(
                user=user,
                credentials=credentials,
                google_id=user_info.get("google_id"),
                scopes=(
                    list(credentials.scopes)
                    if getattr(credentials, "scopes", None)
                    else None
                ),
            )

        logger.info("User %s authenticated via Google OAuth", get_user_identifier(user))

        granted_scopes = (
            list(credentials.scopes)
            if getattr(credentials, "scopes", None)
            else scopes or []
        )
        google_oauth_success.send(
            sender=self.__class__,
            user=user,
            scopes=granted_scopes,
            credentials=credentials,
            user_created=user_created,
            user_info=user_info,
            extra_metadata=extra_metadata,
        )

        return user, user_info, credentials, user_created

    def exchange_code_for_credentials(
        self,
        code: str,
        redirect_uris: list[str] | None,
        state: str,
        scopes: list[str] | None = None,
        code_verifier: str | None = None,
    ) -> Credentials:
        """Exchange authorization code for Google credentials."""
        flow = get_google_auth_flow(
            redirect_uri=redirect_uris,
            state=state,
            scopes=scopes,
            code_verifier=code_verifier,
        )
        flow.fetch_token(code=code)
        return flow.credentials

    def extract_user_data(self, credentials: Credentials) -> dict[str, Any]:
        """Verify ID token and extract standardized user information."""
        id_info = GoogleOAuthService.verify_id_token(credentials)
        return GoogleOAuthService.extract_user_info(id_info)

    def create_or_get_user(self, user_info: dict[str, Any]) -> tuple[Any, bool]:
        """Create or retrieve user based on Google account information."""
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
            email_verified=user_info.get("email_verified"),
        )


class GoogleOAuthCallbackAPIView(GoogleOAuthCallbackBaseAPIView):
    """Public throttled API endpoint to handle Google OAuth callbacks."""

    permission_classes = []
    authentication_classes = []
    throttle_classes = [GoogleOAuthCallbackThrottle]


class GoogleOAuthLogoutAPIView(APIView):
    """
    Logout and clear authentication tokens.

    Blacklists the user's JWT refresh token (when token_blacklist is installed)
    and optionally revokes Google OAuth access when
    ``GOOGLE_OAUTH_REVOKE_ON_LOGOUT=True``.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Handle logout request."""
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                from rest_framework_simplejwt.tokens import RefreshToken

                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as e:
                logger.warning("Failed to blacklist token: %s", e)

        if get_django_google_setting("GOOGLE_OAUTH_REVOKE_ON_LOGOUT"):
            try:
                GoogleOAuthService.revoke_user_token(request.user)
            except Exception as e:
                logger.warning("Failed to revoke token on logout: %s", e)

        google_oauth_logout.send(
            sender=self.__class__,
            user=request.user,
            request=request,
        )

        logger.info("User %s logged out", get_user_identifier(request.user))

        return Response(
            {"message": "Logged out successfully"}, status=status.HTTP_200_OK
        )
