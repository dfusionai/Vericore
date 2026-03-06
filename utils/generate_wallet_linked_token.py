#!/usr/bin/env python3
"""
Generate a JWT that links a wallet address to an API key for the validator.

The token can be used as the Bearer API key; the validator will accept it
(if signed with the matching public key) and can read the linked wallet
from the payload.

Usage:
  python -m utils.generate_wallet_linked_token --wallet 5F3sa2TJAWMqDhXG6jhV4N8ko9SxwGy8TpaNS1repo5EYjLQ
  python -m utils.generate_wallet_linked_token --wallet 5F3sa... --exp-days 30

Requires the validator JWT *private* key. Set one of:
  VALIDATOR_JWT_PRIVATE_KEY       - PEM string (inline)
  VALIDATOR_JWT_PRIVATE_KEY_FILE  - Path to PEM file (e.g. keys/validator_jwt_private.pem)

Uses VALIDATOR_JWT_ALGORITHM (default RS512). Run from repo root.
"""
import argparse
import os
import sys

import jwt

from shared.wallet_api_key_utils import (
    WALLET_CLAIM,
    build_wallet_link_payload,
    is_valid_ss58_format,
    normalize_wallet_address,
)

VALIDATOR_PROXY_SUB = "validator_proxy"
_DEFAULT_ALGORITHM = "RS512"


def _load_private_key() -> str | None:
    inline = os.environ.get("VALIDATOR_JWT_PRIVATE_KEY")
    if inline:
        return inline.strip()
    path = os.environ.get("VALIDATOR_JWT_PRIVATE_KEY_FILE")
    if path:
        path = os.path.abspath(os.path.expanduser(path))
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a wallet-linked JWT for validator API auth."
    )
    parser.add_argument(
        "--wallet",
        required=True,
        help="SS58 wallet address to link to this API key.",
    )
    parser.add_argument(
        "--exp-days",
        type=float,
        default=30,
        help="Token expiry in days (default: 30). Use 0 for no expiry.",
    )
    parser.add_argument(
        "--sub",
        default=VALIDATOR_PROXY_SUB,
        help=f"JWT subject (default: {VALIDATOR_PROXY_SUB}).",
    )
    args = parser.parse_args()

    wallet = normalize_wallet_address(args.wallet)
    if not wallet:
        print("Error: --wallet is required and must be non-empty.", file=sys.stderr)
        return 1
    if not is_valid_ss58_format(wallet):
        print(
            "Warning: wallet does not look like a standard SS58 address (47–49 base58 chars).",
            file=sys.stderr,
        )

    private_key = _load_private_key()
    if not private_key:
        print(
            "Error: Set VALIDATOR_JWT_PRIVATE_KEY or VALIDATOR_JWT_PRIVATE_KEY_FILE.",
            file=sys.stderr,
        )
        return 1

    algorithm = os.environ.get("VALIDATOR_JWT_ALGORITHM", _DEFAULT_ALGORITHM)
    exp_seconds = int(args.exp_days * 86400) if args.exp_days else None

    payload = build_wallet_link_payload(
        sub=args.sub,
        wallet_address=wallet,
        exp_seconds=exp_seconds,
    )
    token = jwt.encode(payload, private_key, algorithm=algorithm)
    if hasattr(token, "decode"):
        token = token.decode("utf-8")

    print("Wallet-linked JWT (use as Bearer token):")
    print(token)
    print(f"\nDecoded claim: {WALLET_CLAIM}={payload.get(WALLET_CLAIM)!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
