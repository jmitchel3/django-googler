"""
Tests for platform_client OAuth flow creation helpers.
"""

from urllib.parse import parse_qs, urlparse

from django.test import override_settings

from django_googler.platform_client import get_google_auth_flow, get_google_auth_url


class TestPlatformClient:
    """Test get_google_auth_flow and get_google_auth_url."""

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID="dynamic-id",
        GOOGLE_OAUTH_CLIENT_SECRET="dynamic-secret",
        GOOGLE_OAUTH_REDIRECT_URIS=["https://example.com/callback/"],
        GOOGLE_OAUTH_SCOPES=["openid", "email"],
        GOOGLE_OAUTH_AUTH_URI="https://accounts.google.com/o/oauth2/auth",
        GOOGLE_OAUTH_TOKEN_URI="https://oauth2.googleapis.com/token",
    )
    def test_flow_reads_dynamic_settings_and_disables_auto_pkce_by_default(self):
        flow = get_google_auth_flow()
        assert flow.client_config["client_id"] == "dynamic-id"
        assert flow.client_config["client_secret"] == "dynamic-secret"
        assert flow.client_config["token_uri"] == "https://oauth2.googleapis.com/token"
        assert flow.redirect_uri == "https://example.com/callback/"
        assert flow.autogenerate_code_verifier is False

        url, state = get_google_auth_url(flow)
        parsed = parse_qs(urlparse(url).query)
        assert state
        assert parsed["client_id"] == ["dynamic-id"]
        assert parsed["redirect_uri"] == ["https://example.com/callback/"]
        assert parsed["prompt"] == ["consent"]
        assert "code_challenge" not in parsed

    def test_flow_with_pkce_autogeneration(self):
        flow = get_google_auth_flow(
            redirect_uri=["https://example.com/cb"],
            scopes=["openid"],
            autogenerate_code_verifier=True,
        )
        url, _state = get_google_auth_url(flow, prompt=None)
        parsed = parse_qs(urlparse(url).query)
        assert flow.code_verifier is not None
        assert "code_challenge" in parsed
        assert parsed["code_challenge_method"] == ["S256"]
        assert "prompt" not in parsed

    def test_flow_accepts_explicit_empty_scopes(self):
        flow = get_google_auth_flow(scopes=[])
        assert flow.oauth2session.scope == []
