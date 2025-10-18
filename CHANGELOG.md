# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.0.4]: https://github.com/jmitchel3/django-googler/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/jmitchel3/django-googler/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/jmitchel3/django-googler/releases/tag/v0.0.2
