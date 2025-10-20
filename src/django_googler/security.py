import logging

from django.core import signing

logger = logging.getLogger(__name__)


class SignedStateOAuthMixin:
    """
    Mixin for handling OAuth state with cryptographic signing instead of sessions.

    This allows state verification to work across different domains without
    relying on session cookies.

    The state data is serialized, compressed, and base64-encoded, making it
    completely opaque while maintaining security and tamper-resistance.
    """

    # State tokens expire after 10 minutes (600 seconds)
    STATE_MAX_AGE = 600

    @staticmethod
    def sign_state(state: str, scopes: list[str] | None = None) -> str:
        """
        Sign and encode the OAuth state using Django's signing framework.

        The resulting signed state is opaque (base64-encoded and compressed)
        so the contents are not visible in the URL.

        Args:
            state: The state string to sign
            scopes: Optional list of OAuth scopes to encode in the state

        Returns:
            Opaque signed state string containing state and optional metadata
        """
        # Build state data dictionary
        state_data = {
            "state": state,
        }
        if scopes is not None:
            state_data["scopes"] = scopes

        # Use dumps() which serializes, compresses, and base64-encodes the data
        # making it completely opaque
        return signing.dumps(
            state_data,
            compress=True,  # Compress to reduce URL length
        )

    @staticmethod
    def verify_signed_state(signed_state: str) -> tuple[bool, str | None, dict | None]:
        """
        Verify and extract the original state and metadata from a signed state.

        Args:
            signed_state: The opaque signed state string to verify

        Returns:
            Tuple of (is_valid, original_state, metadata)
            - is_valid: True if signature is valid and not expired
            - original_state: The original state string if valid, None otherwise
            - metadata: Dict containing additional data (e.g., scopes) if valid, None otherwise
        """
        try:
            # Verify signature, check age, and deserialize
            state_data = signing.loads(
                signed_state,
                max_age=SignedStateOAuthMixin.STATE_MAX_AGE,
            )

            # Handle new format (dict with state and metadata)
            if isinstance(state_data, dict) and "state" in state_data:
                original_state = state_data["state"]
                # Extract metadata (scopes, etc.)
                metadata = {k: v for k, v in state_data.items() if k != "state"}
                return True, original_state, metadata

            # Handle old format (plain string) for backwards compatibility
            if isinstance(state_data, str):
                return True, state_data, {}

            # Unexpected format
            logger.warning("OAuth state has unexpected format")
            return False, None, None

        except signing.SignatureExpired:
            logger.warning("OAuth state signature expired")
            return False, None, None
        except signing.BadSignature:
            logger.warning("OAuth state signature invalid")
            return False, None, None
        except Exception as e:
            logger.error(f"Error verifying OAuth state: {str(e)}")
            return False, None, None
