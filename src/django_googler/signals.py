"""
Django signals for django_googler OAuth events.

This module defines custom signals that are sent during OAuth flows,
allowing you to hook into various stages of the authentication process.

Example::

    from django.dispatch import receiver
    from django_googler.signals import google_oauth_success

    @receiver(google_oauth_success)
    def on_oauth_success(sender, user, scopes, credentials, user_created, **kwargs):
        print(f"User {user} authenticated with scopes: {scopes}")
        if user_created:
            print("This is a new user!")
"""

import django.dispatch

# Signal sent after successful Google OAuth authentication.
# Kwargs:
#   sender: View class that handled the OAuth callback
#   user: Authenticated Django user instance
#   scopes: List of granted OAuth scopes (list[str])
#   credentials: Google OAuth Credentials object
#   user_created: bool indicating whether a new user was created
#   user_info: dict containing user info extracted from Google ID token
#   extra_metadata: Optional dict of custom metadata from signed state
google_oauth_success = django.dispatch.Signal()

# Signal sent when Google OAuth authentication fails during callback.
# Kwargs:
#   sender: View class that handled the OAuth callback
#   error: Short error code or message string
#   request: The Django/DRF request object
#   exception: Optional exception instance that caused the failure
google_oauth_failed = django.dispatch.Signal()

# Signal sent after a user's Google OAuth access token is refreshed.
# Kwargs:
#   sender: Service class that performed the refresh
#   user: Django user instance
#   token: Updated GoogleOAuthToken instance
google_oauth_token_refreshed = django.dispatch.Signal()

# Signal sent after a user logs out via the Google OAuth API logout endpoint.
# Kwargs:
#   sender: View class that handled the logout
#   user: Django user instance
#   request: The DRF request object
google_oauth_logout = django.dispatch.Signal()
