from typing import Optional

from google_auth_oauthlib.flow import Flow

from django_googler.defaults import (
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URIS,
    GOOGLE_OAUTH_SCOPES,
)


def get_google_auth_flow(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    redirect_uri: Optional[list[str]] = None,
    scopes: Optional[list[str]] = None,
    state: Optional[str] = None,
) -> Flow:
    """Get a Google Auth Flow object."""
    if redirect_uri is None:  # Handle None default
        redirect_uri = []

    flow_scopes = scopes or GOOGLE_OAUTH_SCOPES
    if isinstance(scopes, list) and len(scopes) == 0:
        flow_scopes = []
    elif isinstance(scopes, list) and len(scopes) > 0:
        flow_scopes = scopes
    else:
        flow_scopes = GOOGLE_OAUTH_SCOPES
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": client_id or GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": client_secret or GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uris": redirect_uri or GOOGLE_OAUTH_REDIRECT_URIS,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://accounts.google.com/o/oauth2/token",
            }
        },
        scopes=flow_scopes,
        state=state,
    )


def get_google_auth_url(flow: Flow) -> tuple[str, str]:
    """Get a Google Auth URL and state."""
    return flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
