"""
Pre-configured YouTube OAuth connect views for django_googler.
"""

from rest_framework.request import Request

from django_googler.defaults import get_django_google_setting
from django_googler.throttling import GoogleOAuthLoginThrottle
from django_googler.views_api import GoogleOAuthLoginBaseAPIView


def _combine_scopes(extra_scopes: list[str]) -> list[str]:
    """Merge configured base OAuth scopes with additional scopes without duplicates."""
    base_scopes = get_django_google_setting("GOOGLE_OAUTH_SCOPES")
    return list(dict.fromkeys([*base_scopes, *extra_scopes]))


class YouTubeConnectBaseAPIView(GoogleOAuthLoginBaseAPIView):
    """Base API view for initiating incremental YouTube OAuth scope grants."""

    throttle_classes = [GoogleOAuthLoginThrottle]
    extra_scopes: list[str] = [
        "https://www.googleapis.com/auth/youtube.readonly",
    ]

    def get_scopes(self, request: Request) -> list[str]:
        return _combine_scopes(self.extra_scopes)

    def get_prompt_type(self) -> str:
        return "consent"

    def get_include_granted_scopes(self) -> bool:
        return True

    def get_redirect_uri(self, request: Request) -> str | None:
        return request.query_params.get("redirect_uri")


class YouTubeReadOnlyConnectAPIView(YouTubeConnectBaseAPIView):
    """Initiate YouTube OAuth with read-only scope."""

    extra_scopes = [
        "https://www.googleapis.com/auth/youtube.readonly",
    ]


class YouTubeManageConnectAPIView(YouTubeConnectBaseAPIView):
    """Initiate YouTube OAuth with full channel/video management scopes."""

    extra_scopes = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]


class YouTubePartnerConnectAPIView(YouTubeConnectBaseAPIView):
    """Initiate YouTube OAuth with Content ID / Partner scope."""

    extra_scopes = [
        "https://www.googleapis.com/auth/youtubepartner",
    ]


class YouTubePartnerChannelAuditConnectAPIView(YouTubeConnectBaseAPIView):
    """Initiate YouTube OAuth with Partner Channel Audit scope."""

    extra_scopes = [
        "https://www.googleapis.com/auth/youtubepartner-channel-audit",
    ]
