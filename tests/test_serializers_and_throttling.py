"""
Tests for serializers and throttling classes.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import serializers

from django_googler.serializers import (
    GoogleOAuthCallbackRequestSerializer,
    GoogleOAuthCallbackResponseSerializer,
    GoogleOAuthLoginResponseSerializer,
    UserSerializer,
    get_user_serializer_class,
)
from django_googler.throttling import (
    GoogleOAuthCallbackThrottle,
    GoogleOAuthLoginThrottle,
)

User = get_user_model()


class CustomTestUserSerializer(serializers.Serializer):
    """Custom serializer used to test GOOGLE_OAUTH_USER_SERIALIZER override."""

    custom_email = serializers.EmailField(source="email")


@pytest.mark.django_db
class TestSerializers:
    """Test DRF serializers."""

    def test_user_serializer_does_not_mutate_class_meta(self):
        user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
        )
        serializer = UserSerializer(user)
        assert serializer.data == {
            "id": user.id,
            "email": "alice@example.com",
            "username": "alice",
            "first_name": "Alice",
            "last_name": "Smith",
        }
        # Class-level Meta should remain unmutated
        assert UserSerializer.Meta.model is None
        assert UserSerializer.Meta.fields == []

    @override_settings(
        GOOGLE_OAUTH_USER_SERIALIZER=(
            "tests.test_serializers_and_throttling.CustomTestUserSerializer"
        )
    )
    def test_get_user_serializer_class_from_dotted_path(self):
        cls = get_user_serializer_class()
        assert cls is CustomTestUserSerializer

        user = User.objects.create_user(username="bob", email="bob@example.com")
        response_serializer = GoogleOAuthCallbackResponseSerializer(
            {"access": "a", "refresh": "r", "user": user}
        )
        assert response_serializer.data["user"] == {"custom_email": "bob@example.com"}

    @override_settings(GOOGLE_OAUTH_USER_SERIALIZER=CustomTestUserSerializer)
    def test_get_user_serializer_class_direct_class(self):
        assert get_user_serializer_class() is CustomTestUserSerializer

    def test_login_and_callback_request_serializers(self):
        login_ser = GoogleOAuthLoginResponseSerializer(
            data={
                "authorization_url": "https://accounts.google.com/o/oauth2/auth",
                "state": "s",
            }
        )
        assert login_ser.is_valid()

        cb_ser = GoogleOAuthCallbackRequestSerializer(
            data={
                "code": "auth-code",
                "state": "signed-state",
                "redirect_uri": "http://localhost:3000/callback",
                "code_verifier": "pkce-verifier-123",
            }
        )
        assert cb_ser.is_valid()
        assert cb_ser.validated_data["code_verifier"] == "pkce-verifier-123"


class TestThrottling:
    """Test dynamic throttle rate resolution."""

    @override_settings(
        GOOGLE_OAUTH_LOGIN_THROTTLE_RATE="5/minute",
        GOOGLE_OAUTH_CALLBACK_THROTTLE_RATE="15/minute",
    )
    def test_throttles_resolve_rates_dynamically(self):
        assert GoogleOAuthLoginThrottle().get_rate() == "5/minute"
        assert GoogleOAuthCallbackThrottle().get_rate() == "15/minute"

    def test_subclass_rate_override_takes_precedence(self):
        class CustomLoginThrottle(GoogleOAuthLoginThrottle):
            rate = "2/minute"

        assert CustomLoginThrottle().get_rate() == "2/minute"
