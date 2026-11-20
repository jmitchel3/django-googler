# Django Googler

Simple, secure Google OAuth 2.0 authentication for Django and Django REST Framework (DRF). Supports both stateless JWT API flows (for React, Next.js, Vue, mobile) and standard Django session authentication, plus persistent Google token management for calling Google APIs.

## What It Does

1. User clicks **"Sign in with Google"**
2. Google handles authentication (with PKCE and CSRF/signed-state protection)
3. Your Django app verifies the Google ID token, enforces verified email, creates/matches the user, and saves Google OAuth tokens
4. Returns JWT tokens (API mode) or logs the user into a Django session (standard mode)

## Installation

```bash
uv add django-googler
```

or

```bash
pip install django-googler
```

## Quick Setup

### 1. Create a Google Auth Platform Client

- Go to [Google Cloud Console](https://console.cloud.google.com/)
- Navigate to **Google Auth Platform** -> **Clients** -> **Create Client**
- Select **Web Application**
- Add your **Authorized JavaScript origins** (e.g. `http://localhost:3000`, `http://localhost:8000`)
- Add your **Authorized redirect URIs**:
  - `http://localhost:8000/api/auth/google/callback/`
  - `http://localhost:8000/auth/google/callback/`
  - `http://localhost:3000/auth/callback` (if using a separate SPA frontend)
- Copy the **Client ID** and **Client Secret** into your `.env`:

```bash
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
```

### 2. Configure `settings.py`

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # Optional: for JWT logout blacklisting
    "django_googler",
]

# Required if using DRF JWT endpoints
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}

# Required: Get these from Google Cloud Console
GOOGLE_OAUTH_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
GOOGLE_OAUTH_CLIENT_SECRET = "your-client-secret"

# Update for production
GOOGLE_OAUTH_REDIRECT_URIS = [
    "http://localhost:8000/api/auth/google/callback/",
    "http://localhost:8000/auth/google/callback/",
]

# Recommended in production: restrict allowed custom redirect_uri parameters
# GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS = [
#     "https://app.yourdomain.com/auth/callback",
# ]
```

### 3. Add URLs

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    # Django REST Framework OAuth API views (JWT)
    path("api/auth/", include("django_googler.urls.api")),
    # Standard Django session OAuth views
    path("auth/", include("django_googler.urls.default")),
]
```

Both URL groups are optional — mount whichever you need (or both).

**Django REST Framework API Endpoints:**
- `GET /api/auth/google/login/` — Get Google OAuth authorization URL + signed state
- `POST /api/auth/google/callback/` — Exchange authorization code for JWT tokens + user info
- `POST /api/auth/google/refresh/` — Refresh JWT access token (`TokenRefreshView`)
- `POST /api/auth/google/logout/` — Blacklist JWT refresh token & optionally revoke Google token (requires JWT)
- `GET /api/auth/me/` — Get current authenticated user (requires JWT)

**Standard Django Session Endpoints:**
- `GET /auth/google/login/` — Redirects to Google OAuth consent screen (supports `?next=/path/` with open-redirect protection and automatic PKCE)
- `GET /auth/google/callback/` — Handles Google's callback, logs the user into Django's session, and redirects to `next` / `LOGIN_REDIRECT_URL` (or `LOGIN_URL?error=...` on failure)

### 4. Run Migrations

```bash
python manage.py migrate
```

## Usage

### Frontend SPA Flow (DRF + JWT)

**1. Get Google OAuth URL**

```javascript
const redirectUri = encodeURIComponent("http://localhost:3000/auth/callback");
const response = await fetch(
  `http://localhost:8000/api/auth/google/login/?redirect_uri=${redirectUri}`
);
const { authorization_url } = await response.json();

// Redirect user to Google
window.location.href = authorization_url;
```

> **Tip:** The `redirect_uri` and requested `scopes` are cryptographically bound into the signed `state` token, preventing tampering and making callback handling simpler. Client-side PKCE is also supported by passing `code_challenge` (+ `code_challenge_method=S256`) on login and `code_verifier` on callback.

**2. Handle Google's Callback**

After Google redirects back to your frontend with `?code=...&state=...`:

```javascript
const params = Object.fromEntries(new URL(window.location.href).searchParams);

const response = await fetch("http://localhost:8000/api/auth/google/callback/", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    code: params.code,
    state: params.state,
  }),
});

const data = await response.json();
/*
{
  "access": "eyJ0eXAiOiJKV1Q...",
  "refresh": "eyJ0eXAiOiJKV1Q...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "user",
    "first_name": "John",
    "last_name": "Doe"
  }
}
*/
```

**3. Make Authenticated Requests**

```javascript
const response = await fetch("http://localhost:8000/api/auth/me/", {
  headers: {
    Authorization: `Bearer ${accessToken}`,
  },
});
```

**4. Refresh JWT Access Token**

```javascript
const response = await fetch("http://localhost:8000/api/auth/google/refresh/", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ refresh: refreshToken }),
});
```

**5. Logout**

```javascript
await fetch("http://localhost:8000/api/auth/google/logout/", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${accessToken}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ refresh: refreshToken }),
});
```

### Standard Django Template Flow

```html
<a href="{% url 'django_googler:google-login' %}?next=/dashboard/">
    Sign in with Google
</a>
```

## Calling Google APIs on Behalf of Users

Use `GoogleOAuthService.get_credentials(user)` (recommended for `google-api-python-client`) or `GoogleOAuthService.get_valid_token(user)`. Both automatically refresh tokens that are expired or within `GOOGLE_OAUTH_TOKEN_REFRESH_LEEWAY` seconds of expiring:

```python
from django_googler.services import GoogleOAuthService


def calendar_events(request):
    # Option 1: Ready-to-use google.oauth2.credentials.Credentials
    creds = GoogleOAuthService.get_credentials(request.user)
    if creds:
        from googleapiclient.discovery import build

        service = build("calendar", "v3", credentials=creds)
        return service.events().list(calendarId="primary").execute()

    # Option 2: Raw access token for requests/httpx
    access_token, expiry = GoogleOAuthService.get_valid_token(request.user)
    if access_token:
        import requests

        resp = requests.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        return resp.json()
```

## Pre-configured YouTube Connect Views

For incremental YouTube OAuth scope grants, mount any of the built-in views from `django_googler.connect.youtube`:

```python
from django.urls import path
from django_googler.connect.youtube import (
    YouTubeManageConnectAPIView,
    YouTubeReadOnlyConnectAPIView,
)

urlpatterns = [
    path("api/auth/youtube/readonly/", YouTubeReadOnlyConnectAPIView.as_view()),
    path("api/auth/youtube/manage/", YouTubeManageConnectAPIView.as_view()),
]
```

## Signals

Hook into OAuth lifecycle events with Django signals:

```python
from django.dispatch import receiver
from django_googler.signals import (
    google_oauth_failed,
    google_oauth_logout,
    google_oauth_success,
    google_oauth_token_refreshed,
)


@receiver(google_oauth_success)
def on_oauth_success(
    sender, user, scopes, credentials, user_created, user_info, **kwargs
):
    extra_metadata = kwargs.get("extra_metadata")
    if user_created:
        # Run onboarding logic for new users
        pass


@receiver(google_oauth_failed)
def on_oauth_failed(sender, error, request, exception, **kwargs):
    pass


@receiver(google_oauth_token_refreshed)
def on_token_refreshed(sender, user, token, **kwargs):
    pass


@receiver(google_oauth_logout)
def on_logout(sender, user, request, **kwargs):
    pass
```

## Configuration Reference

All settings are read dynamically from `django.conf.settings` (so `@override_settings` in tests works out of the box).

| Setting | Default | Description |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | `""` | **Required.** Google OAuth Client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `""` | **Required.** Google OAuth Client Secret |
| `GOOGLE_OAUTH_REDIRECT_URIS` | `["http://localhost:8000/api/auth/google/callback/"]` | Default redirect URIs |
| `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS` | `None` | Optional strict allowlist for custom `redirect_uri` parameters |
| `GOOGLE_OAUTH_SCOPES` | `["openid", "...userinfo.email", "...userinfo.profile"]` | Default OAuth scopes |
| `GOOGLE_OAUTH_REQUIRE_VERIFIED_EMAIL` | `True` | Reject Google accounts with `email_verified=False` |
| `GOOGLE_OAUTH_USE_PKCE` | `True` | Enable automatic PKCE (S256) on session-based Django views |
| `GOOGLE_OAUTH_STATE_MAX_AGE` | `600` | Signed state token expiration in seconds |
| `GOOGLE_OAUTH_SAVE_TOKENS_TO_DB` | `True` | Persist Google tokens in `GoogleOAuthToken` model |
| `GOOGLE_OAUTH_RETURN_TOKENS` | `False` | Include `google_tokens` in DRF callback response |
| `GOOGLE_OAUTH_STORE_TOKENS` | `False` | Store tokens in Django session |
| `GOOGLE_OAUTH_REVOKE_ON_LOGOUT` | `False` | Revoke Google token on API logout |
| `GOOGLE_OAUTH_TOKEN_REFRESH_LEEWAY` | `60` | Proactively refresh tokens expiring within N seconds |
| `GOOGLE_OAUTH_REQUEST_TIMEOUT` | `10` | Timeout (seconds) for outbound HTTP calls (e.g. token revocation) |
| `GOOGLE_OAUTH_USER_SERIALIZER` | `None` | Custom DRF user serializer (dotted path or class) for `/me/` and callback |
| `GOOGLE_OAUTH_AUTH_BACKEND` | `None` | Custom Django auth backend path for session login |
| `DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK` | `False` | Allow `GET` on DRF callback endpoint (dev/testing only) |
| `GOOGLE_OAUTH_LOGIN_THROTTLE_RATE` | `"30/hour"` | DRF throttle rate for login endpoint |
| `GOOGLE_OAUTH_CALLBACK_THROTTLE_RATE` | `"100/hour"` | DRF throttle rate for callback endpoint |

## Custom User Models

`django-googler` automatically adapts to custom `AUTH_USER_MODEL` configurations (email-only users, custom PKs, custom `USERNAME_FIELD`, etc.). You can also customize the serialized user payload returned by `/api/auth/me/` and `/api/auth/google/callback/` via:

```python
GOOGLE_OAUTH_USER_SERIALIZER = "myapp.serializers.MyUserSerializer"
```

## License

MIT License

## Support

[GitHub Issues](https://github.com/jmitchel3/django-googler/issues)
