import logging

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

logger = logging.getLogger(__name__)


class SignedStateOAuthMixin:
    """
    Mixin for handling OAuth state with cryptographic signing instead of sessions.

    This allows state verification to work across different domains without
    relying on session cookies.
    """

    # State tokens expire after 10 minutes (600 seconds)
    STATE_MAX_AGE = 600

    @staticmethod
    def sign_state(state: str) -> str:
        """
        Sign the OAuth state using Django's signing framework with timestamp.

        Args:
            state: The state string to sign

        Returns:
            Signed state string with timestamp
        """
        signer = TimestampSigner()
        return signer.sign(state)

    @staticmethod
    def verify_signed_state(signed_state: str) -> tuple[bool, str | None]:
        """
        Verify and extract the original state from a signed state.

        Args:
            signed_state: The signed state string to verify

        Returns:
            Tuple of (is_valid, original_state)
            - is_valid: True if signature is valid and not expired
            - original_state: The original state string if valid, None otherwise
        """
        signer = TimestampSigner()
        try:
            # Verify signature and check age
            original_state = signer.unsign(
                signed_state, max_age=SignedStateOAuthMixin.STATE_MAX_AGE
            )
            return True, original_state
        except SignatureExpired:
            logger.warning("OAuth state signature expired")
            return False, None
        except BadSignature:
            logger.warning("OAuth state signature invalid")
            return False, None
