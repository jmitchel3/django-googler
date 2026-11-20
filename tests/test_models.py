"""
Tests for django_googler models.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from django_googler.models import GoogleOAuthToken, get_user_identifier

User = get_user_model()


class TestGetUserIdentifier:
    """Test safe user identifier resolution across custom user models."""

    def test_prefers_email(self):
        user = SimpleNamespace(email="alice@example.com", get_username=lambda: "alice")
        assert get_user_identifier(user) == "alice@example.com"

    def test_falls_back_to_get_username(self):
        user = SimpleNamespace(email="", get_username=lambda: "alice")
        assert get_user_identifier(user) == "alice"

    def test_falls_back_to_str(self):
        class MinimalUser:
            def __str__(self):
                return "minimal-user-42"

        assert get_user_identifier(MinimalUser()) == "minimal-user-42"


@pytest.mark.django_db
class TestGoogleOAuthTokenModel:
    """Test GoogleOAuthToken model methods and properties."""

    def test_str_representation(self):
        user = User.objects.create_user(username="alice", email="alice@example.com")
        token = GoogleOAuthToken.objects.create(user=user, access_token="abc")
        assert str(token) == "Google OAuth Token for alice@example.com"

    def test_is_expired_and_leeway(self):
        user = User.objects.create_user(username="bob", email="bob@example.com")
        token = GoogleOAuthToken.objects.create(
            user=user,
            access_token="abc",
            token_expiry=None,
        )
        assert token.is_expired() is True
        assert token.is_valid is False

        # Expires in 30 seconds
        token.token_expiry = timezone.now() + timedelta(seconds=30)
        token.save()
        assert token.is_expired() is False
        assert token.is_expired(leeway=60) is True
        assert token.is_valid is True

        # Expired 10 seconds ago
        token.token_expiry = timezone.now() - timedelta(seconds=10)
        token.save()
        assert token.is_expired() is True
        assert token.is_valid is False

    def test_scopes_helpers(self):
        user = User.objects.create_user(username="carol", email="carol@example.com")
        token = GoogleOAuthToken.objects.create(user=user, access_token="abc")

        assert token.get_scopes_list() == []
        assert token.has_scope("email") is False

        token.set_scopes_list([" openid ", "email", "email", "", "profile"])
        assert token.scopes == "openid,email,profile"
        assert token.get_scopes_list() == ["openid", "email", "profile"]
        assert token.has_scope("email") is True
        assert token.has_scope("calendar") is False

    def test_can_refresh_property(self):
        user = User.objects.create_user(username="dave", email="dave@example.com")
        token = GoogleOAuthToken.objects.create(user=user, access_token="abc")
        assert token.can_refresh is False

        token.refresh_token = "refresh-123"
        assert token.can_refresh is True

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID="my-client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="my-client-secret",
        GOOGLE_OAUTH_TOKEN_URI="https://oauth2.googleapis.com/token",
    )
    def test_to_credentials(self):
        user = User.objects.create_user(username="eve", email="eve@example.com")
        expiry = timezone.now() + timedelta(hours=1)
        token = GoogleOAuthToken.objects.create(
            user=user,
            access_token="access-xyz",
            refresh_token="refresh-xyz",
            id_token="id-token-xyz",
            token_expiry=expiry,
            scopes="openid,email",
        )

        creds = token.to_credentials()
        assert creds.token == "access-xyz"
        assert creds.refresh_token == "refresh-xyz"
        assert creds.id_token == "id-token-xyz"
        assert creds.client_id == "my-client-id"
        assert creds.client_secret == "my-client-secret"
        assert creds.scopes == ["openid", "email"]
        # google-auth expects naive UTC expiry so creds.expired works without TypeError
        assert creds.expiry is not None
        assert creds.expiry.tzinfo is None
        assert creds.expired is False
