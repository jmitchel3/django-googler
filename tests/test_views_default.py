"""
Tests for standard Django session-based OAuth views and mixins.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

from django_googler.models import GoogleOAuthToken
from django_googler.signals import google_oauth_failed, google_oauth_success

User = get_user_model()


def _fake_credentials(email="user@example.com"):
    return SimpleNamespace(
        token="google-access-token",
        refresh_token="google-refresh-token",
        id_token="fake-id-token",
        client_id="test-client-id.apps.googleusercontent.com",
        expiry=datetime.now(dt_timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    )


@pytest.mark.django_db
class TestDefaultDjangoOAuthViews:
    """End-to-end tests for GoogleOAuthLoginView and GoogleOAuthCallbackView."""

    def test_login_initiates_flow_with_pkce_scopes_and_safe_next(self):
        client = Client()
        login_url = reverse("django_googler:google-login")

        response = client.get(
            f"{login_url}?next=/dashboard/&scopes=openid, https://www.googleapis.com/auth/calendar"
        )
        assert response.status_code == 302
        parsed = urlparse(response["Location"])
        assert parsed.netloc == "accounts.google.com"
        params = parse_qs(parsed.query)
        assert "code_challenge" in params
        assert params["code_challenge_method"] == ["S256"]

        session = client.session
        assert session["oauth_state"] == params["state"][0]
        assert session["oauth_next"] == "/dashboard/"
        assert session["oauth_scopes"] == [
            "openid",
            "https://www.googleapis.com/auth/calendar",
        ]
        assert session["oauth_code_verifier"]

    @override_settings(LOGIN_REDIRECT_URL="/safe-home/")
    def test_login_blocks_open_redirect_in_next_param(self):
        client = Client()
        login_url = reverse("django_googler:google-login")

        response = client.get(f"{login_url}?next=https://evil.com/phish")
        assert response.status_code == 302
        assert client.session["oauth_next"] == "/safe-home/"

    @override_settings(LOGIN_URL="/custom-login/?source=app")
    def test_login_handles_init_exception_and_preserves_login_url_query(self):
        client = Client()
        login_url = reverse("django_googler:google-login")

        with patch(
            "django_googler.mixins.get_google_auth_flow",
            side_effect=RuntimeError("boom"),
        ):
            response = client.get(login_url)

        assert response.status_code == 302
        assert (
            response["Location"] == "/custom-login/?source=app&error=oauth_init_failed"
        )

    @override_settings(LOGIN_REDIRECT_URL="/home/")
    def test_full_login_and_callback_flow_logs_user_in_and_saves_token(self):
        client = Client()
        login_url = reverse("django_googler:google-login")
        callback_url = reverse("django_googler:google-callback")

        # 1. Start login
        login_resp = client.get(f"{login_url}?next=/welcome/&scopes=openid,email")
        state = parse_qs(urlparse(login_resp["Location"]).query)["state"][0]
        verifier = client.session["oauth_code_verifier"]

        fake_creds = _fake_credentials()
        fake_flow = MagicMock(credentials=fake_creds)

        success_receiver = MagicMock()
        google_oauth_success.connect(success_receiver)

        try:
            with (
                patch(
                    "django_googler.mixins.get_google_auth_flow",
                    return_value=fake_flow,
                ) as mock_get_flow,
                patch(
                    "django_googler.services.GoogleOAuthService.verify_id_token",
                    return_value={
                        "email": "alice@example.com",
                        "name": "Alice Doe",
                        "sub": "sub-alice",
                        "email_verified": True,
                    },
                ),
            ):
                cb_resp = client.get(f"{callback_url}?code=auth-code&state={state}")

            assert cb_resp.status_code == 302
            assert cb_resp["Location"] == "/welcome/"

            # Verify stored scopes and PKCE code_verifier were forwarded
            call_kwargs = mock_get_flow.call_args.kwargs
            assert call_kwargs["scopes"] == ["openid", "email"]
            assert call_kwargs["code_verifier"] == verifier
            fake_flow.fetch_token.assert_called_once_with(code="auth-code")

            # Verify user created, logged in, and token stored
            user = User.objects.get(email="alice@example.com")
            assert int(client.session["_auth_user_id"]) == user.pk
            token = GoogleOAuthToken.objects.get(user=user)
            assert token.access_token == "google-access-token"
            assert token.google_id == "sub-alice"

            # Verify session state cleaned up
            assert "oauth_state" not in client.session
            assert "oauth_code_verifier" not in client.session

            # Verify signal fired
            assert success_receiver.call_count == 1
            assert success_receiver.call_args.kwargs["user"] == user
            assert success_receiver.call_args.kwargs["user_created"] is True
        finally:
            google_oauth_success.disconnect(success_receiver)

    @override_settings(LOGIN_URL="/login/")
    def test_callback_error_paths_emit_failed_signal(self):
        client = Client()
        callback_url = reverse("django_googler:google-callback")

        failed_events = []

        def on_fail(sender, error, **kwargs):
            failed_events.append(error)

        google_oauth_failed.connect(on_fail)

        try:
            # Error returned from Google
            r1 = client.get(f"{callback_url}?error=access_denied")
            assert r1["Location"] == "/login/?error=access_denied"

            # Missing code
            r2 = client.get(callback_url)
            assert r2["Location"] == "/login/?error=missing_code"

            # Invalid CSRF state
            r3 = client.get(f"{callback_url}?code=abc&state=wrong")
            assert r3["Location"] == "/login/?error=invalid_state"

            # Unverified email
            session = client.session
            session["oauth_state"] = "good-state"
            session.save()

            fake_flow = MagicMock(credentials=_fake_credentials())
            with (
                patch(
                    "django_googler.mixins.get_google_auth_flow", return_value=fake_flow
                ),
                patch(
                    "django_googler.services.GoogleOAuthService.verify_id_token",
                    return_value={"email": "u@example.com", "email_verified": False},
                ),
            ):
                r4 = client.get(f"{callback_url}?code=abc&state=good-state")
            assert r4["Location"] == "/login/?error=email_not_verified"

            # Missing email
            session = client.session
            session["oauth_state"] = "good-state-2"
            session.save()
            with (
                patch(
                    "django_googler.mixins.get_google_auth_flow", return_value=fake_flow
                ),
                patch(
                    "django_googler.services.GoogleOAuthService.verify_id_token",
                    return_value={"email": "", "email_verified": True},
                ),
            ):
                r5 = client.get(f"{callback_url}?code=abc&state=good-state-2")
            assert r5["Location"] == "/login/?error=no_email"

            # Unexpected exception
            session = client.session
            session["oauth_state"] = "good-state-3"
            session.save()
            with patch(
                "django_googler.mixins.get_google_auth_flow",
                side_effect=RuntimeError("network down"),
            ):
                r6 = client.get(f"{callback_url}?code=abc&state=good-state-3")
            assert r6["Location"] == "/login/?error=oauth_callback_failed"

            assert failed_events == [
                "access_denied",
                "missing_code",
                "invalid_state",
                "email_not_verified",
                "no_email",
                "oauth_callback_failed",
            ]
        finally:
            google_oauth_failed.disconnect(on_fail)
