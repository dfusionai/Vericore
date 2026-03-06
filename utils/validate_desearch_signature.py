"""
Utility to run the Desearch miner's veridex_forward and simulate validator-side
signature verification. Confirms that the proof returned by the miner verifies
with the miner's coldkey (same logic as validator/api_server.py).

Usage:
  Pass the miner coldkey (wallet address) via --coldkey or DESEARCH_COLDKEY_SS58.
  With coldkey set, wallet/subtensor are not loaded (no btcli wallet needed).

  python -m utils.validate_desearch_signature --coldkey <SS58> [--statement "your query"] [--request-id id]

  Or use wallet: omit --coldkey and pass wallet args so the miner loads coldkey from wallet.

Requires:
  - DESEARCH_API_KEY in env (or .env)
  - Miner coldkey: either --coldkey / DESEARCH_COLDKEY_SS58 or wallet (same as miner).
"""
import argparse
import base64
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from shared.desearch_proof import verify_proof
from shared.veridex_protocol import VericoreSynapse


def main() -> int:
    # Parse our args first; set coldkey in env so miner can use it without wallet
    our_parser = argparse.ArgumentParser(
        description="Run miner veridex_forward and validate Desearch proof as validator would."
    )
    our_parser.add_argument(
        "--coldkey",
        type=str,
        default=os.environ.get("DESEARCH_COLDKEY_SS58", ""),
        help="Miner coldkey SS58 (wallet address). Uses DESEARCH_COLDKEY_SS58 env if not set.",
    )
    our_parser.add_argument(
        "--statement",
        type=str,
        default="test statement for signature validation",
        help="Statement to send to Desearch (miner forwards this).",
    )
    our_parser.add_argument(
        "--request-id",
        type=str,
        default="validate-desearch-signature",
        help="Request ID for the synthetic synapse.",
    )
    args, remaining_argv = our_parser.parse_known_args()
    if args.coldkey:
        os.environ["DESEARCH_COLDKEY_SS58"] = args.coldkey.strip()
    sys.argv = [sys.argv[0]] + remaining_argv

    from miner.desearch.miner import Miner

    miner = Miner()
    if not miner.coldkey_ss58:
        print(
            "ERROR: No coldkey. Pass --coldkey <SS58> or set DESEARCH_COLDKEY_SS58, or use wallet args.",
            file=sys.stderr,
        )
        return 1
    if not os.environ.get("DESEARCH_API_KEY"):
        print("ERROR: DESEARCH_API_KEY not set. Set it in env or .env.", file=sys.stderr)
        return 1

    synapse = VericoreSynapse(statement=args.statement, request_id=args.request_id)
    miner.veridex_forward(synapse)

    raw_desearch = getattr(synapse, "desearch", [])
    desearch_list = raw_desearch if isinstance(raw_desearch, list) else []
    if not desearch_list:
        print("No Desearch proof on synapse (empty response or missing proof headers).")
        return 0

    desearch = desearch_list[0]
    if not desearch.response_body or not desearch.proof:
        print("No Desearch proof on synapse (empty response or missing proof headers).")
        return 0

    proof = desearch.proof
    if not (proof.signature and proof.timestamp and proof.expiry):
        print("Desearch proof incomplete (missing signature, timestamp, or expiry).")
        return 1

    try:
        response_body_bytes = base64.b64decode(desearch.response_body)
    except Exception as e:
        print(f"Failed to decode response_body: {e}")
        return 1

    valid = verify_proof(
        coldkey=miner.coldkey_ss58,
        response_body=response_body_bytes,
        signature_hex=proof.signature,
        timestamp=proof.timestamp,
        expiry=proof.expiry,
    )
    if valid:
        print("Signature valid: YES (validator would accept this proof).")
        return 0
    else:
        print("Signature valid: NO (validator would reject this proof).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
