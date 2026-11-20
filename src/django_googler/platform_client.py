"""
Google OAuth client flow helpers for django_googler.
"""

from typing import Optional

from google_auth_oauthlib.flow import Flow

from django_googler.defaults import get_django_google_setting


def get_google_auth_flow(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    redirect_uri: Optional[list[str]] = None,
    scopes: Optional[list[str]] = None,
    state: Optional[str] = None,
    code_verifier: Optional[str] = None,
    autogenerate_code_verifier: bool = False,
) -> Flow:
    """
    Create and configure a Google OAuth ``Flow`` object.

    Settings are read dynamically at call time so runtime overrides
    (such as ``@override_settings``) take effect immediately.

    Note:
        ``autogenerate_code_verifier`` defaults to ``False`` because OAuth flows
        in web applications reconstruct the ``Flow`` across separate login and
        callback HTTP requests. Pass ``autogenerate_code_verifier=True`` on
        login (and persist ``flow.code_verifier``) and pass ``code_verifier=...``
        on callback to enable PKCE.

    Args:
        client_id: Optional Google OAuth client ID override
        client_secret: Optional Google OAuth client secret override
        redirect_uri: Optional list of redirect URIs (first entry is set on flow)
        scopes: Optional list of OAuth scopes (defaults to ``GOOGLE_OAUTH_SCOPES``)
        state: Optional OAuth state parameter
        code_verifier: Optional PKCE code verifier string
        autogenerate_code_verifier: Whether to autogenerate a PKCE code verifier

    Returns:
        Configured ``google_auth_oauthlib.flow.Flow`` instance.
    """
    if scopes is None:
        flow_scopes = get_django_google_setting("GOOGLE_OAUTH_SCOPES")
    else:
        flow_scopes = scopes

    redirect_uris_list = (
        redirect_uri
        if redirect_uri
        else get_django_google_setting("GOOGLE_OAUTH_REDIRECT_URIS")
    )

    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": client_id
                or get_django_google_setting("GOOGLE_OAUTH_CLIENT_ID"),
                "client_secret": client_secret
                or get_django_google_setting("GOOGLE_OAUTH_CLIENT_SECRET"),
                "redirect_uris": redirect_uris_list,
                "auth_uri": get_django_google_setting("GOOGLE_OAUTH_AUTH_URI"),
                "token_uri": get_django_google_setting("GOOGLE_OAUTH_TOKEN_URI"),
            }
        },
        scopes=flow_scopes,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=autogenerate_code_verifier,
    )

    # Set the redirect_uri property on the flow object
    # Required for authorization_url() and fetch_token() to work
    if redirect_uris_list:
        flow.redirect_uri = redirect_uris_list[0]
    return flow


def get_google_auth_url(
    flow: Flow,
    *,
    access_type: str = "offline",
    prompt: Optional[str] = "consent",
    include_granted_scopes: str = "true",
    **extra_params,
) -> tuple[str, str]:
    """
    Generate a Google authorization URL and state from a configured ``Flow``.

    Args:
        flow: Configured ``Flow`` instance
        access_type: OAuth access type (default ``"offline"``)
        prompt: Google consent prompt (``"consent"``, ``"select_account"``, or ``None``)
        include_granted_scopes: ``"true"`` or ``"false"``
        **extra_params: Additional query parameters (e.g. ``code_challenge``,
            ``code_challenge_method``, ``login_hint``, ``hd``)

    Returns:
        Tuple of ``(authorization_url, state)``.
    """
    params = {
        "access_type": access_type,
        "include_granted_scopes": include_granted_scopes,
        **extra_params,
    }
    if prompt is not None:
        params["prompt"] = prompt
    return flow.authorization_url(**params)
