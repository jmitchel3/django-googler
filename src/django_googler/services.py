"""
Service layer for django_googler OAuth operations.

This module contains the business logic for handling Google OAuth authentication,
token processing, and user management.
"""

import logging
from typing import Any, Optional

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


class GoogleOAuthService:
    """Service class for handling Google OAuth operations."""

    @staticmethod
    def process_credentials(credentials) -> dict[str, Any]:
        """
        Process Google OAuth credentials and extract user information.

        Args:
            credentials: Google OAuth credentials object

        Returns:
            Dictionary containing tokens and user info

        Raises:
            Exception: If token verification fails
        """
        import google.auth.transport.requests
        from google.oauth2 import id_token

        # Verify and decode the ID token
        request_adapter = google.auth.transport.requests.Request()
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, request_adapter, credentials.client_id
        )

        # Build response data
        response_data = {
            "access_token": credentials.token,
            "token_type": "Bearer",
            "expires_in": (
                credentials.expiry.isoformat() if credentials.expiry else None
            ),
            "id_token": credentials.id_token,
            "user_info": {
                "email": id_info.get("email"),
                "name": id_info.get("name"),
                "picture": id_info.get("picture"),
                "email_verified": id_info.get("email_verified", False),
                "sub": id_info.get("sub"),  # Google's unique user ID
                "given_name": id_info.get("given_name"),
                "family_name": id_info.get("family_name"),
            },
        }

        # Include refresh token if available
        if credentials.refresh_token:
            response_data["refresh_token"] = credentials.refresh_token

        return response_data

    @staticmethod
    def extract_user_info(id_info: dict[str, Any]) -> dict[str, str]:
        """
        Extract user information from ID token info.

        Args:
            id_info: Decoded ID token information

        Returns:
            Dictionary with standardized user fields
        """
        return {
            "email": id_info.get("email", ""),
            "name": id_info.get("name", ""),
            "given_name": id_info.get("given_name", ""),
            "family_name": id_info.get("family_name", ""),
            "picture": id_info.get("picture", ""),
            "google_id": id_info.get("sub", ""),
        }

    @staticmethod
    def verify_id_token(credentials) -> dict[str, Any]:
        """
        Verify and decode Google ID token.

        Args:
            credentials: Google OAuth credentials object

        Returns:
            Decoded ID token information
        """
        import google.auth.transport.requests
        from google.oauth2 import id_token

        request_adapter = google.auth.transport.requests.Request()
        return id_token.verify_oauth2_token(
            credentials.id_token, request_adapter, credentials.client_id
        )

    @staticmethod
    def store_tokens_in_session(request, credentials) -> None:
        """
        Store OAuth tokens in session if configured to do so.

        Args:
            request: Django request object
            credentials: Google OAuth credentials object
        """
        if getattr(settings, "GOOGLE_OAUTH_STORE_TOKENS", False):
            request.session["google_access_token"] = credentials.token
            if credentials.refresh_token:
                request.session["google_refresh_token"] = credentials.refresh_token
            if credentials.expiry:
                request.session["google_token_expiry"] = credentials.expiry.isoformat()


class UserService:
    """Service class for user management operations."""

    @staticmethod
    def get_or_create_user(
        email: str,
        name: Optional[str] = None,
        google_id: Optional[str] = None,
        picture: Optional[str] = None,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
    ):
        """
        Get or create a user from Google OAuth information.

        Args:
            email: User's email address (required)
            name: User's full name
            google_id: Google's unique user ID (sub claim)
            picture: URL to user's profile picture
            given_name: User's first name from Google
            family_name: User's last name from Google

        Returns:
            User instance

        Raises:
            ValueError: If email is not provided
        """
        User = get_user_model()

        if not email:
            raise ValueError("Email is required to get or create user")

        # Try to find user by email
        try:
            user = User.objects.get(email=email)
            logger.info(f"Found existing user: {email}")

            # Update user info if needed
            updated = UserService._update_user_info(user, name, given_name, family_name)

            if updated:
                user.save()
                logger.info(f"Updated user info for: {email}")

            return user

        except User.DoesNotExist:
            # Create new user
            logger.info(f"Creating new user: {email}")
            return UserService._create_new_user(
                email, name, given_name, family_name, google_id, picture
            )

    @staticmethod
    def _update_user_info(
        user,
        name: Optional[str] = None,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
    ) -> bool:
        """
        Update user information if fields are missing.

        Args:
            user: User instance to update
            name: Full name to parse if given_name/family_name not provided
            given_name: First name
            family_name: Last name

        Returns:
            True if user was updated, False otherwise
        """
        updated = False

        # Update first name if missing
        if not user.first_name:
            if given_name:
                user.first_name = given_name
                updated = True
            elif name:
                name_parts = name.split(maxsplit=1)
                user.first_name = name_parts[0]
                updated = True

        # Update last name if missing
        if not user.last_name:
            if family_name:
                user.last_name = family_name
                updated = True
            elif name:
                name_parts = name.split(maxsplit=1)
                if len(name_parts) > 1:
                    user.last_name = name_parts[1]
                    updated = True

        return updated

    @staticmethod
    def _create_new_user(
        email: str,
        name: Optional[str] = None,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
        google_id: Optional[str] = None,
        picture: Optional[str] = None,
    ):
        """
        Create a new user from OAuth information.

        Args:
            email: User's email address
            name: Full name (used if given_name/family_name not provided)
            given_name: First name
            family_name: Last name
            google_id: Google's unique user ID
            picture: URL to user's profile picture

        Returns:
            Newly created User instance
        """
        User = get_user_model()

        # Determine first and last names
        if given_name and family_name:
            first_name = given_name
            last_name = family_name
        elif name:
            name_parts = name.split(maxsplit=1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
        else:
            first_name = ""
            last_name = ""

        # Generate unique username from email
        username = UserService._generate_unique_username(email)

        # Create the user
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )

        logger.info(f"Created new user: {email} (username: {username})")

        # Note: If you want to store google_id and picture, you should:
        # 1. Create a custom user model with these fields, or
        # 2. Create a separate UserProfile model related to User
        # Example:
        # if hasattr(user, 'profile'):
        #     user.profile.google_id = google_id
        #     user.profile.picture = picture
        #     user.profile.save()

        return user

    @staticmethod
    def _generate_unique_username(email: str) -> str:
        """
        Generate a unique username from an email address.

        Args:
            email: User's email address

        Returns:
            Unique username string
        """
        User = get_user_model()

        # Extract base username from email
        base_username = email.split("@")[0]

        # Clean up username (remove special characters if needed)
        username = base_username

        # Ensure username is unique
        if not User.objects.filter(username=username).exists():
            return username

        # Add numeric suffix if username exists
        counter = 1
        while User.objects.filter(username=f"{base_username}{counter}").exists():
            counter += 1

        return f"{base_username}{counter}"


class OAuthFlowService:
    """Service class for managing OAuth flow state and validation."""

    @staticmethod
    def store_state(request, state: str) -> None:
        """
        Store OAuth state in session for CSRF protection.

        Args:
            request: Django request object
            state: OAuth state string
        """
        request.session["oauth_state"] = state

    @staticmethod
    def verify_state(request, state: Optional[str]) -> bool:
        """
        Verify OAuth state for CSRF protection.

        Args:
            request: Django request object
            state: State parameter from OAuth callback

        Returns:
            True if state is valid, False otherwise
        """
        session_state = request.session.get("oauth_state")
        return bool(state and session_state and state == session_state)

    @staticmethod
    def clear_state(request) -> None:
        """
        Clear OAuth state from session.

        Args:
            request: Django request object
        """
        if "oauth_state" in request.session:
            del request.session["oauth_state"]

    @staticmethod
    def store_next_url(request, next_url: str) -> None:
        """
        Store the next URL for redirect after OAuth.

        Args:
            request: Django request object
            next_url: URL to redirect to after successful OAuth
        """
        request.session["oauth_next"] = next_url

    @staticmethod
    def get_next_url(request, default: str = "/") -> str:
        """
        Get and clear the next URL from session.

        Args:
            request: Django request object
            default: Default URL if none stored

        Returns:
            Next URL string
        """
        return request.session.pop("oauth_next", default)
