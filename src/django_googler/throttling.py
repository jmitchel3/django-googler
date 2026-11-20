"""
DRF throttle classes for django_googler OAuth endpoints.
"""

from rest_framework.throttling import AnonRateThrottle

from django_googler.defaults import get_django_google_setting


class GoogleOAuthLoginThrottle(AnonRateThrottle):
    """Throttle for OAuth login endpoint."""

    setting_name = "GOOGLE_OAUTH_LOGIN_THROTTLE_RATE"

    def get_rate(self):
        """Resolve throttle rate dynamically from settings unless overridden."""
        if getattr(self, "rate", None):
            return self.rate
        return get_django_google_setting(self.setting_name)


class GoogleOAuthCallbackThrottle(AnonRateThrottle):
    """Throttle for OAuth callback endpoint."""

    setting_name = "GOOGLE_OAUTH_CALLBACK_THROTTLE_RATE"

    def get_rate(self):
        """Resolve throttle rate dynamically from settings unless overridden."""
        if getattr(self, "rate", None):
            return self.rate
        return get_django_google_setting(self.setting_name)
