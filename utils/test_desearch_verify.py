#!/usr/bin/env python3
"""
Test flow: call Desearch API (like the miner), get response + proof headers,
then run verify_proof (like the validator). Use this to confirm the proof
verification path end-to-end.

Usage:
  Set DESEARCH_API_KEY in env (and ensure this coldkey is linked to your Desearch account).
  Then run:

    python -m utils.test_desearch_verify
    python -m utils.test_desearch_verify --coldkey 5CdQ3YfmGPJojVahShC2EyT9rUmThecZQiiLquDKVNYCGhbX --statement "test query"

  Default coldkey for verification: 5CdQ3YfmGPJojVahShC2EyT9rUmThecZQiiLquDKVNYCGhbX
"""
import argparse
import os
import sys
from urllib.parse import urlencode

from dotenv import load_dotenv

load_dotenv()

# Default coldkey (public key) for verification when testing
DEFAULT_TEST_COLDKEY = "5CdQ3YfmGPJojVahShC2EyT9rUmThecZQiiLquDKVNYCGhbX"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Call Desearch API, get proof headers, run verify_proof (test miner → validator flow)."
    )
    parser.add_argument(
        "--coldkey",
        default=os.environ.get("DESEARCH_COLDKEY_SS58", DEFAULT_TEST_COLDKEY),
        help=f"Coldkey SS58 for X-Coldkey and for verify_proof (default: {DEFAULT_TEST_COLDKEY[:20]}...).",
    )
    parser.add_argument(
        "--statement",
        default="test query for proof verification",
        help="Search query sent to Desearch /web.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DESEARCH_BASE_URL", "https://api.desearch.ai"),
        help="Desearch API base URL.",
    )
    args = parser.parse_args()

    api_key = (os.environ.get("DESEARCH_API_KEY") or "").strip()
    if not api_key:
        print("ERROR: DESEARCH_API_KEY not set. Set it in env or .env.", file=sys.stderr)
        return 1

    coldkey = args.coldkey.strip()
    base_url = args.base_url.rstrip("/")
    path = "/web"
    params = {"num": 10, "start": 0, "query": args.statement}
    url = f"{base_url}{path}?{urlencode(params)}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": api_key,
        "X-Coldkey": coldkey,
    }

    try:
        import requests
    except ImportError:
        print("ERROR: requests not found. pip install requests", file=sys.stderr)
        return 1

    print(f"Calling Desearch: GET {url}")
    print(f"X-Coldkey: {coldkey[:20]}...")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except Exception as e:
        print(f"ERROR: Desearch request failed: {e}", file=sys.stderr)
        return 1

    body_bytes = resp.content
    sig = resp.headers.get("X-Proof-Signature", "")
    ts = resp.headers.get("X-Proof-Timestamp", "")
    exp = resp.headers.get("X-Proof-Expiry", "")

    print(f"Response: status={resp.status_code} body_len={len(body_bytes)}")
    print(f"X-Proof-Signature: len={len(sig)}")
    print(f"X-Proof-Timestamp: {ts!r}")
    print(f"X-Proof-Expiry: {exp!r}")

    if resp.status_code != 200:
        print(f"ERROR: Desearch returned {resp.status_code}. Body preview: {body_bytes[:200]!r}", file=sys.stderr)
        return 1
    if not (sig and ts and exp):
        print("ERROR: Missing proof headers (401 or Desearch not returning proof).", file=sys.stderr)
        return 1

    from shared.desearch_proof import verify_proof

    print("\nRunning verify_proof(coldkey=..., response_body=..., signature_hex, timestamp, expiry)...")
    valid = verify_proof(
        coldkey=coldkey,
        response_body=body_bytes,
        signature_hex=sig,
        timestamp=ts,
        expiry=exp,
    )
    if valid:
        print("Result: Signature valid YES (validator would accept this proof).")
        return 0
    else:
        print("Result: Signature valid NO (validator would reject this proof).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
