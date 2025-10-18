# Django Googler

Django Googler is a simple way to integrate Google OAuth Platform with your Django project. It provides both **Django Rest Framework** API views and **regular Django views** for handling Google OAuth authentication flows.

## Features

- 🔐 **Google OAuth 2.0 Integration** - Complete OAuth flow implementation
- 🎯 **Dual View Support** - Both DRF API views and regular Django views
- 🔧 **Service Layer Architecture** - Clean separation of business logic
- ⚙️ **Highly Configurable** - Override settings via Django settings
- 🛡️ **CSRF Protection** - Built-in state verification
- 👥 **Automatic User Management** - Create or update users from Google info
- 📦 **Zero Configuration** - Works out of the box with sensible defaults
- 🚦 **Rate Limiting** - Built-in throttling to prevent abuse
- ✅ **Settings Validation** - Django system checks for configuration
- 📝 **DRF Serializers** - Proper request/response validation

## Installation

```bash
pip install django-googler
```

## Dependencies

- [Python 3.12+](https://www.python.org/)
- [Django 5.2+](https://docs.djangoproject.com/)
- [Django Rest Framework 3.15+](https://www.django-rest-framework.org/)
- [google-auth 2.41+](https://pypi.org/project/google-auth/)
- [google-auth-oauthlib 1.2+](https://pypi.org/project/google-auth-oauthlib/)

## Quick Start

### 1. Add to Installed Apps

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "rest_framework.authtoken",  # Required for API token authentication
    "django_googler",
]
```

### 2. Configure Google OAuth Settings

Get your credentials from [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

```python
# settings.py
import os

# Required: Get these from Google Cloud Console
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

# Optional: Override default redirect URIs
GOOGLE_OAUTH_REDIRECT_URIS = [
    "http://localhost:8000/auth/google/callback/",
    "http://localhost:8000/api/auth/google/callback/",
]

# Optional: Override default scopes
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# Optional: Store OAuth tokens in session (useful for making Google API calls from backend)
# Default: False
GOOGLE_OAUTH_STORE_TOKENS = True

# Optional: Return Google tokens in API callback response (for frontend Google API calls)
# Default: False (only returns DRF token)
GOOGLE_OAUTH_RETURN_TOKENS = False

# Optional: Login URL for error redirects
# Default: "/login/"
LOGIN_URL = "/admin/login/"
```

### 3. Run Migrations

```bash
python manage.py migrate
```

This creates the necessary database tables for the authtoken app.

### 4. Add URL Patterns

Choose between **Regular Django Views** or **Django Rest Framework API Views** (or use both!):

#### Regular Django Views

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path("auth/", include("django_googler.urls.default")),
]
```

Or explicitly:
```python
# urls.py
from django.urls import path
from django_googler import GoogleOAuthLoginView, GoogleOAuthCallbackView

urlpatterns = [
    path("auth/google/login/", GoogleOAuthLoginView.as_view(), name="google-login"),
    path(
        "auth/google/callback/",
        GoogleOAuthCallbackView.as_view(),
        name="google-callback",
    ),
]
```

#### Django Rest Framework API Views

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path("api/auth/", include("django_googler.urls.drf")),
]
```

Or explicitly:
```python
# urls.py
from django.urls import path
from django_googler import (
    GoogleOAuthLoginAPIView,
    GoogleOAuthCallbackAPIView,
    CurrentUserAPIView,
    GoogleOAuthLogoutAPIView,
)

urlpatterns = [
    path(
        "api/auth/google/login/",
        GoogleOAuthLoginAPIView.as_view(),
        name="google-login-api",
    ),
    path(
        "api/auth/google/callback/",
        GoogleOAuthCallbackAPIView.as_view(),
        name="google-callback-api",
    ),
    path("api/auth/me/", CurrentUserAPIView.as_view(), name="current-user"),
    path("api/auth/logout/", GoogleOAuthLogoutAPIView.as_view(), name="logout"),
]
```

## Usage

### Regular Django Views (Browser Redirects)

1. **Redirect users to the login view:**
   ```html
   <a href="{% url 'django_googler:google-login' %}?next=/dashboard/">Sign in with Google</a>
   ```

2. **Users are redirected to Google for authentication**

3. **After authentication, users are redirected back and automatically logged in**

The regular Django views will:
- Create a new user if they don't exist
- Update existing user information
- Log the user into Django's authentication system
- Redirect to the `next` parameter or `/` by default

### Django Rest Framework API Views (JSON Responses)

1. **GET the login endpoint to get the authorization URL:**
   ```bash
   curl http://localhost:8000/api/auth/google/login/
   ```

   Response:
   ```json
   {
       "authorization_url": "https://accounts.google.com/o/oauth2/auth?...",
       "state": "random-state-string"
   }
   ```

2. **Redirect users to the `authorization_url`**

3. **After Google redirects back with the authorization code, POST it to the callback:**
   ```bash
   curl -X POST http://localhost:8000/api/auth/google/callback/ \
     -H "Content-Type: application/json" \
     -d '{
       "code": "4/0AY0e-g...",
       "state": "random-state-string",
       "redirect_uri": "http://localhost:3000/auth/callback"
     }'
   ```

   Response (user is created/logged in and API token returned):
   ```json
   {
       "token": "drf_api_token_abc123...",
       "user": {
           "id": 1,
           "email": "user@example.com",
           "username": "user",
           "first_name": "John",
           "last_name": "Doe"
       }
   }
   ```

   **Note:** Google tokens are **not** included by default. If your frontend needs to call Google APIs directly (Calendar, Drive, Gmail, etc.), set `GOOGLE_OAUTH_RETURN_TOKENS = True` in settings to include them in the response.

4. **Use the returned token for authenticated requests:**
   ```bash
   curl http://localhost:8000/api/protected/ \
     -H "Authorization: Token drf_api_token_abc123..."
   ```

### Additional DRF Endpoints

#### Get Current User

```bash
curl http://localhost:8000/api/auth/me/ \
  -H "Authorization: Token your-token-here"
```

Response:
```json
{
    "id": 1,
    "email": "user@example.com",
    "username": "user",
    "first_name": "John",
    "last_name": "Doe"
}
```

#### Logout

```bash
curl -X POST http://localhost:8000/api/auth/logout/ \
  -H "Authorization: Token your-token-here"
```

Response:
```json
{
    "message": "Logged out successfully"
}
```

This will:
- Delete the user's DRF authentication token
- Clear all OAuth session data (access tokens, refresh tokens, etc.)

## Advanced Usage

### Using the Service Layer

You can use the service layer directly in your own views or logic:

```python
from django_googler import GoogleOAuthService, UserService, OAuthFlowService

# Verify and process OAuth credentials
credentials_data = GoogleOAuthService.process_credentials(credentials)

# Create or update user from OAuth info
user = UserService.get_or_create_user(
    email="user@example.com",
    name="John Doe",
    google_id="1234567890",
    picture="https://...",
)

# Manage OAuth flow state
OAuthFlowService.store_state(request, state)
is_valid = OAuthFlowService.verify_state(request, state)
OAuthFlowService.clear_state(request)
```

### Custom Scopes

Request additional Google API scopes:

```html
<!-- In your template -->
<a href="{% url 'django_googler:google-login' %}?scopes=openid,email,profile,https://www.googleapis.com/auth/calendar">
    Sign in with Google Calendar Access
</a>
```

Or for API views:
```bash
curl "http://localhost:8000/api/auth/google/login/?scopes=openid,email,profile"
```

### Storing OAuth Tokens

If you want to make API calls to Google on behalf of users, enable token storage:

```python
# settings.py
GOOGLE_OAUTH_STORE_TOKENS = True
```

Then access tokens in your views:
```python
def my_view(request):
    access_token = request.session.get("google_access_token")
    refresh_token = request.session.get("google_refresh_token")
    token_expiry = request.session.get("google_token_expiry")

    # Use tokens to make Google API calls
    # ...
```

### Extending User Creation

If you need to store additional user information (like `google_id` or `picture`), you can:

1. **Create a custom user model:**
   ```python
   from django.contrib.auth.models import AbstractUser


   class User(AbstractUser):
       google_id = models.CharField(max_length=255, blank=True)
       picture = models.URLField(blank=True)
   ```

2. **Or create a user profile model:**
   ```python
   class UserProfile(models.Model):
       user = models.OneToOneField(User, on_delete=models.CASCADE)
       google_id = models.CharField(max_length=255, blank=True)
       picture = models.URLField(blank=True)
   ```

3. **Override the UserService (recommended):**
   ```python
   from django_googler.services import UserService as BaseUserService


   class CustomUserService(BaseUserService):
       @staticmethod
       def _create_new_user(
           email,
           name=None,
           given_name=None,
           family_name=None,
           google_id=None,
           picture=None,
       ):
           user = super()._create_new_user(
               email, name, given_name, family_name, google_id, picture
           )
           # Store additional fields
           if google_id:
               user.google_id = google_id
           if picture:
               user.picture = picture
           user.save()
           return user
   ```

## Architecture

Django Googler follows a clean service-layer architecture:

- **`views.py`** - View layer (DRF and Django views)
- **`services.py`** - Business logic layer
  - `GoogleOAuthService` - OAuth token processing
  - `UserService` - User creation and management
  - `OAuthFlowService` - OAuth state management
- **`platform_client.py`** - Google OAuth client wrapper
- **`defaults.py`** - Configuration and settings

## Configuration Reference

All settings are optional and have sensible defaults:

| Setting | Default | Description |
|---------|---------|-------------|
| `GOOGLE_OAUTH_CLIENT_ID` | `""` | Google OAuth Client ID (required) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `""` | Google OAuth Client Secret (required) |
| `GOOGLE_OAUTH_REDIRECT_URIS` | `["http://localhost:8000/api/googler/callback"]` | Authorized redirect URIs |
| `GOOGLE_OAUTH_SCOPES` | `["openid", "email", "profile"]` | OAuth scopes to request |
| `GOOGLE_OAUTH_STORE_TOKENS` | `False` | Store tokens in session |
| `GOOGLE_OAUTH_RETURN_TOKENS` | `False` | Return Google tokens in API response |
| `LOGIN_URL` | `"/login/"` | Redirect URL on OAuth errors |

### Rate Limiting

Django Googler includes built-in rate limiting for OAuth endpoints:
- Login endpoint: 10 requests per hour
- Callback endpoint: 20 requests per hour

You can customize these rates in your Django REST Framework settings:

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    }
}
```

## Error Handling

The views handle various error scenarios:

| Error Code | Description |
|------------|-------------|
| `oauth_init_failed` | Failed to initiate OAuth flow |
| `missing_code` | Authorization code not provided by Google |
| `invalid_state` | CSRF state verification failed |
| `no_email` | Google didn't provide an email address |
| `oauth_callback_failed` | General callback processing error |

Access errors via query parameters:
```python
def login_view(request):
    error = request.GET.get("error")
    if error == "invalid_state":
        messages.error(request, "Security check failed. Please try again.")
```

## Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the **Google+ API** and **People API**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Configure **Authorized redirect URIs**:
   - For local development: `http://localhost:8000/auth/google/callback/`
   - For production: `https://yourdomain.com/auth/google/callback/`
6. Copy the **Client ID** and **Client Secret** to your Django settings

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues and questions, please use the [GitHub issue tracker](https://github.com/jmitchel3/django-googler/issues).
