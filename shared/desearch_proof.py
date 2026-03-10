"""
Verify Desearch proof: signature over (coldkey|data_hash|timestamp|expiry).

  - data_hash = SHA256(response_body).hexdigest()
  - message = f"{coldkey}|{data_hash}|{timestamp}|{expiry}"  (coldkey = miner's SS58, for binding)
  - Signature is verified with Desearch's public key (DESEARCH_PUBLIC_KEY).
"""
import hashlib
import logging
from datetime import datetime, timezone

# Desearch's SS58 public key; used to verify X-Proof-Signature.
DESEARCH_PUBLIC_KEY = "5CdQ3YfmGPJojVahShC2EyT9rUmThecZQiiLquDKVNYCGhbX"

logger = logging.getLogger(__name__)


def _log(level: str, msg: str, *args) -> None:
    """Log to standard logger and bt.logging when available (e.g. validator)."""
    formatted = msg % args if args else msg
    getattr(logger, level)(msg, *args)
    try:
        import bittensor as bt
        getattr(bt.logging, level)(formatted)
    except (ImportError, AttributeError):
        pass


def verify_proof(
    coldkey: str,
    response_body: bytes,
    signature_hex: str,
    timestamp: str,
    expiry: str,
) -> bool:
    """
    Verify Desearch proof: check expiry, reconstruct message, verify signature with Desearch's public key.

    Args:
        coldkey: Miner's coldkey SS58 (included in the signed message for binding; from metagraph).
        response_body: Raw Desearch response body bytes.
        signature_hex: X-Proof-Signature (hex).
        timestamp: X-Proof-Timestamp.
        expiry: X-Proof-Expiry.

    Returns:
        True if proof is valid and not expired, False otherwise.
    """
    coldkey_preview = coldkey[:16] + "..." if len(coldkey) > 16 else coldkey
    _log(
        "info",
        "desearch_proof verify_proof received: coldkey=%s response_body_len=%s signature_hex_len=%s timestamp=%s expiry=%s",
        coldkey_preview,
        len(response_body),
        len(signature_hex),
        timestamp,
        expiry,
    )

    # 1. Check expiry
    try:
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expiry_dt:
            _log("warning", "desearch_proof: expired (expiry=%s)", expiry)
            return False
    except (ValueError, TypeError) as e:
        _log("warning", "desearch_proof: malformed expiry=%s error=%s", expiry, e)
        return False

    # 2. Hash the response body
    data_hash = hashlib.sha256(response_body).hexdigest()

    # 3. Reconstruct the signed message
    message = f"{coldkey}|{data_hash}|{timestamp}|{expiry}"
    message_bytes = message.encode("utf-8")
    _log("info", "desearch_proof: data_hash=%s message=%s", data_hash, message)

    # 4. Verify signature against Desearch's public key
    try:
        sig_bytes = bytes.fromhex(signature_hex)
    except (ValueError, TypeError) as e:
        _log("warning", "desearch_proof: invalid signature_hex (len=%s) error=%s", len(signature_hex), e)
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

    keypair = Keypair(ss58_address=DESEARCH_PUBLIC_KEY)
    ok = keypair.verify(message_bytes, sig_bytes)
    _log("info", "desearch_proof: keypair.verify result=%s", ok)
    return ok
