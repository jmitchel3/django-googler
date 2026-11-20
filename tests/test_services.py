"""
Tests for django_googler services.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from django.utils import timezone

from django_googler.models import GoogleOAuthToken
from django_googler.services import (
    GoogleOAuthService,
    OAuthFlowService,
    UserService,
    _make_aware,
)
from django_googler.signals import google_oauth_token_refreshed

User = get_user_model()


@pytest.mark.django_db
class TestUserService:
    """Test UserService functionality."""

    def test_create_new_user(self):
        """Test creating a new user from OAuth info."""
        user, created = UserService.get_or_create_user(
            email="test@example.com",
            name="Test User",
            google_id="123456789",
            picture="https://example.com/photo.jpg",
        )

        assert created is True
        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.username == "test"
        assert user.has_usable_password() is False

    def test_create_user_with_given_family_names(self):
        """Test creating a user with given_name and family_name."""
        user, _ = UserService.get_or_create_user(
            email="john@example.com",
            given_name="John",
            family_name="Doe",
        )

        assert user.first_name == "John"
        assert user.last_name == "Doe"

    def test_create_user_with_only_given_name(self):
        """Creating a user with only given_name (no family_name) preserves first_name."""
        user, _ = UserService.get_or_create_user(
            email="madonna@example.com",
            given_name="Madonna",
        )

        assert user.first_name == "Madonna"
        assert user.last_name == ""

    def test_get_existing_user_case_insensitive_email(self):
        """Test retrieving an existing user regardless of email casing."""
        User.objects.create_user(
            username="existing",
            email="existing@example.com",
            first_name="Existing",
        )

        user, created = UserService.get_or_create_user(email="EXISTING@Example.com")

        assert created is False
        assert user.email == "existing@example.com"
        assert user.first_name == "Existing"
        assert User.objects.filter(email__iexact="existing@example.com").count() == 1

    def test_get_existing_user_by_google_id_when_email_changes(self):
        """Prefer matching existing user by stable Google sub ID."""
        existing = User.objects.create_user(
            username="original",
            email="old@example.com",
        )
        GoogleOAuthToken.objects.create(
            user=existing,
            access_token="tok",
            google_id="google-sub-999",
        )

        user, created = UserService.get_or_create_user(
            email="new-email@example.com",
            google_id="google-sub-999",
            email_verified=True,
        )

        assert created is False
        assert user.pk == existing.pk

    def test_multiple_users_same_email_selects_earliest_deterministically(self):
        """Duplicate emails do not crash with MultipleObjectsReturned."""
        first = User.objects.create_user(username="dup1", email="dup@example.com")
        User.objects.create_user(username="dup2", email="dup@example.com")

        user, created = UserService.get_or_create_user(email="dup@example.com")
        assert created is False
        assert user.pk == first.pk

    def test_rejects_unverified_email_by_default(self):
        """Unverified Google emails are rejected when GOOGLE_OAUTH_REQUIRE_VERIFIED_EMAIL=True."""
        with pytest.raises(ValueError, match="not verified"):
            UserService.get_or_create_user(
                email="unverified@example.com",
                email_verified=False,
            )

    @override_settings(GOOGLE_OAUTH_REQUIRE_VERIFIED_EMAIL=False)
    def test_allows_unverified_email_when_setting_disabled(self):
        user, created = UserService.get_or_create_user(
            email="unverified@example.com",
            email_verified=False,
        )
        assert created is True
        assert user.email == "unverified@example.com"

    def test_update_existing_user_info(self):
        """Test updating existing user with new info."""
        User.objects.create_user(
            username="test",
            email="test@example.com",
        )

        user, _ = UserService.get_or_create_user(
            email="test@example.com", name="Test User"
        )

        assert user.first_name == "Test"
        assert user.last_name == "User"

    def test_update_existing_user_with_given_and_family_names(self):
        User.objects.create_user(username="jane", email="jane@example.com")
        user, _ = UserService.get_or_create_user(
            email="jane@example.com",
            given_name="Jane",
            family_name="Roe",
        )
        assert user.first_name == "Jane"
        assert user.last_name == "Roe"

    def test_generate_unique_username_and_sanitization(self):
        """Test unique username generation and invalid char stripping."""
        user1, _ = UserService.get_or_create_user(email="test@example.com")
        assert user1.username == "test"

        user2, _ = UserService.get_or_create_user(email="test@different.com")
        assert user2.username == "test1"

        user3, _ = UserService.get_or_create_user(email="test@another.com")
        assert user3.username == "test2"

        user4, _ = UserService.get_or_create_user(email="bad chars!#$@example.com")
        assert user4.username == "badchars"

        user5, _ = UserService.get_or_create_user(email="!!!@example.com")
        assert user5.username == "user"

    def test_create_user_without_email_raises_error(self):
        """Test that creating user without email raises error."""
        with pytest.raises(ValueError, match="Email is required"):
            UserService.get_or_create_user(email="")

    def test_create_user_fallback_when_create_user_raises_type_error(self):
        """Fallback to direct model instantiation if custom manager rejects kwargs."""
        with patch.object(User.objects, "create_user", side_effect=TypeError("bad kw")):
            user, created = UserService.get_or_create_user(
                email="fallback@example.com",
                name="Fall Back",
            )
            assert created is True
            assert user.email == "fallback@example.com"
            assert user.has_usable_password() is False


class TestOAuthFlowService:
    """Test OAuthFlowService functionality."""

    def test_store_and_verify_state(self):
        """Test storing and verifying OAuth state."""
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        OAuthFlowService.store_state(request, "test-state-123")
        assert request.session["oauth_state"] == "test-state-123"

        assert OAuthFlowService.verify_state(request, "test-state-123") is True
        assert OAuthFlowService.verify_state(request, "wrong-state") is False
        assert OAuthFlowService.verify_state(request, None) is False

    def test_verify_state_without_session_state(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        assert OAuthFlowService.verify_state(request, "any-state") is False

    def test_store_get_and_clear_scopes_and_code_verifier(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        OAuthFlowService.store_state(request, "state-1")
        OAuthFlowService.store_scopes(request, ["openid", "email"])
        OAuthFlowService.store_code_verifier(request, "verifier-abc")

        assert OAuthFlowService.get_scopes(request) == ["openid", "email"]
        assert OAuthFlowService.get_code_verifier(request) == "verifier-abc"

        OAuthFlowService.store_scopes(request, None)
        OAuthFlowService.store_code_verifier(request, None)
        assert OAuthFlowService.get_scopes(request) is None
        assert OAuthFlowService.get_code_verifier(request) is None

        OAuthFlowService.store_scopes(request, ["openid"])
        OAuthFlowService.store_code_verifier(request, "verifier-2")
        OAuthFlowService.clear_state(request)
        assert "oauth_state" not in request.session
        assert "oauth_scopes" not in request.session
        assert "oauth_code_verifier" not in request.session

    def test_store_and_get_next_url(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        OAuthFlowService.store_next_url(request, "/dashboard/")
        assert request.session["oauth_next"] == "/dashboard/"

        next_url = OAuthFlowService.get_next_url(request)
        assert next_url == "/dashboard/"
        assert "oauth_next" not in request.session

    def test_get_next_url_default(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        next_url = OAuthFlowService.get_next_url(request, default="/home/")
        assert next_url == "/home/"


@pytest.mark.django_db
class TestGoogleOAuthService:
    """Test GoogleOAuthService functionality."""

    def test_make_aware_handles_none_naive_and_aware(self):
        assert _make_aware(None) is None

        naive = datetime(2026, 1, 1, 12, 0, 0)
        aware = _make_aware(naive)
        assert timezone.is_aware(aware)
        assert aware.utcoffset() == timedelta(0)

        already_aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt_timezone.utc)
        assert _make_aware(already_aware) == already_aware

    def test_extract_user_info(self):
        id_info = {
            "email": "test@example.com",
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "picture": "https://example.com/photo.jpg",
            "sub": "123456789",
            "email_verified": True,
        }

        user_info = GoogleOAuthService.extract_user_info(id_info)

        assert user_info == {
            "email": "test@example.com",
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "picture": "https://example.com/photo.jpg",
            "google_id": "123456789",
            "email_verified": True,
        }

    def test_extract_user_info_with_missing_fields(self):
        id_info = {"email": "test@example.com"}

        user_info = GoogleOAuthService.extract_user_info(id_info)

        assert user_info["email"] == "test@example.com"
        assert user_info["name"] == ""
        assert user_info["google_id"] == ""
        assert user_info["email_verified"] is False

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_process_credentials(self, mock_verify):
        mock_verify.return_value = {
            "email": "alice@example.com",
            "name": "Alice",
            "picture": "https://example.com/a.jpg",
            "email_verified": True,
            "sub": "sub-1",
            "given_name": "Alice",
            "family_name": "A",
        }
        expiry = datetime(2026, 6, 1, 12, 0, 0)
        creds = SimpleNamespace(
            token="access-1",
            refresh_token="refresh-1",
            id_token="id-tok-1",
            client_id="cid",
            expiry=expiry,
        )

        result = GoogleOAuthService.process_credentials(creds)
        assert result["access_token"] == "access-1"
        assert result["refresh_token"] == "refresh-1"
        assert result["expires_in"] == expiry.isoformat()
        assert result["user_info"]["email"] == "alice@example.com"
        assert result["user_info"]["email_verified"] is True

    def test_store_tokens_in_session_when_enabled(self, settings):
        settings.GOOGLE_OAUTH_STORE_TOKENS = True

        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        expiry = datetime(2026, 1, 1, 12, 0, 0)
        credentials = SimpleNamespace(
            token="test-access-token",
            refresh_token="test-refresh-token",
            expiry=expiry,
        )

        GoogleOAuthService.store_tokens_in_session(request, credentials)

        assert request.session["google_access_token"] == "test-access-token"
        assert request.session["google_refresh_token"] == "test-refresh-token"
        assert request.session["google_token_expiry"] == expiry.isoformat()

    def test_store_tokens_in_session_when_disabled(self, settings):
        settings.GOOGLE_OAUTH_STORE_TOKENS = False

        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        credentials = SimpleNamespace(
            token="test-access-token",
            refresh_token="test-refresh-token",
            expiry=None,
        )

        GoogleOAuthService.store_tokens_in_session(request, credentials)

        assert "google_access_token" not in request.session
        assert "google_refresh_token" not in request.session

    def test_save_and_get_user_token_preserves_existing_refresh_token(self):
        user = User.objects.create_user(username="tokuser", email="tok@example.com")
        assert GoogleOAuthService.get_user_token(user) is None

        expiry1 = datetime(2026, 6, 1, 12, 0, 0)
        creds1 = SimpleNamespace(
            token="access-1",
            refresh_token="refresh-1",
            id_token="id-1",
            expiry=expiry1,
            scopes=["openid", "email"],
        )
        token = GoogleOAuthService.save_user_token(
            user=user, credentials=creds1, google_id="sub-123"
        )
        assert token.access_token == "access-1"
        assert token.refresh_token == "refresh-1"
        assert token.google_id == "sub-123"
        assert token.get_scopes_list() == ["openid", "email"]

        # Re-auth without a new refresh_token keeps the existing refresh_token
        creds2 = SimpleNamespace(
            token="access-2",
            refresh_token=None,
            id_token=None,
            expiry=expiry1 + timedelta(hours=1),
            scopes=None,
        )
        updated = GoogleOAuthService.save_user_token(
            user=user, credentials=creds2, scopes=["openid", "profile"]
        )
        assert updated.access_token == "access-2"
        assert updated.refresh_token == "refresh-1"
        assert updated.get_scopes_list() == ["openid", "profile"]

    def test_refresh_user_token_updates_fields_and_emits_signal(self):
        user = User.objects.create_user(username="refuser", email="ref@example.com")
        token = GoogleOAuthToken.objects.create(
            user=user,
            access_token="old-access",
            refresh_token="old-refresh",
            token_expiry=timezone.now() - timedelta(minutes=5),
            scopes="openid,email",
        )

        signal_receiver = MagicMock()
        google_oauth_token_refreshed.connect(signal_receiver)

        new_expiry = datetime.now(dt_timezone.utc).replace(tzinfo=None) + timedelta(
            hours=1
        )

        def fake_refresh(self, _request):
            self.token = "new-access"
            self._refresh_token = "rotated-refresh"
            self._id_token = "new-id-token"
            self.expiry = new_expiry

        try:
            with patch(
                "google.oauth2.credentials.Credentials.refresh",
                new=fake_refresh,
            ):
                refreshed = GoogleOAuthService.refresh_user_token(user)

            assert refreshed.access_token == "new-access"
            assert refreshed.refresh_token == "rotated-refresh"
            assert refreshed.id_token == "new-id-token"
            assert refreshed.is_valid is True
            assert signal_receiver.call_count == 1
            assert signal_receiver.call_args.kwargs["user"] == user
            assert signal_receiver.call_args.kwargs["token"].pk == token.pk
        finally:
            google_oauth_token_refreshed.disconnect(signal_receiver)

    def test_refresh_user_token_validation_and_error_handling(self):
        user = User.objects.create_user(username="noref", email="noref@example.com")
        with pytest.raises(ValueError, match="No token found"):
            GoogleOAuthService.refresh_user_token(user)

        token = GoogleOAuthToken.objects.create(
            user=user, access_token="old", refresh_token=None
        )
        with pytest.raises(ValueError, match="No refresh token available"):
            GoogleOAuthService.refresh_user_token(token)

        token.refresh_token = "bad-refresh"
        token.save()
        with patch(
            "google.oauth2.credentials.Credentials.refresh",
            side_effect=RuntimeError("google error"),
        ):
            with pytest.raises(RuntimeError, match="google error"):
                GoogleOAuthService.refresh_user_token(token)

    def test_revoke_user_token_uses_post_body_and_timeout(self):
        user = User.objects.create_user(username="revuser", email="rev@example.com")
        assert GoogleOAuthService.revoke_user_token(user) is False

        GoogleOAuthToken.objects.create(
            user=user,
            access_token="secret-access",
            refresh_token="secret-refresh",
        )

        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = GoogleOAuthService.revoke_user_token(user)

        assert result is True
        assert GoogleOAuthService.get_user_token(user) is None
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        # Security: token must be sent in POST body (data=), never URL query (params=)
        assert kwargs["data"] == {"token": "secret-refresh"}
        assert "params" not in kwargs
        assert kwargs["timeout"] == 10

    def test_revoke_user_token_deletes_even_when_google_fails(self):
        user = User.objects.create_user(username="revfail", email="revfail@example.com")
        GoogleOAuthToken.objects.create(user=user, access_token="only-access")

        with patch("requests.post", side_effect=ConnectionError("offline")):
            assert GoogleOAuthService.revoke_user_token(user) is True
        assert GoogleOAuthService.get_user_token(user) is None

        GoogleOAuthToken.objects.create(user=user, access_token="only-access")
        with patch("requests.post", return_value=MagicMock(status_code=400)):
            assert GoogleOAuthService.revoke_user_token(user) is True
        assert GoogleOAuthService.get_user_token(user) is None

    def test_get_valid_token_and_get_credentials_auto_refresh_within_leeway(self):
        user = User.objects.create_user(username="lee", email="lee@example.com")
        assert GoogleOAuthService.get_valid_token(user) == (None, None)
        assert GoogleOAuthService.get_credentials(user) is None

        # Token expires in 20 seconds (< 60s default leeway) -> triggers auto-refresh
        token = GoogleOAuthToken.objects.create(
            user=user,
            access_token="expiring-soon",
            refresh_token="ref-1",
            token_expiry=timezone.now() + timedelta(seconds=20),
        )

        new_expiry = datetime.now(dt_timezone.utc).replace(tzinfo=None) + timedelta(
            hours=1
        )

        def fake_refresh(self, _request):
            self.token = "fresh-access"
            self.expiry = new_expiry

        with patch("google.oauth2.credentials.Credentials.refresh", new=fake_refresh):
            access, expiry = GoogleOAuthService.get_valid_token(user)
            assert access == "fresh-access"
            assert expiry is not None

        # Now token is fresh -> get_credentials returns ready-to-use Credentials
        creds = GoogleOAuthService.get_credentials(user)
        assert creds is not None
        assert creds.token == "fresh-access"

        # If expired without refresh token -> returns (None, None) / None
        token.refresh_from_db()
        token.refresh_token = None
        token.token_expiry = timezone.now() - timedelta(minutes=1)
        token.save()
        assert GoogleOAuthService.get_valid_token(user) == (None, None)
        assert GoogleOAuthService.get_credentials(user) is None

    def test_get_valid_token_and_credentials_return_none_on_refresh_failure(self):
        user = User.objects.create_user(username="failref", email="failref@example.com")
        GoogleOAuthToken.objects.create(
            user=user,
            access_token="expired",
            refresh_token="bad-ref",
            token_expiry=timezone.now() - timedelta(minutes=5),
        )
        with patch(
            "google.oauth2.credentials.Credentials.refresh",
            side_effect=RuntimeError("revoked"),
        ):
            assert GoogleOAuthService.get_valid_token(user) == (None, None)
            assert GoogleOAuthService.get_credentials(user) is None
