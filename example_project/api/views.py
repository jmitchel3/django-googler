from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from django_googler.defaults import (
    GOOGLE_OAUTH_SCOPES,
)
from django_googler.views_api import GoogleOAuthLoginAPIView


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def test_view(request):
    return Response({"message": "Hello, world!"})


class YouTubeLoginAPIView(GoogleOAuthLoginAPIView):
    def get_scopes(self, request: Request) -> list[str]:
        return GOOGLE_OAUTH_SCOPES + [
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ]

    def get_prompt_type(self) -> str:
        return "consent"

    def get_include_granted_scopes(self) -> bool:
        return True
