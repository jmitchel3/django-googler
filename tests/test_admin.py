"""
Tests for django_googler Django admin configuration.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.utils import timezone

from django_googler.admin import GoogleOAuthTokenAdmin
from django_googler.models import GoogleOAuthToken

User = get_user_model()


def _make_admin_request():
    request = RequestFactory().get("/admin/")
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
class TestGoogleOAuthTokenAdmin:
    """Test GoogleOAuthTokenAdmin display helpers, security, and actions."""

    def setup_method(self):
        self.site = AdminSite()
        self.model_admin = GoogleOAuthTokenAdmin(GoogleOAuthToken, self.site)

    def test_display_methods_and_xss_escaping(self):
        user = User.objects.create_user(username="adm", email="adm@example.com")
        token = GoogleOAuthToken.objects.create(
            user=user,
            access_token="a" * 40,
            refresh_token="r" * 40,
            token_expiry=timezone.now() + timedelta(hours=1),
            scopes="openid,<script>alert(1)</script>",
            google_id="sub-adm",
        )

        assert self.model_admin.user_email(token) == "adm@example.com"
        assert self.model_admin.token_status(token) == "Valid"
        assert "Valid" in self.model_admin.token_status_badge(token)
        assert self.model_admin.has_refresh_token(token) is True
        assert self.model_admin.scope_count(token) == 2
        assert self.model_admin.expiry_display(token) != "Unknown"
        assert "..." in self.model_admin.access_token_preview(token)
        assert "..." in self.model_admin.refresh_token_preview(token)

        # Verify XSS payload in scopes is HTML-escaped
        rendered_scopes = self.model_admin.scopes_display(token)
        assert "<script>" not in rendered_scopes
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered_scopes

    def test_display_methods_for_expired_and_empty_tokens(self):
        user = User.objects.create_user(username="exp", email="exp@example.com")
        token = GoogleOAuthToken.objects.create(
            user=user,
            access_token="",
            refresh_token="",
            token_expiry=None,
            scopes="",
        )

        assert self.model_admin.token_status(token) == "Expired"
        assert "Expired" in self.model_admin.token_status_badge(token)
        assert self.model_admin.expiry_display(token) == "Unknown"
        assert self.model_admin.scopes_display(token) == "None"
        assert self.model_admin.access_token_preview(token) == "None"
        assert self.model_admin.refresh_token_preview(token) == "None"

        # Non-expired but missing access token -> Invalid
        token.token_expiry = timezone.now() + timedelta(hours=1)
        assert self.model_admin.token_status(token) == "Invalid"
        assert "Invalid" in self.model_admin.token_status_badge(token)

        # Short tokens are shown without ellipsis
        token.access_token = "short-tok"
        token.refresh_token = "short-ref"
        assert "short-tok" in self.model_admin.access_token_preview(token)
        assert "short-ref" in self.model_admin.refresh_token_preview(token)

    def test_dynamic_search_fields_and_permissions(self):
        request = _make_admin_request()
        fields = self.model_admin.get_search_fields(request)
        assert "user__email" in fields
        assert "user__username" in fields
        assert "google_id" in fields

        assert self.model_admin.has_add_permission(request) is False
        assert self.model_admin.has_delete_permission(request) is True

    def test_admin_refresh_and_revoke_actions(self):
        user1 = User.objects.create_user(username="act1", email="act1@example.com")
        user2 = User.objects.create_user(username="act2", email="act2@example.com")
        t1 = GoogleOAuthToken.objects.create(
            user=user1, access_token="a1", refresh_token="r1"
        )
        t2 = GoogleOAuthToken.objects.create(
            user=user2, access_token="a2", refresh_token=None
        )
        qs = GoogleOAuthToken.objects.filter(pk__in=[t1.pk, t2.pk])
        request = _make_admin_request()

        # Refresh action: t1 succeeds, t2 fails (no refresh token)
        with patch(
            "django_googler.admin.GoogleOAuthService.refresh_user_token",
            side_effect=[t1, ValueError("no refresh")],
        ):
            self.model_admin.refresh_selected_tokens(request, qs)

        msgs = [m.message for m in request._messages]
        assert any("Refreshed 1 token(s)." in m for m in msgs)
        assert any("Failed to refresh 1 token(s)." in m for m in msgs)

        # Revoke action: deletes both
        request2 = _make_admin_request()
        with patch("requests.post", return_value=MagicMock(status_code=200)):
            self.model_admin.revoke_selected_tokens(request2, qs)

        assert GoogleOAuthToken.objects.filter(pk__in=[t1.pk, t2.pk]).count() == 0
        msgs2 = [m.message for m in request2._messages]
        assert any("Revoked and deleted 2 token(s)." in m for m in msgs2)
