#!/usr/bin/env python3
"""
One-time link: bind your Bittensor coldkey to your Desearch account.

Signs your Desearch API key with your coldkey and POSTs to Desearch's
/bt/miner/link so the miner can use the API with proof.

Usage:
  python -m utils.link_desearch_miner --wallet.name my_wallet --wallet.hotkey miner_desearch_hotkey

  Password: prompted interactively if not in WALLET_PASSWORD/DESEARCH_WALLET_PASSWORD or --wallet.password.

Requires:
  - DESEARCH_API_KEY in env (or .env)
  - Coldkey password (env, --wallet.password, or interactive prompt)
  - bittensor_wallet: pip install bittensor-wallet
  - Wallet with a coldkey (same wallet/hotkey as miner; only coldkey is used for the link)
"""
import argparse
import getpass
import os
import sys

from dotenv import load_dotenv

load_dotenv()

DESEARCH_LINK_PATH = "/bt/miner/link"


def main() -> int:
    api_key = os.environ.get("DESEARCH_API_KEY", "").strip()
    if not api_key:
        print(
            "Error: DESEARCH_API_KEY not set. Set it in env or .env.",
            file=sys.stderr,
        )
        return 1

    try:
        from bittensor_wallet import Wallet
    except ImportError:
        print(
            "Error: bittensor_wallet not found. Install with: pip install bittensor-wallet",
            file=sys.stderr,
        )
        return 1

    try:
        import requests
    except ImportError:
        print("Error: requests not found. Install with: pip install requests", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description="Link your Bittensor coldkey to your Desearch account (one-time)."
    )
    parser.add_argument(
        "--wallet.name",
        dest="wallet_name",
        required=True,
        help="Wallet name (must match the miner; coldkey lives under this name).",
    )
    parser.add_argument(
        "--wallet.path",
        dest="wallet_path",
        default=os.environ.get("WALLET_PATH", ""),
        help="Wallet root directory (default: ~/.bittensor/wallets). Set if miner uses a custom path.",
    )
    parser.add_argument(
        "--wallet.hotkey",
        dest="wallet_hotkey",
        default="default",
        help="Hotkey name (default: default). Same wallet as miner; only coldkey is used for link.",
    )
    parser.add_argument(
        "--wallet.password",
        dest="wallet_password",
        default=os.environ.get("DESEARCH_WALLET_PASSWORD", os.environ.get("WALLET_PASSWORD", "")),
        help="Coldkey password. Default: DESEARCH_WALLET_PASSWORD or WALLET_PASSWORD env.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DESEARCH_BASE_URL", "https://api.desearch.ai"),
        help="Desearch API base URL (default: DESEARCH_BASE_URL or https://api.desearch.ai)",
    )
    args = parser.parse_args()

    password = (args.wallet_password or "").strip()
    if not password:
        try:
            password = getpass.getpass("Coldkey password: ")
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            return 1
        if not password.strip():
            print("Error: Coldkey password required.", file=sys.stderr)
            return 1
        password = password.strip()

    wallet_kwargs = {"name": args.wallet_name}
    if (args.wallet_path or "").strip():
        wallet_kwargs["path"] = os.path.abspath(os.path.expanduser(args.wallet_path.strip()))
    wallet = Wallet(**wallet_kwargs)
    try:
        keypair = wallet.get_coldkey(password)
    except Exception as e:
        print(f"Error loading coldkey: {e}", file=sys.stderr)
        print(
            "Tip: Use the same --wallet.name as your miner (the wallet that has the coldkey). "
            "If the miner uses a custom wallet directory, set --wallet.path or WALLET_PATH.",
            file=sys.stderr,
        )
        return 1

    coldkey_ss58 = keypair.ss58_address
    print(f"Using coldkey: {coldkey_ss58}")

    signature_bytes = keypair.sign(api_key.encode("utf-8"))
    signature_hex = signature_bytes.hex()

    url = args.base_url.rstrip("/") + DESEARCH_LINK_PATH
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "coldkey_ss58": coldkey_ss58,
        "signature_hex": signature_hex,
    }

    print("Linking miner to Desearch account...")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        print(f"Error calling Desearch: {e}", file=sys.stderr)
        return 1

    print(f"\nResponse from {DESEARCH_LINK_PATH} [{response.status_code}]:")
    print(response.text)
    if response.status_code >= 400:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
