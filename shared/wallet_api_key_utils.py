"""
Utilities to link a wallet address (Bittensor SS58) to an API key (JWT).

Linking is done by including a wallet claim in the JWT. Issuers create tokens with
that claim; the validator reads it after verifying the token and can use it for
authorization or attribution.

Usage:
- Issuer: build payload with build_wallet_link_payload(), sign with your private key,
  and give the JWT to the client as the API key.
- Validator: after decoding the JWT, call get_linked_wallet_from_payload(payload)
  to get the wallet address, if present.
"""

from __future__ import annotations

import re
from typing import Any

# JWT claim name for the linked wallet (SS58 address).
WALLET_CLAIM = "wallet"

# Optional: SS58 format is base58 with 48-49 chars typically; we only do a loose check.
_SS58_PATTERN = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{47,49}$")


def get_linked_wallet_from_payload(payload: dict[str, Any]) -> str | None:
    """
    Return the wallet address linked to this API key (JWT payload), if present.

    Args:
        payload: Decoded JWT payload (e.g. from jwt.decode).

    Returns:
        The SS58 wallet address string, or None if no wallet claim or invalid value.
    """
    if not payload or not isinstance(payload, dict):
        return None
    raw = payload.get(WALLET_CLAIM)
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    addr = raw.strip()
    return addr if addr else None


def build_wallet_link_payload(
    sub: str,
    wallet_address: str,
    *,
    exp_seconds: int | None = None,
    **extra_claims: Any,
) -> dict[str, Any]:
    """
    Build a JWT payload that links the given wallet to the token (for use as API key).

    Caller should then sign this payload with the validator's JWT private key
    (e.g. jwt.encode(payload, private_key, algorithm="RS512")).

    Args:
        sub: JWT subject (e.g. "validator_proxy").
        wallet_address: SS58 wallet address to link. Will be normalized (stripped).
        exp_seconds: Optional seconds from now for exp claim; omit for no exp.
        **extra_claims: Additional claims to include (e.g. iat, jti).

    Returns:
        Payload dict suitable for jwt.encode.
    """
    import time

    payload: dict[str, Any] = {
        "sub": sub,
        WALLET_CLAIM: normalize_wallet_address(wallet_address),
        **extra_claims,
    }
    if exp_seconds is not None:
        payload["exp"] = int(time.time()) + exp_seconds
    return payload


def normalize_wallet_address(addr: str) -> str:
    """
    Normalize a wallet address for storage in JWT: strip whitespace and remove
    any non-breaking space (\\xa0) that can slip in from config/env.
    """
    if not addr or not isinstance(addr, str):
        return ""
    return addr.replace("\xa0", "").strip()


def is_valid_ss58_format(addr: str) -> bool:
    """
    Return True if the string looks like an SS58 address (length and charset).
    Does not verify checksum.
    """
    if not addr or not isinstance(addr, str):
        return False
    return bool(_SS58_PATTERN.match(addr.strip()))
