"""
Tests for django_googler dynamic settings and Django system checks.
"""

import pytest
from django.test import override_settings

from django_googler import defaults
from django_googler.checks import check_google_oauth_settings
from django_googler.defaults import app_settings, get_django_google_setting


class TestDefaults:
    """Test dynamic settings resolution and backwards-compatible accessors."""

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="override-client-id")
    def test_dynamic_setting_respects_override_settings(self):
        assert (
            get_django_google_setting("GOOGLE_OAUTH_CLIENT_ID") == "override-client-id"
        )
        assert app_settings.GOOGLE_OAUTH_CLIENT_ID == "override-client-id"
        assert defaults.GOOGLE_OAUTH_CLIENT_ID == "override-client-id"

    def test_mutable_defaults_return_fresh_copy(self):
        scopes1 = get_django_google_setting("GOOGLE_OAUTH_SCOPES")
        scopes1.append("https://example.com/fake")
        scopes2 = get_django_google_setting("GOOGLE_OAUTH_SCOPES")
        assert "https://example.com/fake" not in scopes2

    def test_invalid_setting_raises_attribute_error(self):
        with pytest.raises(AttributeError, match="Invalid django_googler setting"):
            _ = app_settings.NOT_A_REAL_SETTING

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = defaults.NOT_A_REAL_SETTING


class TestSystemChecks:
    """Test Django system checks for django_googler."""

    @override_settings(
        DEBUG=True,
        GOOGLE_OAUTH_CLIENT_ID="valid-id",
        GOOGLE_OAUTH_CLIENT_SECRET="valid-secret",
        GOOGLE_OAUTH_REDIRECT_URIS=["http://localhost:8000/api/auth/google/callback/"],
        GOOGLE_OAUTH_SCOPES=["openid", "email"],
        DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK=False,
    )
    def test_checks_pass_with_valid_config(self):
        errors = check_google_oauth_settings(None)
        assert errors == []

    @override_settings(
        DEBUG=True,
        GOOGLE_OAUTH_CLIENT_ID="",
        GOOGLE_OAUTH_CLIENT_SECRET="",
    )
    def test_checks_report_missing_client_id_and_secret(self):
        errors = check_google_oauth_settings(None)
        ids = {e.id for e in errors}
        assert "django_googler.E001" in ids
        assert "django_googler.E002" in ids

    @override_settings(
        DEBUG=False,
        GOOGLE_OAUTH_CLIENT_ID="prod-id",
        GOOGLE_OAUTH_CLIENT_SECRET="prod-secret",
        GOOGLE_OAUTH_REDIRECT_URIS=["http://localhost:8000/api/auth/google/callback/"],
        DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK=True,
    )
    def test_checks_warn_on_production_misconfigurations(self):
        errors = check_google_oauth_settings(None)
        ids = {e.id for e in errors}
        assert "django_googler.W001" in ids
        assert "django_googler.W002" in ids

    @override_settings(
        DEBUG=True,
        GOOGLE_OAUTH_CLIENT_ID="valid-id",
        GOOGLE_OAUTH_CLIENT_SECRET="valid-secret",
        GOOGLE_OAUTH_REDIRECT_URIS="http://localhost:8000/callback",
        GOOGLE_OAUTH_SCOPES="openid email",
    )
    def test_checks_report_non_list_settings(self):
        errors = check_google_oauth_settings(None)
        ids = {e.id for e in errors}
        assert "django_googler.E003" in ids
        assert "django_googler.E004" in ids
