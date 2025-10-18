# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.0.3]: https://github.com/jmitchel3/django-googler/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/jmitchel3/django-googler/releases/tag/v0.0.2
