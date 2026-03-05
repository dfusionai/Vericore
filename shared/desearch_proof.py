"""
Verify Desearch proof: signature over (coldkey|data_hash|timestamp|expiry) using miner's coldkey.
"""
import hashlib
from datetime import datetime, timezone


def verify_proof(
    coldkey: str,
    response_body: bytes,
    signature_hex: str,
    timestamp: str,
    expiry: str,
) -> bool:
    """
    Verify Desearch proof: check expiry, reconstruct message, verify signature with miner's coldkey.

    Args:
        coldkey: Miner's coldkey SS58 (from metagraph).
        response_body: Raw Desearch response body bytes.
        signature_hex: X-Proof-Signature (hex).
        timestamp: X-Proof-Timestamp.
        expiry: X-Proof-Expiry.

    Returns:
        True if proof is valid and not expired, False otherwise.
    """
    # 1. Check expiry
    try:
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expiry_dt:
            return False
    except (ValueError, TypeError):
        return False

    # 2. Hash the response body
    data_hash = hashlib.sha256(response_body).hexdigest()

    # 3. Reconstruct the signed message
    message = f"{coldkey}|{data_hash}|{timestamp}|{expiry}"
    message_bytes = message.encode("utf-8")

    # 4. Verify signature with miner's coldkey (public key)
    try:
        sig_bytes = bytes.fromhex(signature_hex)
    except (ValueError, TypeError):
        return False

    try:
        from bittensor import Keypair
    except ImportError:
        try:
            from bittensor_wallet import Keypair  # type: ignore
        except ImportError:
            raise ImportError(
                "Desearch proof verification requires bittensor or bittensor_wallet (Keypair.verify)"
            ) from None

    keypair = Keypair(ss58_address=coldkey)
    return keypair.verify(message_bytes, sig_bytes)
