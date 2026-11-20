"""
Tests for django_googler security helpers and signed state verification.
"""

import time

import pytest
from django.core import signing
from django.test import RequestFactory, override_settings

from django_googler.security import (
    SignedStateOAuthMixin,
    is_safe_next_url,
    validate_redirect_uri,
)


class TestSafeNextUrl:
    """Test open-redirect protection helper."""

    def test_allows_relative_path(self):
        request = RequestFactory().get("/", HTTP_HOST="testserver")
        assert is_safe_next_url(request, "/dashboard/?tab=1") is True

    def test_allows_same_host(self):
        request = RequestFactory().get("/", HTTP_HOST="testserver")
        assert is_safe_next_url(request, "http://testserver/profile/") is True

    def test_blocks_external_host_and_schemes(self):
        request = RequestFactory().get("/", HTTP_HOST="testserver")
        assert is_safe_next_url(request, "https://evil.com/phish") is False
        assert is_safe_next_url(request, "//evil.com/phish") is False
        assert is_safe_next_url(request, "javascript:alert(1)") is False
        assert is_safe_next_url(request, "") is False
        assert is_safe_next_url(request, None) is False


class TestValidateRedirectUri:
    """Test redirect_uri validation and allowlisting."""

    def test_none_or_empty_returns_none(self):
        assert validate_redirect_uri(None) is None
        assert validate_redirect_uri("") is None

    def test_accepts_valid_http_and_https(self):
        uri = "https://app.example.com/auth/callback"
        assert validate_redirect_uri(uri) == uri
        assert (
            validate_redirect_uri("http://localhost:3000/callback")
            == "http://localhost:3000/callback"
        )

    def test_rejects_invalid_schemes_and_missing_host(self):
        with pytest.raises(ValueError, match="Invalid redirect_uri"):
            validate_redirect_uri("javascript:alert(1)")
        with pytest.raises(ValueError, match="Invalid redirect_uri"):
            validate_redirect_uri("/relative/callback")

    @override_settings(
        GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS=["https://app.example.com/callback"]
    )
    def test_enforces_allowlist_when_configured(self):
        assert (
            validate_redirect_uri("https://app.example.com/callback")
            == "https://app.example.com/callback"
        )
        with pytest.raises(ValueError, match="GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS"):
            validate_redirect_uri("https://evil.example.com/callback")


class TestSignedStateOAuthMixin:
    """Test cryptographic state signing and verification."""

    def test_sign_and_verify_full_payload(self):
        signed = SignedStateOAuthMixin.sign_state(
            "raw-state-123",
            scopes=["openid", "email"],
            extra_metadata={"tenant": "acme"},
            redirect_uri="http://localhost:3000/callback",
        )
        is_valid, state, metadata = SignedStateOAuthMixin.verify_signed_state(signed)
        assert is_valid is True
        assert state == "raw-state-123"
        assert metadata == {
            "scopes": ["openid", "email"],
            "extra_metadata": {"tenant": "acme"},
            "redirect_uri": "http://localhost:3000/callback",
        }

    def test_rejects_tampered_and_empty_state(self):
        assert SignedStateOAuthMixin.verify_signed_state("") == (False, None, None)
        assert SignedStateOAuthMixin.verify_signed_state("not-a-valid-token") == (
            False,
            None,
            None,
        )

        signed = SignedStateOAuthMixin.sign_state("raw-state")
        tampered = signed[:-2] + ("a" if signed[-1] != "a" else "b")
        assert SignedStateOAuthMixin.verify_signed_state(tampered) == (
            False,
            None,
            None,
        )

    def test_rejects_state_signed_without_salt(self):
        unsalted = signing.dumps({"state": "abc"}, compress=True)
        assert SignedStateOAuthMixin.verify_signed_state(unsalted) == (
            False,
            None,
            None,
        )

    @override_settings(GOOGLE_OAUTH_STATE_MAX_AGE=1)
    def test_rejects_expired_state(self):
        signed = SignedStateOAuthMixin.sign_state("short-lived")
        time.sleep(1.1)
        assert SignedStateOAuthMixin.verify_signed_state(signed) == (False, None, None)

    def test_subclass_state_max_age_override(self):
        class CustomStateMixin(SignedStateOAuthMixin):
            STATE_MAX_AGE = 120

        assert CustomStateMixin.get_state_max_age() == 120

    def test_legacy_string_and_unexpected_format(self):
        legacy = signing.dumps("plain-state", salt=SignedStateOAuthMixin.STATE_SALT)
        assert SignedStateOAuthMixin.verify_signed_state(legacy) == (
            True,
            "plain-state",
            {},
        )

        unexpected = signing.dumps([1, 2, 3], salt=SignedStateOAuthMixin.STATE_SALT)
        assert SignedStateOAuthMixin.verify_signed_state(unexpected) == (
            False,
            None,
            None,
        )
