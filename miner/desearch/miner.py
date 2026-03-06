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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Tuple, List, Optional
from urllib.parse import urlencode

import bittensor as bt
import requests

from dotenv import load_dotenv

from shared.log_data import LoggerType
from shared.proxy_log_handler import register_proxy_log_handler
from shared.veridex_protocol import (
    VericoreSynapse,
    SourceEvidence,
    SourceType,
    Desearch,
    DesearchProof,
)
from shared.environment_variables import DESEARCH_API_KEY, DESEARCH_BASE_URL

# When set (e.g. by utils.validate_desearch_signature), use this coldkey and skip wallet/subtensor/registration.
DESEARCH_COLDKEY_SS58_ENV = os.environ.get("DESEARCH_COLDKEY_SS58", "").strip()

bt.logging.set_trace()
load_dotenv()

# Desearch SERP (legacy): GET /web?num=5&start=0&query=...
DESEARCH_SERP_SEARCH_PATH = "/web"
DESEARCH_SERP_NUM_RESULTS = 5
DESEARCH_SERP_START = 0

# Max evidence items taken per Desearch source (SERP, web, twitter). Each source contributes at most this many.
DESEARCH_MAX_EVIDENCE_PER_SOURCE = 5

# Desearch new endpoints (POST, JSON body)
DESEARCH_WEB_SEARCH_PATH = "/desearch/ai/search/links/web"
DESEARCH_TWITTER_SEARCH_PATH = "/desearch/ai/search/links/twitter"
DESEARCH_WEB_TOOLS = ["web", "reddit", "wikipedia"]

# Feature flags (env-configurable)
DESEARCH_ENABLE_SERP = os.environ.get("DESEARCH_ENABLE_SERP", "false").lower() == "true"
DESEARCH_ENABLE_WEB = os.environ.get("DESEARCH_ENABLE_WEB", "false").lower() == "true"
DESEARCH_ENABLE_TWITTER = os.environ.get("DESEARCH_ENABLE_TWITTER", "true").lower() == "true"


@dataclass
class DesearchApiResponse:
    """Raw response from the Desearch API including proof headers."""
    body: bytes
    signature_hex: str
    timestamp: str
    expiry: str


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
        if DESEARCH_COLDKEY_SS58_ENV:
            bt.logging(config=None, logging_dir=self.config.full_path)
        else:
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

            bt.logging.info(f"Blacklisting neuron {synapse.dendrite.hotkey} with uid {neuron_uid}")

            neuron = self.metagraph.neurons[neuron_uid]
            if not neuron.validator_permit:
                return True, None
            if neuron.axon_info is None or not neuron.axon_info.is_serving:
                return True, None

            bt.logging.warning(f"Invalid validator with hotkey {synapse.dendrite.hotkey} with uid {neuron_uid}")                
            return False, None
        except (ValueError, IndexError):
            return True, None

    def call_desearch_serp_web_search(self, statement: str) -> Optional[DesearchApiResponse]:
        """Legacy SERP web search: GET /web. Returns DesearchApiResponse or None."""
        if not DESEARCH_API_KEY:
            bt.logging.debug("call_desearch_serp: skipped — DESEARCH_API_KEY not set")
            return None
        if not self.coldkey_ss58:
            bt.logging.debug("call_desearch_serp: skipped — coldkey_ss58 not set")
            return None
        params = {
            "num": DESEARCH_SERP_NUM_RESULTS,
            "start": DESEARCH_SERP_START,
            "query": statement,
        }
        url = f"{DESEARCH_BASE_URL.rstrip('/')}{DESEARCH_SERP_SEARCH_PATH}?{urlencode(params)}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if DESEARCH_API_KEY:
            headers["Authorization"] = f"{DESEARCH_API_KEY}"
        if self.coldkey_ss58:
            headers["X-Coldkey"] = self.coldkey_ss58
        bt.logging.info(
            f"call_desearch_serp: GET {url[:80]}... X-Coldkey={self.coldkey_ss58[:12]}..."
        )
        try:
            resp = requests.get(url, headers=headers, timeout=60)
            body_bytes = resp.content
            sig = resp.headers.get("X-Proof-Signature", "")
            ts = resp.headers.get("X-Proof-Timestamp", "")
            exp = resp.headers.get("X-Proof-Expiry", "")
            bt.logging.info(
                f"call_desearch_serp: status={resp.status_code} body_len={len(body_bytes)} "
                f"proof={bool(sig)} timestamp={bool(ts)} expiry={bool(exp)}"
            )
            if resp.status_code != 200:
                try:
                    body_preview = body_bytes[:200].decode("utf-8", errors="replace").strip()
                except Exception:
                    body_preview = repr(body_bytes[:100])
                bt.logging.warning(
                    f"call_desearch_serp: non-200 status={resp.status_code} body_preview={body_preview!r}"
                )
            if not (sig and ts and exp):
                bt.logging.warning("call_desearch_serp: missing proof headers")
            return DesearchApiResponse(body=body_bytes, signature_hex=sig, timestamp=ts, expiry=exp)
        except Exception as e:
            bt.logging.warning(f"call_desearch_serp failed: {e}")
            return None

    def _call_desearch_post(self, endpoint: str, payload: dict) -> Optional[DesearchApiResponse]:
        """Shared POST helper for the new Desearch endpoints. Returns DesearchApiResponse or None."""
        if not DESEARCH_API_KEY:
            bt.logging.debug(f"_call_desearch_post({endpoint}): skipped — DESEARCH_API_KEY not set")
            return None
        if not self.coldkey_ss58:
            bt.logging.debug(f"_call_desearch_post({endpoint}): skipped — coldkey_ss58 not set")
            return None
        url = f"{DESEARCH_BASE_URL.rstrip('/')}{endpoint}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": DESEARCH_API_KEY,
            "X-Coldkey": self.coldkey_ss58,
        }
        bt.logging.info(
            f"_call_desearch_post: POST {url[:80]}... X-Coldkey={self.coldkey_ss58[:12]}..."
        )
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            body_bytes = resp.content
            sig = resp.headers.get("X-Proof-Signature", "")
            ts = resp.headers.get("X-Proof-Timestamp", "")
            exp = resp.headers.get("X-Proof-Expiry", "")
            bt.logging.info(
                f"_call_desearch_post({endpoint}): status={resp.status_code} body_len={len(body_bytes)} "
                f"proof={bool(sig)} timestamp={bool(ts)} expiry={bool(exp)}"
            )
            if resp.status_code != 200:
                try:
                    body_preview = body_bytes[:200].decode("utf-8", errors="replace").strip()
                except Exception:
                    body_preview = repr(body_bytes[:100])
                bt.logging.warning(
                    f"_call_desearch_post({endpoint}): non-200 status={resp.status_code} body_preview={body_preview!r}"
                )
            if not (sig and ts and exp):
                bt.logging.warning(f"_call_desearch_post({endpoint}): missing proof headers")
            return DesearchApiResponse(body=body_bytes, signature_hex=sig, timestamp=ts, expiry=exp)
        except Exception as e:
            bt.logging.warning(f"_call_desearch_post({endpoint}) failed: {e}")
            return None

    def call_desearch_web(self, statement: str) -> Optional[DesearchApiResponse]:
        """POST /desearch/ai/search/links/web with tools."""
        return self._call_desearch_post(
            DESEARCH_WEB_SEARCH_PATH,
            {"prompt": statement, "tools": DESEARCH_WEB_TOOLS},
        )

    def call_desearch_twitter(self, statement: str) -> Optional[DesearchApiResponse]:
        """POST /desearch/ai/search/links/twitter."""
        return self._call_desearch_post(
            DESEARCH_TWITTER_SEARCH_PATH,
            {"prompt": statement},
        )

    def _parse_serp_results(self, body: bytes) -> List[SourceEvidence]:
        """Parse legacy SERP GET /web response into SourceEvidence list."""
        try:
            data = json.loads(body.decode("utf-8"))
            items = data if isinstance(data, list) else data.get("results", data.get("data", []))
        except Exception:
            return []
        evidence: List[SourceEvidence] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = (item.get("link", item.get("url", "")) or "").strip()
            excerpt = (item.get("snippet", item.get("excerpt", "")) or "").strip()
            if url or excerpt:
                evidence.append(SourceEvidence(url=url, excerpt=excerpt, source_type=SourceType.DESEARCH.value))
        return evidence

    # The web endpoint returns multiple result groups (search_results, reddit_search_results,
    # wikipedia_search_results, youtube_search_results, etc.). Only groups listed here are
    # ingested as evidence; all others are discarded. Twitter is handled by a separate endpoint.
    DESEARCH_WEB_PRIORITY_KEYS = {"reddit_search_results"}

    def _parse_web_results(self, body: bytes) -> List[SourceEvidence]:
        """Parse POST /desearch/ai/search/links/web response. Only keeps priority result groups (reddit)."""
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        evidence: List[SourceEvidence] = []
        for key in self.DESEARCH_WEB_PRIORITY_KEYS:
            items = data.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = (item.get("link", item.get("url", "")) or "").strip()
                excerpt = (item.get("snippet", item.get("excerpt", "")) or "").strip()
                if url or excerpt:
                    evidence.append(SourceEvidence(url=url, excerpt=excerpt, source_type=SourceType.DESEARCH.value))
        return evidence

    def _parse_twitter_results(self, body: bytes) -> List[SourceEvidence]:
        """Parse POST /desearch/ai/search/links/twitter response. Extracts from miner_tweets."""
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return []
        tweets = data.get("miner_tweets", []) if isinstance(data, dict) else []
        evidence: List[SourceEvidence] = []
        for tweet in tweets:
            if not isinstance(tweet, dict):
                continue
            url = (tweet.get("url", "") or "").strip()
            excerpt = (tweet.get("text", "") or "").strip()
            if url or excerpt:
                evidence.append(SourceEvidence(url=url, excerpt=excerpt, source_type=SourceType.DESEARCH.value))
        return evidence

    def veridex_forward(self, synapse: VericoreSynapse) -> VericoreSynapse:
        bt.logging.info(f"{synapse.request_id} | Received Vericore request")
        statement = synapse.statement
        synapse.veridex_response = []

        valid_results: List[DesearchApiResponse] = []
        evidence_list: List[SourceEvidence] = []

        parsers = {
            "serp": self._parse_serp_results,
            "web": self._parse_web_results,
            "twitter": self._parse_twitter_results,
        }

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}
            if DESEARCH_ENABLE_SERP:
                futures["serp"] = pool.submit(self.call_desearch_serp_web_search, statement)
            if DESEARCH_ENABLE_WEB:
                futures["web"] = pool.submit(self.call_desearch_web, statement)
            if DESEARCH_ENABLE_TWITTER:
                futures["twitter"] = pool.submit(self.call_desearch_twitter, statement)

            for key, future in futures.items():
                try:
                    result = future.result()
                except Exception as e:
                    bt.logging.warning(f"{synapse.request_id} | Desearch {key} call raised: {e}")
                    continue
                if not result:
                    bt.logging.info(f"{synapse.request_id} | Desearch {key}: no response")
                    continue
                if not (result.signature_hex and result.timestamp and result.expiry):
                    bt.logging.warning(f"{synapse.request_id} | Desearch {key}: missing proof headers")
                    continue
                valid_results.append(result)
                parsed = parsers[key](result.body)
                taken = parsed[:DESEARCH_MAX_EVIDENCE_PER_SOURCE]
                evidence_list.extend(taken)
                bt.logging.info(
                    f"{synapse.request_id} | Desearch {key}: {len(taken)} evidence items (of {len(parsed)} parsed), "
                    f"body_len={len(result.body)} proof_sig_len={len(result.signature_hex)}"
                )

        if not valid_results:
            bt.logging.info(f"{synapse.request_id} | No valid Desearch responses, returning empty")
            return synapse

        synapse.desearch = [
            Desearch(
                response_body=base64.b64encode(r.body).decode("ascii"),
                proof=DesearchProof(
                    signature=r.signature_hex,
                    timestamp=r.timestamp,
                    expiry=r.expiry,
                ),
            )
            for r in valid_results
        ]
        synapse.veridex_response = evidence_list
        bt.logging.info(
            f"{synapse.request_id} | Miner returns {len(evidence_list)} evidence items "
            f"from {len(valid_results)} Desearch endpoint(s)"
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
