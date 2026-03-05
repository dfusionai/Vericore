"""
Example miner that uses Desearch API and attaches proof to the synapse.

Requires:
- DESEARCH_API_KEY: your Desearch API key (set in env).
- Miner coldkey must be linked to your Desearch account (one-time: POST to /bt/miner/link).
See https://desearch.ai/docs/api-reference and miner README for linking and usage.
"""
import argparse
import base64
import json
import os
import time
import traceback
from typing import Tuple, List

import bittensor as bt
import requests

from dotenv import load_dotenv

from shared.log_data import LoggerType
from shared.proxy_log_handler import register_proxy_log_handler
from shared.veridex_protocol import (
    VericoreSynapse,
    SourceEvidence,
    Desearch,
    DesearchProof,
)
from shared.environment_variables import DESEARCH_API_KEY, DESEARCH_BASE_URL

# When set (e.g. by utils.validate_desearch_signature), use this coldkey and skip wallet/subtensor/registration.
DESEARCH_COLDKEY_SS58_ENV = os.environ.get("DESEARCH_COLDKEY_SS58", "").strip()

bt.logging.set_trace()
load_dotenv()

# Desearch search endpoint (adjust if API differs)
DESEARCH_SEARCH_PATH = "/search"


class Miner:
    def __init__(self):
        self.config = self.get_config()
        self.setup_bittensor_objects()
        self.setup_logging()

        if not DESEARCH_API_KEY:
            bt.logging.warning(
                "DESEARCH_API_KEY not set. Set it in env to use the Desearch miner."
            )

    def get_config(self):
        if DESEARCH_COLDKEY_SS58_ENV:
            parser = argparse.ArgumentParser()
            parser.add_argument("--netuid", type=int, default=1, help="Subnet UID.")
            bt.logging.add_args(parser)
            config = parser.parse_args()
            log_dir = getattr(config, "logging_dir", os.path.expanduser("~/.bittensor/miner"))
            config.full_path = os.path.join(os.path.abspath(log_dir), "desearch_validate")
            os.makedirs(config.full_path, exist_ok=True)
            return config
        parser = argparse.ArgumentParser()
        parser.add_argument("--netuid", type=int, default=1, help="Subnet UID.")
        bt.subtensor.add_args(parser)
        bt.logging.add_args(parser)
        bt.wallet.add_args(parser)
        bt.axon.add_args(parser)
        config = bt.config(parser)
        config.full_path = os.path.expanduser(
            "{}/{}/{}/netuid{}/{}".format(
                config.logging.logging_dir,
                config.wallet.name,
                config.wallet.hotkey_str,
                config.netuid,
                "miner",
            )
        )
        os.makedirs(config.full_path, exist_ok=True)
        return config

    def setup_logging(self):
        bt.logging(config=self.config, logging_dir=self.config.full_path)

    def setup_proxy_logger(self):
        bt_logger = __import__("logging").getLogger("bittensor")
        register_proxy_log_handler(bt_logger, LoggerType.Miner, self.wallet)

    def setup_bittensor_objects(self):
        if DESEARCH_COLDKEY_SS58_ENV:
            self.wallet = None
            self.subtensor = None
            self.metagraph = None
            self.my_subnet_uid = -1
            self.coldkey_ss58 = DESEARCH_COLDKEY_SS58_ENV
            return
        self.wallet = bt.wallet(config=self.config)
        self.subtensor = bt.subtensor(config=self.config)
        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error("Miner not registered. Run btcli register.")
            exit()
        self.my_subnet_uid = self.metagraph.hotkeys.index(
            self.wallet.hotkey.ss58_address
        )
        # Coldkey SS58 for Desearch requests (validator uses same from metagraph to verify)
        self.coldkey_ss58 = ""
        if hasattr(self.wallet, "coldkeypub") and self.wallet.coldkeypub is not None:
            self.coldkey_ss58 = getattr(self.wallet.coldkeypub, "ss58_address", "") or ""

    def blacklist_fn(self, synapse: VericoreSynapse) -> Tuple[bool, str]:
        if self.metagraph is None:
            return True, None
        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            return True, None
        try:
            neuron_uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
            neuron = self.metagraph.neurons[neuron_uid]
            if not neuron.validator_permit:
                return True, None
            if neuron.axon_info is None or not neuron.axon_info.is_serving:
                return True, None
            return False, None
        except (ValueError, IndexError):
            return True, None

    def call_desearch(self, statement: str) -> tuple[bytes, str, str, str] | None:
        """
        Call Desearch API once. Returns (response_body_bytes, signature_hex, timestamp, expiry) or None.
        """
        if not DESEARCH_API_KEY or not self.coldkey_ss58:
            return None
        url = f"{DESEARCH_BASE_URL.rstrip('/')}{DESEARCH_SEARCH_PATH}"
        headers = {
            "Authorization": f"Bearer {DESEARCH_API_KEY}",
            "X-Coldkey": self.coldkey_ss58,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                url,
                json={"query": statement},
                headers=headers,
                timeout=60,
            )
            body_bytes = resp.content
            sig = resp.headers.get("X-Proof-Signature", "")
            ts = resp.headers.get("X-Proof-Timestamp", "")
            exp = resp.headers.get("X-Proof-Expiry", "")
            return (body_bytes, sig, ts, exp)
        except Exception as e:
            bt.logging.warning(f"Desearch API call failed: {e}")
            return None

    def veridex_forward(self, synapse: VericoreSynapse) -> VericoreSynapse:
        bt.logging.info(f"{synapse.request_id} | Received Vericore request")
        statement = synapse.statement
        synapse.veridex_response = []

        result = self.call_desearch(statement)
        if not result:
            bt.logging.info(f"{synapse.request_id} | No Desearch response, returning empty")
            return synapse

        body_bytes, signature_hex, timestamp, expiry = result
        if not (signature_hex and timestamp and expiry):
            bt.logging.warning(f"{synapse.request_id} | Desearch response missing proof headers")
            return synapse

        # Set proof on root (body base64 + proof from headers)
        synapse.desearch = Desearch(
            response_body=base64.b64encode(body_bytes).decode("ascii"),
            proof=DesearchProof(
                signature=signature_hex,
                timestamp=timestamp,
                expiry=expiry,
            ),
        )

        # Parse response and build evidence (assume JSON list of {url, snippet})
        try:
            data = json.loads(body_bytes.decode("utf-8"))
            items = data if isinstance(data, list) else data.get("results", data.get("data", []))
        except Exception:
            items = []

        evidence_list: List[SourceEvidence] = []
        for item in items:
            if isinstance(item, dict):
                url = item.get("url", "").strip()
                excerpt = item.get("snippet", item.get("excerpt", "")).strip()
            else:
                continue
            if url or excerpt:
                evidence_list.append(
                    SourceEvidence(url=url, excerpt=excerpt, source_type="desearch")
                )

        synapse.veridex_response = evidence_list
        bt.logging.info(
            f"{synapse.request_id} | Miner returns {len(evidence_list)} Desearch evidence items"
        )
        return synapse

    def setup_axon(self):
        self.axon = bt.axon(wallet=self.wallet, config=self.config)
        self.axon.attach(forward_fn=self.veridex_forward, blacklist_fn=self.blacklist_fn)
        self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
        self.axon.start()

    def run(self):
        self.setup_axon()
        self.setup_proxy_logger()
        step = 0
        while True:
            try:
                if step % 60 == 0:
                    self.metagraph.sync()
                step += 1
                time.sleep(1)
            except KeyboardInterrupt:
                self.axon.stop()
                break
            except Exception as e:
                bt.logging.error(traceback.format_exc())
                continue


if __name__ == "__main__":
    Miner().run()
