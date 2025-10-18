# Django Googler

Simple Google OAuth authentication for Django. Returns JWT tokens for your API.

## What It Does

1. User clicks "Sign in with Google"
2. Google handles authentication
3. Your Django app gets JWT tokens + user info
4. Use JWT tokens for authenticated API requests

## Installation

```bash
uv add django-googler
```

or

```bash
pip install django-googler
```

## Quick Setup

### 1. Add to `settings.py`

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # Optional: for logout
    "django_googler",
]

# Get these from Google Cloud Console
GOOGLE_OAUTH_CLIENT_ID = "your-client-id"
GOOGLE_OAUTH_CLIENT_SECRET = "your-client-secret"
```

### 2. Add URLs

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path("api/auth/", include("django_googler.urls.drf")),
]
```

### 3. Run Migrations

```bash
python manage.py migrate
```

Done! You now have these endpoints:
- `GET /api/auth/google/login/` - Get Google OAuth URL
- `POST /api/auth/google/callback/` - Exchange code for JWT tokens
- `GET /api/auth/me/` - Get current user (requires JWT)
- `POST /api/auth/logout/` - Logout (requires JWT)

## Usage

### Frontend Flow

**1. Get Google OAuth URL**

```javascript
const redirect_uri = 'http://localhost:3000/auth/callback';
const apiBaseUrl = 'http://localhost:8000';
const loginApiEndpoint = `${apiBaseUrl}/api/auth/google/login/`;
const requestUrl = `${loginApiEndpoint}?redirect_uri=${redirect_uri}`;
const response = await fetch(requestUrl);
const data = await response.json();
// data = { "authorization_url": "https://accounts.google.com/...", "state": "..." }

// Redirect user to Google
window.location.href = data.authorization_url;
```

**2. Handle Google's Callback**

After Google redirects back to your frontend with a `code` and `state`:

```javascript
// Get the callback data from the current URL
const currentUrl = new URL(window.location.href);
const googleCallbackData = Object.fromEntries(currentUrl.searchParams);

// Send the callback data to the backend
const apiBaseUrl = 'http://localhost:8000';
const callbackApiEndpoint = `${apiBaseUrl}/api/auth/google/callback/`;
const response = await fetch(callbackApiEndpoint, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(googleCallbackData)
});

const responseData = await response.json();
/* responseData = {
  "access": "eyJ0eXAiOiJKV1Q...",  // JWT access token (short-lived)
  "refresh": "eyJ0eXAiOiJKV1Q...", // JWT refresh token (long-lived)
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "user",
    "first_name": "John",
    "last_name": "Doe"
  }
} */

// Save tokens
localStorage.setItem('access_token', responseData.access);
localStorage.setItem('refresh_token', responseData.refresh);
```

**3. Make Authenticated Requests**

```javascript
const apiBaseUrl = 'http://localhost:8000';
const meApiEndpoint = `${apiBaseUrl}/api/auth/me/`;
const response = await fetch(meApiEndpoint, {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
  }
});

const responseData = await response.json();
/* responseData = {
  "id": 1,
  "email": "user@example.com",
  "username": "user",
  "first_name": "John",
  "last_name": "Doe"
} */
```

**4. Logout**

```javascript
const apiBaseUrl = 'http://localhost:8000';
const logoutApiEndpoint = `${apiBaseUrl}/api/auth/logout/`;
const response = await fetch(logoutApiEndpoint, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    refresh: localStorage.getItem('refresh_token')
  })
});

localStorage.removeItem('access_token');
localStorage.removeItem('refresh_token');
```

## Configuration

### Required Settings

```python
GOOGLE_OAUTH_CLIENT_ID = "your-client-id"
GOOGLE_OAUTH_CLIENT_SECRET = "your-client-secret"
```

### Optional Settings

```python
# Return Google tokens in callback response (for calling Google APIs from frontend)
# Default: False
GOOGLE_OAUTH_RETURN_TOKENS = False

# Revoke Google access on logout
# Default: False
GOOGLE_OAUTH_REVOKE_ON_LOGOUT = False

# Save Google OAuth tokens to database (for backend Google API calls)
# Default: True
GOOGLE_OAUTH_SAVE_TOKENS_TO_DB = True

# Request additional Google API scopes
# Default: ["openid", "email", "profile"]
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    # "https://www.googleapis.com/auth/calendar",  # Add if needed
]
```

## Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project
3. Enable **Google+ API**
4. Create **OAuth 2.0 Client ID** credentials
5. Add authorized redirect URIs:
   - Development: `http://localhost:8000/api/auth/google/callback/`
   - Production: `https://yourdomain.com/api/auth/google/callback/`
6. Copy Client ID and Secret to your Django settings

## Making Google API Calls

If your backend needs to call Google APIs on behalf of users:

```python
from django_googler.services import GoogleOAuthService


def my_view(request):
    # Get valid access token (auto-refreshes if expired)
    access_token, expiry = GoogleOAuthService.get_valid_token(request.user)

    if access_token:
        import requests

        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers=headers,
        )
        return response.json()
```

## Using Django Views (Instead of API)

If you prefer browser redirects over API calls:

```python
# urls.py
urlpatterns = [
    path("auth/", include("django_googler.urls.default")),
]
```

Then in your template:
```html
<a href="{% url 'django_googler:google-login' %}?next=/dashboard/">
    Sign in with Google
</a>
```

Users will be redirected to Google and back, then logged into Django's session.

## Architecture

- **Views** - Handle OAuth flow and return JWT tokens
- **Services** - Business logic for OAuth, users, and tokens
- **Models** - Store Google OAuth tokens in database

## License

MIT License

## Support

[GitHub Issues](https://github.com/jmitchel3/django-googler/issues)
