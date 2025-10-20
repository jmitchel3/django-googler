"""
Django signals for django_googler OAuth events.

This module defines custom signals that are sent during OAuth flows,
allowing you to hook into various stages of the authentication process.

Example:
    from django.dispatch import receiver
    from django_googler.signals import google_oauth_success

    @receiver(google_oauth_success)
    def on_oauth_success(sender, user, scopes, credentials, user_created, **kwargs):
        print(f"User {user.email} authenticated with scopes: {scopes}")

        if user_created:
            print("This is a new user!")

        # You can access the Google credentials to make API calls
        # credentials.token, credentials.refresh_token, etc.
"""

import django.dispatch

# Signal sent after successful Google OAuth authentication
google_oauth_success = django.dispatch.Signal()
"""
Signal sent after a user successfully completes Google OAuth authentication.

Arguments:
    sender: The class that handled the OAuth callback (usually a view class)
    user: The Django user instance that was authenticated
    scopes: List of OAuth scopes that were granted (list of strings)
    credentials: The Google OAuth credentials object
    user_created: Boolean indicating if this was a new user (True) or existing (False)
    user_info: Dictionary containing user information from Google

Example:
    from django.dispatch import receiver
    from django_googler.signals import google_oauth_success

    @receiver(google_oauth_success)
    def handle_oauth_success(sender, user, scopes, credentials, user_created, user_info, **kwargs):
        print(f"OAuth success for {user.email}")
        print(f"Scopes: {', '.join(scopes)}")

        if user_created:
            # Handle new user setup
            print("Setting up new user...")

        if 'https://www.googleapis.com/auth/youtube.readonly' in scopes:
            # User granted YouTube access
            print("User has YouTube access!")
"""
