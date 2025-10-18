from rest_framework.throttling import AnonRateThrottle

from django_googler.defaults import (
    GOOGLE_OAUTH_CALLBACK_THROTTLE_RATE,
    GOOGLE_OAUTH_LOGIN_THROTTLE_RATE,
)

# ============================================================================
# Throttle Classes
# ============================================================================


class GoogleOAuthLoginThrottle(AnonRateThrottle):
    """Throttle for OAuth login endpoint."""

    rate = GOOGLE_OAUTH_LOGIN_THROTTLE_RATE


class GoogleOAuthCallbackThrottle(AnonRateThrottle):
    """Throttle for OAuth callback endpoint."""

    rate = GOOGLE_OAUTH_CALLBACK_THROTTLE_RATE
