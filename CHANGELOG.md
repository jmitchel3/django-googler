# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-20

### Security
- **Open-redirect protection**: `GoogleOAuthLoginView` and `GoogleOAuthCallbackView` now validate `next` redirect URLs using Django's `url_has_allowed_host_and_scheme`.
- **Verified email enforcement**: `UserService.get_or_create_user` now enforces `email_verified=True` by default (`GOOGLE_OAUTH_REQUIRE_VERIFIED_EMAIL = True`) to prevent unverified-email account takeover.
- **Stable Google `sub` lookup**: Existing users are matched by `GoogleOAuthToken.google_id` first, then case-insensitive email, preventing duplicate accounts on email case or address changes.
- **Admin XSS fix**: `GoogleOAuthTokenAdmin.scopes_display` now escapes scope values with `format_html_join` instead of unescaped string concatenation.
- **Dedicated state signing salt & `redirect_uri` binding**: Signed OAuth state tokens now use a dedicated salt (`django_googler.oauth_state`), support configurable `GOOGLE_OAUTH_STATE_MAX_AGE`, and bind `redirect_uri` into the signed payload to prevent tampering.
- **Optional redirect URI allowlist**: Added `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS` setting and `http`/`https` scheme validation.
- **Safer token revocation**: `GoogleOAuthService.revoke_user_token` now sends tokens in the POST body (`data=`) instead of URL query parameters (`params=`), adds an explicit request timeout (`GOOGLE_OAUTH_REQUEST_TIMEOUT`), and prefers revoking the refresh token to invalidate the full grant.
- **Production error hygiene**: DRF views no longer expose raw internal exception strings (`detail`) in 500 responses when `DEBUG=False`.
- **PKCE support**: Automatic S256 PKCE enabled for session-based views (`GOOGLE_OAUTH_USE_PKCE = True`) and optional client-side PKCE (`code_challenge` / `code_verifier`) supported on DRF endpoints; fixed `google-auth-oauthlib >= 1.2` auto-PKCE mismatch on stateless API callbacks.

### Added
- **Dynamic settings**: All settings now resolve live from `django.conf.settings` (supporting `@override_settings` in tests) via `get_django_google_setting` and `app_settings`.
- **Google `Credentials` helpers**: Added `GoogleOAuthToken.to_credentials()` and `GoogleOAuthService.get_credentials(user)` for direct integration with `google-api-python-client`.
- **Configurable `UserSerializer`**: Added `GOOGLE_OAUTH_USER_SERIALIZER` setting and `get_serializer_class()` hooks on `CurrentUserAPIView` and `GoogleOAuthCallbackBaseAPIView`.
- **New signals**: Added `google_oauth_failed`, `google_oauth_token_refreshed`, and `google_oauth_logout` signals; `extra_metadata` from signed state is now passed to `google_oauth_success`.
- **Token refresh improvements**: Added `leeway` parameter to `GoogleOAuthToken.is_expired()` and `GOOGLE_OAUTH_TOKEN_REFRESH_LEEWAY` (default 60s), atomic row locking (`select_for_update`), and persistence of rotated refresh/ID tokens.
- **Admin enhancements**: Added bulk `Refresh selected tokens` and `Revoke and delete selected tokens` actions, dynamic `get_search_fields` for custom user models, and `list_select_related`.
- **Additional system checks**: Added `E003`, `E004`, and `W002` checks for misconfigured setting types and production `DJANGO_GOOGLER_ALLOW_GET_ON_DRF_CALLBACK`.
- **PEP 561 typing marker**: Added `src/django_googler/py.typed`.

### Fixed
- Fixed `platform_client.py` to use `GOOGLE_OAUTH_TOKEN_URI` (`https://oauth2.googleapis.com/token`) instead of the legacy `accounts.google.com/o/oauth2/token` endpoint.
- Fixed `UserSerializer` mutating shared class-level `Meta` across requests and assuming primary key is always named `"id"`.
- Fixed `UserService._create_new_user` dropping `given_name` when `family_name` was omitted, checking User fields instead of Profile fields when updating `user.profile`, and generating invalid usernames from emails containing special characters.
- Fixed `_make_aware` to anchor naive Google UTC expiry timestamps in UTC rather than Django's local `TIME_ZONE`.
- Fixed session-based callback flow not passing originally requested `scopes` during token exchange.
- Fixed `views_default.py` caching `LOGIN_URL` / `LOGIN_REDIRECT_URL` at import time and hardcoding `ModelBackend`.
- Fixed custom User model crashes in `__str__`, logging, and Django Admin when `email` or `username` fields are absent.
- Fixed README endpoint typos (`/api/auth/logout/` -> `/api/auth/google/logout/`, `/api/googler/callback` -> `/api/auth/google/callback/`).

## [0.0.4] - 2025-10-18

### Added
- **Database Token Storage**: Google OAuth tokens are now persistently stored in the database
  - New `GoogleOAuthToken` model to store access tokens, refresh tokens, and metadata
  - Automatic token storage when users authenticate (enabled by default via `GOOGLE_OAUTH_SAVE_TOKENS_TO_DB`)
  - One-to-one relationship with Django User model
  - Stores token expiry, scopes, Google ID, and ID token
- **Token Management Service Methods**:
  - `GoogleOAuthService.save_user_token()` - Save or update user tokens
  - `GoogleOAuthService.get_user_token()` - Retrieve user's stored token
  - `GoogleOAuthService.refresh_user_token()` - Automatically refresh expired tokens
  - `GoogleOAuthService.revoke_user_token()` - Revoke and delete user tokens
  - `GoogleOAuthService.get_valid_token()` - Get valid token with auto-refresh
- **Django Admin Interface** for managing OAuth tokens:
  - View all user tokens with status indicators (Valid/Expired/Invalid)
  - Token preview with truncated display for security
  - Scope management and visibility
  - Search by user email, username, or Google ID
  - Filter by creation date, update date, and expiry
- **New Configuration Settings**:
  - `GOOGLE_OAUTH_SAVE_TOKENS_TO_DB` (default: `True`) - Save tokens to database
  - `GOOGLE_OAUTH_REVOKE_ON_LOGOUT` (default: `False`) - Revoke tokens on logout
  - `GOOGLE_OAUTH_STORE_TOKENS` (default: `False`) - Store tokens in session (legacy)
- **Token Helper Methods** on `GoogleOAuthToken` model:
  - `is_expired()` - Check if access token is expired
  - `has_scope()` - Check if token has a specific OAuth scope
  - `get_scopes_list()` - Get list of granted scopes
  - `is_valid` property - Check if token is valid and not expired
  - `can_refresh` property - Check if token can be refreshed

### Changed
- Views now automatically save OAuth tokens to database when users authenticate
- Logout endpoint can optionally revoke Google OAuth tokens if `GOOGLE_OAUTH_REVOKE_ON_LOGOUT` is enabled
- Token storage is now database-first instead of session-only

### Security
- Tokens are now persistently stored in the database for better token lifecycle management
- Token refresh capability allows long-term API access without re-authentication
- Optional token revocation on logout for enhanced security

### Migration
- New migration `0001_initial` creates the `GoogleOAuthToken` table
- Run `python manage.py migrate` to apply the new database schema
- Existing installations will need to run migrations to use token storage features

## [0.0.3] - 2025-10-18

### Fixed
- Fixed URL name conflicts between default and DRF URL configs by adding proper app namespaces
- Fixed incorrect type hints in `platform_client.py` (changed to use `Optional` and `Tuple`)
- Fixed `get_google_auth_url()` return type to properly reflect tuple return value
- Added proper DRF serializers to API views for request/response validation

### Added
- Rate limiting/throttling on OAuth endpoints (10/hour for login, 20/hour for callback)
- Current user endpoint (`/api/auth/google/me/`) for authenticated user info
- Logout endpoint (`/api/auth/google/logout/`) to clear tokens and session data
- Django system checks for validating OAuth configuration settings
- `apps.py` and `checks.py` for proper Django app configuration
- `serializers.py` with comprehensive DRF serializers:
  - `GoogleOAuthLoginResponseSerializer`
  - `GoogleOAuthCallbackRequestSerializer`
  - `GoogleOAuthCallbackResponseSerializer`
  - `UserSerializer`
  - `GoogleTokensSerializer`

### Changed
- URL app names: `django_googler_default` → `django_googler`, `django_googler_drf` → `django_googler_api`
- All `reverse()` calls now use namespaced URLs (e.g., `django_googler:google-callback`)
- API views now properly validate input/output using serializers

### Security
- Added rate limiting to prevent abuse of OAuth endpoints
- Added validation for required OAuth settings at startup

## [0.0.2] - 2024-XX-XX

### Added
- Initial release with DRF support
- Google OAuth login and callback views
- Session-based authentication
- Basic OAuth flow implementation

[0.1.0]: https://github.com/jmitchel3/django-googler/compare/v0.0.20...v0.1.0
[0.0.4]: https://github.com/jmitchel3/django-googler/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/jmitchel3/django-googler/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/jmitchel3/django-googler/releases/tag/v0.0.2
