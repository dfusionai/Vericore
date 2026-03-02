#!/usr/bin/env python3
"""
Debug why a JWT isn't authenticating against the validator.

Usage:
  python -m validator.jwt_auth_debug "eyJhbGciOiJSUz..."
  python -m validator.jwt_auth_debug   # reads token from stdin

Uses the same key/algorithm as the API server (VALIDATOR_JWT_PUBLIC_KEY or
VALIDATOR_JWT_PUBLIC_KEY_FILE / VALIDATOR_JWT_ALGORITHM). Run from repo root.
"""
import json
import sys
from base64 import urlsafe_b64decode

import jwt

# Load validator config (same as api_server)
from shared.environment_variables import (
    VALIDATOR_JWT_PUBLIC_KEY,
    VALIDATOR_JWT_ALGORITHM,
)

VALIDATOR_PROXY_SUB = "validator_proxy"


def decode_unverified(token: str):
    """Decode header and payload without verifying signature."""
    parts = token.split(".")
    if len(parts) != 3:
        return None, None, "JWT must have 3 segments (header.payload.signature)"
    try:
        # add padding if needed
        def pad(s):
            return s + "=" * (4 - len(s) % 4) if len(s) % 4 else s

        raw_header = urlsafe_b64decode(pad(parts[0]))
        raw_payload = urlsafe_b64decode(pad(parts[1]))
        header = json.loads(raw_header)
        payload = json.loads(raw_payload)
        return header, payload, None
    except Exception as e:
        return None, None, str(e)


def main():
    if len(sys.argv) > 1:
        token = sys.argv[1].strip()
    else:
        token = sys.stdin.read().strip()
    if not token:
        print("Usage: python -m validator.jwt_auth_debug <token>")
        sys.exit(1)

    print("=== JWT (unverified decode) ===\n")
    header, payload, err = decode_unverified(token)
    if err:
        print(f"Decode error: {err}")
        sys.exit(1)

    print("Header:", json.dumps(header, indent=2))
    print("\nPayload:", json.dumps(payload, indent=2))
    token_alg = header.get("alg", "")
    sub = payload.get("sub")
    exp = payload.get("exp")
    if exp is not None:
        import time
        now = int(time.time())
        if exp < now:
            print(f"\nExpiry: EXPIRED (exp={exp} was {now - exp}s ago)")
        else:
            print(f"\nExpiry: valid (exp={exp}, in {exp - now}s)")

    print("\n=== Validator config ===")
    print(f"VALIDATOR_JWT_ALGORITHM (expected): {VALIDATOR_JWT_ALGORITHM}")
    print(f"Token alg (actual):                {token_alg}")
    if token_alg != VALIDATOR_JWT_ALGORITHM:
        print(f"\n>>> ALGORITHM MISMATCH: token is signed with '{token_alg}' but validator expects '{VALIDATOR_JWT_ALGORITHM}'.")
        print("    Fix: set VALIDATOR_JWT_ALGORITHM=" + token_alg + " (or re-issue token with " + VALIDATOR_JWT_ALGORITHM + ").")

    if not VALIDATOR_JWT_PUBLIC_KEY:
        print("\n>>> No public key loaded (VALIDATOR_JWT_PUBLIC_KEY or VALIDATOR_JWT_PUBLIC_KEY_FILE).")
        sys.exit(1)
    print(f"Public key: loaded ({len(VALIDATOR_JWT_PUBLIC_KEY)} chars)")

    print("\n=== Verification attempt ===")
    try:
        decoded = jwt.decode(
            token,
            VALIDATOR_JWT_PUBLIC_KEY,
            algorithms=[VALIDATOR_JWT_ALGORITHM],
        )
        if decoded.get("sub") != VALIDATOR_PROXY_SUB:
            print(f">>> SUB mismatch: got '{decoded.get('sub')}', expected '{VALIDATOR_PROXY_SUB}'")
        else:
            print("OK: Token is valid and sub=validator_proxy.")
    except jwt.ExpiredSignatureError as e:
        print(f">>> Expired: {e}")
    except jwt.InvalidSignatureError as e:
        print(f">>> Invalid signature: {e}")
        print("   (Wrong public key or token was signed with a different key.)")
    except jwt.InvalidAlgorithmError as e:
        print(f">>> Algorithm not allowed: {e}")
        print(f"   Set VALIDATOR_JWT_ALGORITHM={token_alg} to accept this token.")
    except jwt.InvalidTokenError as e:
        print(f">>> Invalid token: {e}")


if __name__ == "__main__":
    main()
