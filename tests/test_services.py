"""
Tests for django_googler services.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from django_googler.services import GoogleOAuthService, OAuthFlowService, UserService

User = get_user_model()


@pytest.mark.django_db
class TestUserService:
    """Test UserService functionality."""

    def test_create_new_user(self):
        """Test creating a new user from OAuth info."""
        user = UserService.get_or_create_user(
            email="test@example.com",
            name="Test User",
            google_id="123456789",
            picture="https://example.com/photo.jpg",
        )

        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.username == "test"

    def test_create_user_with_given_family_names(self):
        """Test creating a user with given_name and family_name."""
        user = UserService.get_or_create_user(
            email="john@example.com",
            given_name="John",
            family_name="Doe",
        )

        assert user.first_name == "John"
        assert user.last_name == "Doe"

    def test_get_existing_user(self):
        """Test retrieving an existing user."""
        # Create user first
        User.objects.create_user(
            username="existing",
            email="existing@example.com",
            first_name="Existing",
        )

        # Try to get or create
        user = UserService.get_or_create_user(email="existing@example.com")

        assert user.email == "existing@example.com"
        assert user.first_name == "Existing"
        assert User.objects.filter(email="existing@example.com").count() == 1

    def test_update_existing_user_info(self):
        """Test updating existing user with new info."""
        # Create user without name
        User.objects.create_user(
            username="test",
            email="test@example.com",
        )

        # Update with OAuth info
        user = UserService.get_or_create_user(
            email="test@example.com", name="Test User"
        )

        assert user.first_name == "Test"
        assert user.last_name == "User"

    def test_generate_unique_username(self):
        """Test unique username generation."""
        # Create first user
        user1 = UserService.get_or_create_user(email="test@example.com")
        assert user1.username == "test"

        # Create second user with same email prefix
        user2 = UserService.get_or_create_user(email="test@different.com")
        assert user2.username == "test1"

        # Create third user
        user3 = UserService.get_or_create_user(email="test@another.com")
        assert user3.username == "test2"

    def test_create_user_without_email_raises_error(self):
        """Test that creating user without email raises error."""
        with pytest.raises(ValueError, match="Email is required"):
            UserService.get_or_create_user(email="")


class TestOAuthFlowService:
    """Test OAuthFlowService functionality."""

    def test_store_and_verify_state(self):
        """Test storing and verifying OAuth state."""
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        # Store state
        OAuthFlowService.store_state(request, "test-state-123")
        assert request.session["oauth_state"] == "test-state-123"

        # Verify valid state
        assert OAuthFlowService.verify_state(request, "test-state-123") is True

        # Verify invalid state
        assert OAuthFlowService.verify_state(request, "wrong-state") is False

    def test_verify_state_without_session_state(self):
        """Test verifying state when no state in session."""
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        assert OAuthFlowService.verify_state(request, "any-state") is False

    def test_clear_state(self):
        """Test clearing OAuth state from session."""
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {"oauth_state": "test-state"}

        OAuthFlowService.clear_state(request)
        assert "oauth_state" not in request.session

    def test_store_and_get_next_url(self):
        """Test storing and retrieving next URL."""
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        # Store next URL
        OAuthFlowService.store_next_url(request, "/dashboard/")
        assert request.session["oauth_next"] == "/dashboard/"

        # Get next URL (should remove from session)
        next_url = OAuthFlowService.get_next_url(request)
        assert next_url == "/dashboard/"
        assert "oauth_next" not in request.session

    def test_get_next_url_default(self):
        """Test getting next URL with default when none stored."""
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        next_url = OAuthFlowService.get_next_url(request, default="/home/")
        assert next_url == "/home/"


class TestGoogleOAuthService:
    """Test GoogleOAuthService functionality."""

    def test_extract_user_info(self):
        """Test extracting user info from ID token."""
        id_info = {
            "email": "test@example.com",
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "picture": "https://example.com/photo.jpg",
            "sub": "123456789",
        }

        user_info = GoogleOAuthService.extract_user_info(id_info)

        assert user_info["email"] == "test@example.com"
        assert user_info["name"] == "Test User"
        assert user_info["given_name"] == "Test"
        assert user_info["family_name"] == "User"
        assert user_info["picture"] == "https://example.com/photo.jpg"
        assert user_info["google_id"] == "123456789"

    def test_extract_user_info_with_missing_fields(self):
        """Test extracting user info when some fields are missing."""
        id_info = {"email": "test@example.com"}

        user_info = GoogleOAuthService.extract_user_info(id_info)

        assert user_info["email"] == "test@example.com"
        assert user_info["name"] == ""
        assert user_info["google_id"] == ""

    def test_store_tokens_in_session_when_enabled(self, settings):
        """Test storing tokens when GOOGLE_OAUTH_STORE_TOKENS is True."""
        settings.GOOGLE_OAUTH_STORE_TOKENS = True

        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        # Mock credentials
        class MockCredentials:
            token = "test-access-token"
            refresh_token = "test-refresh-token"
            expiry = None

        credentials = MockCredentials()

        GoogleOAuthService.store_tokens_in_session(request, credentials)

        assert request.session["google_access_token"] == "test-access-token"
        assert request.session["google_refresh_token"] == "test-refresh-token"

    def test_store_tokens_in_session_when_disabled(self, settings):
        """Test not storing tokens when GOOGLE_OAUTH_STORE_TOKENS is False."""
        settings.GOOGLE_OAUTH_STORE_TOKENS = False

        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        # Mock credentials
        class MockCredentials:
            token = "test-access-token"
            refresh_token = "test-refresh-token"
            expiry = None

        credentials = MockCredentials()

        GoogleOAuthService.store_tokens_in_session(request, credentials)

        assert "google_access_token" not in request.session
        assert "google_refresh_token" not in request.session
