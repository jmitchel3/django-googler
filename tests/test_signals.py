"""
Tests for django_googler signals.
"""

from unittest.mock import MagicMock, Mock

import pytest
from django.contrib.auth import get_user_model

from django_googler.signals import google_oauth_success


User = get_user_model()


@pytest.mark.django_db
class TestGoogleOAuthSuccessSignal:
    """Tests for the google_oauth_success signal."""

    def test_signal_is_sent_on_oauth_success(self):
        """Test that the signal is sent with correct parameters."""
        # Create a receiver to track signal calls
        receiver_mock = Mock()

        # Connect the mock receiver to the signal
        google_oauth_success.connect(receiver_mock)

        try:
            # Create test data
            user = User.objects.create_user(
                username="testuser", email="test@example.com"
            )
            scopes = [
                "email",
                "profile",
                "https://www.googleapis.com/auth/youtube.readonly",
            ]
            credentials = MagicMock()
            credentials.token = "test_access_token"
            credentials.refresh_token = "test_refresh_token"
            credentials.scopes = scopes
            user_info = {"email": "test@example.com", "name": "Test User"}

            # Send the signal
            google_oauth_success.send(
                sender=self.__class__,
                user=user,
                scopes=scopes,
                credentials=credentials,
                user_created=True,
                user_info=user_info,
            )

            # Verify the receiver was called
            assert receiver_mock.called
            assert receiver_mock.call_count == 1

            # Verify the signal was called with correct arguments
            call_kwargs = receiver_mock.call_args[1]
            assert call_kwargs["user"] == user
            assert call_kwargs["scopes"] == scopes
            assert call_kwargs["credentials"] == credentials
            assert call_kwargs["user_created"] is True
            assert call_kwargs["user_info"] == user_info

        finally:
            # Disconnect the receiver
            google_oauth_success.disconnect(receiver_mock)

    def test_multiple_receivers_can_listen_to_signal(self):
        """Test that multiple receivers can listen to the same signal."""
        receiver1_mock = Mock()
        receiver2_mock = Mock()

        google_oauth_success.connect(receiver1_mock)
        google_oauth_success.connect(receiver2_mock)

        try:
            # Send the signal
            google_oauth_success.send(
                sender=self.__class__,
                user=Mock(),
                scopes=["email"],
                credentials=Mock(),
                user_created=False,
                user_info={},
            )

            # Both receivers should have been called
            assert receiver1_mock.called
            assert receiver2_mock.called

        finally:
            google_oauth_success.disconnect(receiver1_mock)
            google_oauth_success.disconnect(receiver2_mock)

    def test_signal_includes_scopes_information(self):
        """Test that scopes are properly passed to the signal."""
        received_scopes = []

        def scope_receiver(sender, scopes, **kwargs):
            received_scopes.extend(scopes)

        google_oauth_success.connect(scope_receiver)

        try:
            expected_scopes = [
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/youtube.readonly",
            ]

            # Send the signal with scopes
            google_oauth_success.send(
                sender=self.__class__,
                user=Mock(),
                scopes=expected_scopes,
                credentials=Mock(),
                user_created=False,
                user_info={},
            )

            # Verify scopes were received
            assert received_scopes == expected_scopes

        finally:
            google_oauth_success.disconnect(scope_receiver)

    @pytest.mark.django_db
    def test_signal_distinguishes_new_vs_existing_users(self):
        """Test that the signal properly indicates new vs existing users."""
        new_user_flags = []

        def user_created_receiver(sender, user_created, **kwargs):
            new_user_flags.append(user_created)

        google_oauth_success.connect(user_created_receiver)

        try:
            # Test with new user
            google_oauth_success.send(
                sender=self.__class__,
                user=Mock(),
                scopes=[],
                credentials=Mock(),
                user_created=True,
                user_info={},
            )

            # Test with existing user
            google_oauth_success.send(
                sender=self.__class__,
                user=Mock(),
                scopes=[],
                credentials=Mock(),
                user_created=False,
                user_info={},
            )

            # Verify both flags were received correctly
            assert new_user_flags == [True, False]

        finally:
            google_oauth_success.disconnect(user_created_receiver)
