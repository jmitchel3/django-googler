"""
Mixins for django_googler OAuth views.

This module provides reusable mixins that encapsulate common OAuth flow logic
to reduce code duplication between API and regular Django views.
"""

import logging
from typing import Any, Optional

from django.urls import reverse
from google.oauth2.credentials import Credentials

from django_googler.platform_client import get_google_auth_flow, get_google_auth_url
from django_googler.services import GoogleOAuthService, OAuthFlowService, UserService

logger = logging.getLogger(__name__)


class OAuthFlowInitMixin:
    """
    Mixin for initializing Google OAuth flow.

    Provides common logic for:
    - Building redirect URIs
    - Parsing custom scopes from request
    - Creating OAuth flows
    - Generating authorization URLs and state
    - Storing state in session
    """

    def get_redirect_uri_name(self) -> str:
        """
        Get the URL name for the OAuth callback.

        Must be overridden by subclasses to specify which callback URL to use.

        Returns:
            str: URL name for reverse()
        """
        raise NotImplementedError("Subclasses must implement get_redirect_uri_name()")

    def build_redirect_uri(self, request) -> str:
        """
        Build the full redirect URI for OAuth callback.

        Args:
            request: HTTP request object (Django or DRF)

        Returns:
            str: Full absolute redirect URI
        """
        callback_url_name = self.get_redirect_uri_name()
        return request.build_absolute_uri(reverse(callback_url_name))

    def parse_scopes(self, request) -> Optional[list[str]]:
        """
        Parse custom scopes from request query parameters.

        Args:
            request: HTTP request object (Django or DRF)

        Returns:
            list[str] or None: List of scope strings or None if not provided
        """
        # Handle both Django request (GET) and DRF request (query_params)
        query_params = getattr(request, "query_params", request.GET)
        scopes = query_params.get("scopes")

        if scopes:
            return scopes.split(",")
        return None

    def init_oauth_flow(self, request) -> tuple[str, str]:
        """
        Initialize OAuth flow and generate authorization URL.

        Args:
            request: HTTP request object (Django or DRF)

        Returns:
            tuple: (authorization_url, state)
        """
        # Build redirect URI
        redirect_uri = self.build_redirect_uri(request)

        # Parse custom scopes
        scopes = self.parse_scopes(request)

        # Create OAuth flow
        flow = get_google_auth_flow(redirect_uri=[redirect_uri], scopes=scopes)

        # Generate authorization URL and state
        authorization_url, state = get_google_auth_url(flow)

        # Store state in session for CSRF protection
        OAuthFlowService.store_state(request, state)

        return authorization_url, state


class OAuthCallbackProcessingMixin:
    """
    Mixin for processing Google OAuth callback.

    Provides common logic for:
    - Verifying state (CSRF protection)
    - Exchanging authorization code for tokens
    - Verifying ID token
    - Extracting user information
    - Creating/retrieving user
    - Storing tokens (session and database)
    """

    def get_redirect_uri_name(self) -> str:
        """
        Get the URL name for the OAuth callback.

        Must be overridden by subclasses to specify which callback URL to use.

        Returns:
            str: URL name for reverse()
        """
        raise NotImplementedError("Subclasses must implement get_redirect_uri_name()")

    def build_redirect_uri(self, request, redirect_uri: Optional[str] = None) -> str:
        """
        Build the full redirect URI for OAuth callback.

        Args:
            request: HTTP request object (Django or DRF)
            redirect_uri: Optional pre-built redirect URI to use

        Returns:
            str: Full absolute redirect URI
        """
        if redirect_uri:
            return redirect_uri

        callback_url_name = self.get_redirect_uri_name()
        return request.build_absolute_uri(reverse(callback_url_name))

    def verify_oauth_state(self, request, state: str) -> bool:
        """
        Verify OAuth state for CSRF protection.

        Args:
            request: HTTP request object (Django or DRF)
            state: State parameter from OAuth callback

        Returns:
            bool: True if state is valid, False otherwise
        """
        return OAuthFlowService.verify_state(request, state)

    def exchange_code_for_credentials(
        self, code: str, redirect_uri: str, state: str
    ) -> Credentials:
        """
        Exchange authorization code for Google credentials.

        Args:
            code: Authorization code from Google
            redirect_uri: Redirect URI used in OAuth flow
            state: State parameter for flow recreation

        Returns:
            Credentials: Google OAuth credentials

        Raises:
            Exception: If token exchange fails
        """
        # Create flow with same parameters as login
        flow = get_google_auth_flow(redirect_uri=[redirect_uri], state=state)

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

    def create_or_get_user(self, user_info: dict[str, Any]):
        """
        Create or retrieve user based on Google account information.

        Args:
            user_info: Dictionary with user information from Google

        Returns:
            User: Django user instance

        Raises:
            ValueError: If email is missing from user_info
        """
        email = user_info.get("email")
        if not email:
            raise ValueError("No email provided by Google")

        user = UserService.get_or_create_user(
            email=email,
            name=user_info.get("name"),
            google_id=user_info.get("google_id"),
            picture=user_info.get("picture"),
            given_name=user_info.get("given_name"),
            family_name=user_info.get("family_name"),
        )
        return user

    def store_user_tokens(
        self, request, user, credentials: Credentials, user_info: dict[str, Any]
    ) -> None:
        """
        Store OAuth tokens in session and optionally in database.

        Args:
            request: HTTP request object (Django or DRF)
            user: Django user instance
            credentials: Google OAuth credentials
            user_info: User information dictionary
        """
        # Store tokens in session
        GoogleOAuthService.store_tokens_in_session(request, credentials)

        # Optionally save tokens to database
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

    def cleanup_oauth_state(self, request) -> None:
        """
        Clean up OAuth state from session.

        Args:
            request: HTTP request object (Django or DRF)
        """
        OAuthFlowService.clear_state(request)

    def process_oauth_callback(
        self, request, code: str, state: str, redirect_uri: Optional[str] = None
    ) -> tuple[Any, dict[str, Any], Credentials]:
        """
        Process the complete OAuth callback flow.

        Args:
            request: HTTP request object (Django or DRF)
            code: Authorization code from Google
            state: State parameter for CSRF protection
            redirect_uri: Optional pre-built redirect URI

        Returns:
            tuple: (user, user_info, credentials)

        Raises:
            ValueError: If state verification fails or email is missing
            Exception: If any step in the OAuth process fails
        """
        # Verify state for CSRF protection
        if not self.verify_oauth_state(request, state):
            raise ValueError("Invalid state parameter - CSRF verification failed")

        # Build redirect URI
        final_redirect_uri = self.build_redirect_uri(request, redirect_uri)

        # Exchange code for credentials
        credentials = self.exchange_code_for_credentials(
            code, final_redirect_uri, state
        )

        # Extract user information
        user_info = self.extract_user_data(credentials)

        # Create or get user
        user = self.create_or_get_user(user_info)

        # Store tokens
        self.store_user_tokens(request, user, credentials, user_info)

        # Cleanup
        self.cleanup_oauth_state(request)

        logger.info(f"User {user.email} authenticated via Google OAuth")

        return user, user_info, credentials


class TokenResponseMixin:
    """
    Mixin for building token response data.

    Provides logic for:
    - Building response with optional Google tokens
    - Respecting GOOGLE_OAUTH_RETURN_TOKENS setting
    """

    def build_google_tokens_response(self, credentials: Credentials) -> dict[str, Any]:
        """
        Build Google tokens response data.

        Args:
            credentials: Google OAuth credentials

        Returns:
            dict: Google tokens data
        """
        tokens_data = {
            "access_token": credentials.token,
            "expires_in": (
                credentials.expiry.isoformat() if credentials.expiry else None
            ),
        }

        # Include refresh token if available
        if credentials.refresh_token:
            tokens_data["refresh_token"] = credentials.refresh_token

        return tokens_data

    def should_return_google_tokens(self) -> bool:
        """
        Check if Google tokens should be included in response.

        Returns:
            bool: True if tokens should be returned
        """
        from django_googler.defaults import GOOGLE_OAUTH_RETURN_TOKENS

        return GOOGLE_OAUTH_RETURN_TOKENS
