from rest_framework.request import Request

from django_googler.views_api import GoogleOAuthLoginBaseAPIView


class YouTubeConnectBaseAPIView(GoogleOAuthLoginBaseAPIView):
    def get_scopes(self, request: Request) -> list[str]:
        return [
            "https://www.googleapis.com/auth/youtube.readonly",
        ]

    def get_prompt_type(self) -> str:
        return "consent"

    def get_include_granted_scopes(self) -> bool:
        return True

    def get_redirect_uri(self, request: Request) -> str | None:
        return request.query_params.get("redirect_uri")


class YouTubeReadOnlyConnectAPIView(YouTubeConnectBaseAPIView):
    def get_scopes(self, request: Request) -> list[str]:
        return [
            "https://www.googleapis.com/auth/youtube.readonly",
        ]


class YouTubeManageConnectAPIView(YouTubeConnectBaseAPIView):
    def get_scopes(self, request: Request) -> list[str]:
        return [
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ]


class YouTubePartnerConnectAPIView(YouTubeConnectBaseAPIView):
    def get_scopes(self, request: Request) -> list[str]:
        return [
            "https://www.googleapis.com/auth/youtubepartner",
        ]


class YouTubePartnerChannelAuditConnectAPIView(YouTubeConnectBaseAPIView):
    def get_scopes(self, request: Request) -> list[str]:
        return [
            "https://www.googleapis.com/auth/youtubepartner-channel-audit",
        ]
