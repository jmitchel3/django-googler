"""
Tests for DRF Google OAuth API views and YouTube connect views.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import serializers
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from django_googler.connect.youtube import (
    YouTubeManageConnectAPIView,
    YouTubePartnerChannelAuditConnectAPIView,
    YouTubePartnerConnectAPIView,
    YouTubeReadOnlyConnectAPIView,
)
from django_googler.models import GoogleOAuthToken
from django_googler.security import SignedStateOAuthMixin
from django_googler.signals import (
    google_oauth_failed,
    google_oauth_logout,
    google_oauth_success,
)
from django_googler.views_api import GoogleOAuthLoginBaseAPIView

User = get_user_model()


class CustomAPIUserSerializer(serializers.Serializer):
    """Custom serializer to verify GOOGLE_OAUTH_USER_SERIALIZER support."""

    uid = serializers.IntegerField(source="pk")
    mail = serializers.EmailField(source="email")


def _fake_credentials():
    return SimpleNamespace(
        token="google-access-token",
        refresh_token="google-refresh-token",
        id_token="fake-id-token",
        client_id="test-client-id.apps.googleusercontent.com",
        expiry=datetime.now(dt_timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        scopes=["openid", "email"],
    )


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """Clear throttle cache before and after each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestGoogleOAuthLoginAPIView:
    """Tests for GET /api/auth/google/login/."""

    def test_login_returns_authorization_url_and_signed_state(self):
        client = APIClient()
        url = reverse("django_googler_api:google-login")

        resp = client.get(
            url,
            {
                "redirect_uri": "http://localhost:3000/auth/callback",
                "scopes": "openid, email",
                "code_challenge": "abc123challenge",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "authorization_url" in data
        assert "state" in data

        # Verify state is embedded in authorization_url and carries redirect_uri + scopes
        parsed = parse_qs(urlparse(data["authorization_url"]).query)
        assert parsed["state"] == [data["state"]]
        assert parsed["redirect_uri"] == ["http://localhost:3000/auth/callback"]
        assert parsed["code_challenge"] == ["abc123challenge"]
        assert parsed["code_challenge_method"] == ["S256"]

        is_valid, _orig, metadata = SignedStateOAuthMixin.verify_signed_state(
            data["state"]
        )
        assert is_valid is True
        assert metadata["redirect_uri"] == "http://localhost:3000/auth/callback"
        assert metadata["scopes"] == ["openid", "email"]

    @override_settings(
        GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS=["https://app.example.com/callback"]
    )
    def test_login_rejects_disallowed_redirect_uri(self):
        client = APIClient()
        url = reverse("django_googler_api:google-login")

        resp = client.get(url, {"redirect_uri": "https://evil.example.com/cb"})
        assert resp.status_code == 400
        assert "GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS" in resp.json()["error"]

    def test_login_rejects_invalid_code_challenge_method(self):
        client = APIClient()
        url = reverse("django_googler_api:google-login")

        resp = client.get(
            url,
            {"code_challenge": "abc", "code_challenge_method": "plain"},
        )
        assert resp.status_code == 400
        assert "S256" in resp.json()["error"]

    @override_settings(DEBUG=False)
    def test_login_hides_internal_exception_details_when_debug_false(self):
        client = APIClient()
        url = reverse("django_googler_api:google-login")

        with patch(
            "django_googler.views_api.get_google_auth_flow",
            side_effect=RuntimeError("super secret db error"),
        ):
            resp = client.get(url)

        assert resp.status_code == 500
        body = resp.json()
        assert body == {"error": "Failed to initiate OAuth flow"}
        assert "detail" not in body

    def test_subclass_with_extra_metadata_and_none_prompt(self):
        class CustomLoginView(GoogleOAuthLoginBaseAPIView):
            permission_classes = []
            authentication_classes = []

            def get_prompt_type(self):
                return None

            def get_extra_metadata(self, request):
                return {"source": "mobile"}

        factory = APIRequestFactory()
        request = factory.get("/login/")
        resp = CustomLoginView.as_view()(request)
        assert resp.status_code == 200
        parsed = parse_qs(urlparse(resp.data["authorization_url"]).query)
        assert "prompt" not in parsed

        is_valid, _orig, metadata = SignedStateOAuthMixin.verify_signed_state(
            resp.data["state"]
        )
        assert is_valid is True
        assert metadata["extra_metadata"] == {"source": "mobile"}


@pytest.mark.django_db
class TestGoogleOAuthCallbackAPIView:
    """Tests for POST/GET /api/auth/google/callback/."""

    def test_callback_creates_user_issues_jwt_and_fires_signal_with_metadata(self):
        client = APIClient()
        cb_url = reverse("django_googler_api:google-callback")

        signed_state = SignedStateOAuthMixin.sign_state(
            "orig-state",
            scopes=["openid", "email"],
            extra_metadata={"plan": "pro"},
            redirect_uri="http://localhost:3000/auth/callback",
        )

        fake_flow = MagicMock(credentials=_fake_credentials())
        received_signals = []

        def on_success(sender, **kwargs):
            received_signals.append(kwargs)

        google_oauth_success.connect(on_success)

        try:
            with (
                patch(
                    "django_googler.views_api.get_google_auth_flow",
                    return_value=fake_flow,
                ) as mock_get_flow,
                patch(
                    "django_googler.services.GoogleOAuthService.verify_id_token",
                    return_value={
                        "email": "newuser@example.com",
                        "name": "New User",
                        "sub": "sub-new-1",
                        "email_verified": True,
                    },
                ),
            ):
                # Note: redirect_uri omitted from POST body -> recovered from signed state!
                resp = client.post(
                    cb_url,
                    {
                        "code": "google-code",
                        "state": signed_state,
                        "code_verifier": "my-pkce-verifier",
                    },
                    format="json",
                )

            assert resp.status_code == 201
            body = resp.json()
            assert "access" in body
            assert "refresh" in body
            assert body["user"]["email"] == "newuser@example.com"
            assert "google_tokens" not in body

            # Verify redirect_uri from signed state & PKCE verifier were passed to flow
            flow_kwargs = mock_get_flow.call_args.kwargs
            assert flow_kwargs["redirect_uri"] == [
                "http://localhost:3000/auth/callback"
            ]
            assert flow_kwargs["code_verifier"] == "my-pkce-verifier"
            assert flow_kwargs["scopes"] == ["openid", "email"]

            # Verify signal received extra_metadata
            assert len(received_signals) == 1
            assert received_signals[0]["extra_metadata"] == {"plan": "pro"}
            assert received_signals[0]["user_created"] is True

            # Verify DB token saved
            user = User.objects.get(email="newuser@example.com")
            assert GoogleOAuthToken.objects.filter(user=user).exists()
        finally:
            google_oauth_success.disconnect(on_success)

    @override_settings(
        GOOGLE_OAUTH_RETURN_TOKENS=True,
        GOOGLE_OAUTH_USER_SERIALIZER=("tests.test_views_api.CustomAPIUserSerializer"),
    )
    def test_callback_existing_user_returns_200_google_tokens_and_custom_serializer(
        self,
    ):
        existing = User.objects.create_user(
            username="existing", email="existing@example.com"
        )
        client = APIClient()
        cb_url = reverse("django_googler_api:google-callback")
        signed_state = SignedStateOAuthMixin.sign_state("s-1")

        fake_flow = MagicMock(credentials=_fake_credentials())
        with (
            patch(
                "django_googler.views_api.get_google_auth_flow", return_value=fake_flow
            ),
            patch(
                "django_googler.services.GoogleOAuthService.verify_id_token",
                return_value={
                    "email": "existing@example.com",
                    "sub": "sub-existing",
                    "email_verified": True,
                },
            ),
        ):
            resp = client.post(
                cb_url, {"code": "c", "state": signed_state}, format="json"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["user"] == {"uid": existing.pk, "mail": "existing@example.com"}
        assert body["google_tokens"]["access_token"] == "google-access-token"
        assert body["google_tokens"]["refresh_token"] == "google-refresh-token"

    def test_callback_get_disabled_by_default_and_works_when_enabled(self):
        client = APIClient()
        cb_url = reverse("django_googler_api:google-callback")

        resp = client.get(cb_url)
        assert resp.status_code == 405

        signed_state = SignedStateOAuthMixin.sign_state("s-get")
        fake_flow = MagicMock(credentials=_fake_credentials())

        with (
            override_settings(DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK=True),
            patch(
                "django_googler.views_api.get_google_auth_flow", return_value=fake_flow
            ),
            patch(
                "django_googler.services.GoogleOAuthService.verify_id_token",
                return_value={
                    "email": "getuser@example.com",
                    "sub": "sub-get",
                    "email_verified": True,
                },
            ),
        ):
            resp = client.get(cb_url, {"code": "c", "state": signed_state})

        assert resp.status_code == 201
        assert resp.json()["user"]["email"] == "getuser@example.com"

    def test_callback_rejects_invalid_state_and_redirect_uri_mismatch(self):
        client = APIClient()
        cb_url = reverse("django_googler_api:google-callback")

        failed = []
        google_oauth_failed.connect(lambda sender, error, **kw: failed.append(error))

        # Invalid state
        r1 = client.post(cb_url, {"code": "c", "state": "tampered"}, format="json")
        assert r1.status_code == 400
        assert "Invalid or expired state" in r1.json()["error"]

        # redirect_uri mismatch between signed state and POST body
        signed_state = SignedStateOAuthMixin.sign_state(
            "s-2", redirect_uri="http://localhost:3000/callback-a"
        )
        r2 = client.post(
            cb_url,
            {
                "code": "c",
                "state": signed_state,
                "redirect_uri": "http://localhost:3000/callback-b",
            },
            format="json",
        )
        assert r2.status_code == 400
        assert "redirect_uri does not match" in r2.json()["error"]

        # Missing required fields -> 400 DRF ValidationError
        r3 = client.post(cb_url, {}, format="json")
        assert r3.status_code == 400

    @override_settings(DEBUG=False)
    def test_callback_hides_internal_exception_details_when_debug_false(self):
        client = APIClient()
        cb_url = reverse("django_googler_api:google-callback")
        signed_state = SignedStateOAuthMixin.sign_state("s-err")

        with patch(
            "django_googler.views_api.get_google_auth_flow",
            side_effect=RuntimeError("sensitive stack info"),
        ):
            resp = client.post(
                cb_url, {"code": "c", "state": signed_state}, format="json"
            )

        assert resp.status_code == 500
        assert resp.json() == {"error": "Authentication failed"}


@pytest.mark.django_db
class TestCurrentUserAndLogoutAPIViews:
    """Tests for /api/auth/me/ and /api/auth/google/logout/."""

    def test_current_user_requires_auth_and_returns_serialized_user(self):
        client = APIClient()
        me_url = reverse("django_googler_api:current-user")

        assert client.get(me_url).status_code == 401

        user = User.objects.create_user(
            username="meuser",
            email="me@example.com",
            first_name="Me",
            last_name="User",
        )
        token = str(RefreshToken.for_user(user).access_token)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.get(me_url)
        assert resp.status_code == 200
        assert resp.json()["email"] == "me@example.com"
        assert resp.json()["first_name"] == "Me"

    @override_settings(GOOGLE_OAUTH_REVOKE_ON_LOGOUT=True)
    def test_logout_blacklists_jwt_revokes_google_token_and_emits_signal(self):
        user = User.objects.create_user(username="logoutu", email="logout@example.com")
        GoogleOAuthToken.objects.create(
            user=user, access_token="acc", refresh_token="ref"
        )
        refresh = RefreshToken.for_user(user)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        logout_url = reverse("django_googler_api:google-logout")

        logout_receiver = MagicMock()
        google_oauth_logout.connect(logout_receiver)

        try:
            with patch(
                "requests.post", return_value=MagicMock(status_code=200)
            ) as mock_post:
                resp = client.post(logout_url, {"refresh": str(refresh)}, format="json")

            assert resp.status_code == 200
            assert GoogleOAuthToken.objects.filter(user=user).exists() is False
            mock_post.assert_called_once()
            assert logout_receiver.call_count == 1
            assert logout_receiver.call_args.kwargs["user"] == user

            # Refresh token should now be blacklisted
            refresh_url = reverse("django_googler_api:token-refresh")
            refresh_resp = client.post(
                refresh_url, {"refresh": str(refresh)}, format="json"
            )
            assert refresh_resp.status_code == 401
        finally:
            google_oauth_logout.disconnect(logout_receiver)


@pytest.mark.django_db
class TestYouTubeConnectViews:
    """Tests for pre-configured YouTube connect views."""

    @pytest.mark.parametrize(
        "view_cls,expected_scope",
        [
            (
                YouTubeReadOnlyConnectAPIView,
                "https://www.googleapis.com/auth/youtube.readonly",
            ),
            (
                YouTubeManageConnectAPIView,
                "https://www.googleapis.com/auth/youtube.upload",
            ),
            (
                YouTubePartnerConnectAPIView,
                "https://www.googleapis.com/auth/youtubepartner",
            ),
            (
                YouTubePartnerChannelAuditConnectAPIView,
                "https://www.googleapis.com/auth/youtubepartner-channel-audit",
            ),
        ],
    )
    def test_youtube_connect_views_include_expected_scopes_and_consent_prompt(
        self, view_cls, expected_scope
    ):
        factory = APIRequestFactory()
        request = factory.get(
            "/youtube/connect/?redirect_uri=http://localhost:3000/yt/cb"
        )
        resp = view_cls.as_view()(request)
        assert resp.status_code == 200
        parsed = parse_qs(urlparse(resp.data["authorization_url"]).query)
        assert parsed["prompt"] == ["consent"]
        assert parsed["include_granted_scopes"] == ["true"]
        assert expected_scope in parsed["scope"][0]
