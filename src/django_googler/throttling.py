from rest_framework.throttling import AnonRateThrottle

# ============================================================================
# Throttle Classes
# ============================================================================


class GoogleOAuthLoginThrottle(AnonRateThrottle):
    """Throttle for OAuth login endpoint - 10 requests per hour."""

    rate = "10/hour"


class GoogleOAuthCallbackThrottle(AnonRateThrottle):
    """Throttle for OAuth callback endpoint - 20 requests per hour."""

    rate = "20/hour"
