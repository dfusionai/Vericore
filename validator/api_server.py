import os
import time
import random
import traceback
import argparse
import asyncio
import json
import numpy as np

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import bittensor as bt
from veridex_protocol import VeridexSynapse, SourceEvidence
from validator.quality_model import VeridexQualityModel
from validator.active_tester import StatementGenerator
from validator.snippet_fetcher import SnippetFetcher

###############################################################################
# APIQueryHandler: handles miner queries, scores responses, and writes each
# result to its own uniquely named JSON file for later processing by the daemon.
###############################################################################
class APIQueryHandler:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()  # Creates dendrite, wallet, subtensor, metagraph only once.
        self.my_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        # Local moving scores (for tracking locally; the daemon aggregates independently)
        self.moving_scores = [1.0] * len(self.metagraph.S)
        self.quality_model = VeridexQualityModel()
        self.statement_generator = StatementGenerator()
        self.fetcher = SnippetFetcher()
        # Directory to write individual result files (shared with the daemon)
        self.results_dir = 'results'
        os.makedirs(self.results_dir, exist_ok=True)

    def get_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--custom", default="my_custom_value", help="Custom value")
        parser.add_argument("--netuid", type=int, default=1, help="Chain subnet uid")
        bt.subtensor.add_args(parser)
        bt.logging.add_args(parser)
        bt.wallet.add_args(parser)
        config = bt.config(parser)
        config.full_path = os.path.expanduser(
            "{}/{}/{}/netuid{}/validator".format(
                config.logging.logging_dir,
                config.wallet.name,
                config.wallet.hotkey_str,
                config.netuid,
            )
        )
        os.makedirs(config.full_path, exist_ok=True)
        return config

    def setup_logging(self):
        bt.logging(config=self.config, logging_dir=self.config.full_path)
        bt.logging.info("Starting APIQueryHandler with config:")
        bt.logging.info(self.config)

    def setup_bittensor_objects(self):
        bt.logging.info("Setting up Bittensor objects for API Server.")
        self.wallet = bt.wallet(config=self.config)
        bt.logging.info(f"Wallet: {self.wallet}")
        self.subtensor = bt.subtensor(config=self.config)
        bt.logging.info(f"Subtensor: {self.subtensor}")
        # Create the dendrite (used to query miners)
        self.dendrite = bt.dendrite(wallet=self.wallet)
        bt.logging.info(f"Dendrite: {self.dendrite}")
        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        bt.logging.info(f"Metagraph: {self.metagraph}")
        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error("Wallet not registered on chain. Run 'btcli register'.")
            exit()
        else:
            self.my_subnet_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            bt.logging.info(f"API Server running on uid: {self.my_subnet_uid}")

    async def handle_veridex_query(self, request_id: str, statement: str, sources: list,
                              is_test: bool = False, is_nonsense: bool = False) -> dict:
        """
        1. Query a subset of miners with the given statement.
        2. Verify that each snippet is truly on the page.
        3. Score the responses (apply domain factor, speed factor, etc.) and update
           the local moving_scores.
        4. Write the complete result (including final scores) to a uniquely named JSON file.
        """
        subset_axons = self._select_miner_subset(k=5)
        bt.logging.debug(subset_axons)
        synapse = VeridexSynapse(statement=statement, sources=sources)
        start_time = time.time()
        responses = await self.dendrite.forward(axons=subset_axons, synapse=synapse, timeout=120, deserialize=True)
        end_time = time.time()
        elapsed = end_time - start_time + 1e-9
        bt.logging.debug(responses)

        # If the query call returns None (instead of a list), substitute a list of None values
        if responses is None:
            bt.logging.warning("dendrite.query returned None; substituting with [None]*len(subset_axons)")
            responses = [None] * len(subset_axons)

        response_data = []
        for axon_info, resp in zip(subset_axons, responses):
            miner_hotkey = axon_info.hotkey
            miner_uid = self._hotkey_to_uid(miner_hotkey)
            if miner_uid is None:
                continue

            if resp is None or resp.veridex_response is None:
                final_score = -5.0
                self._update_moving_score(miner_uid, final_score)
                response_data.append({
                    "miner_hotkey": miner_hotkey,
                    "miner_uid": miner_uid,
                    "status": "no_response",
                    "raw_score": final_score
                })
                continue

            vericore_responses = []
            domain_counts = {}
            sum_of_snippets = 0.0
            for evid in resp.veridex_response:
                snippet_str = evid.excerpt.strip()
                if not snippet_str:
                    snippet_score = -1.0
                    vericore_responses.append({
                        "url": evid.url,
                        "excerpt": evid.excerpt,
                        "domain": self._extract_domain(evid.url),
                        "snippet_found": False,
                        "local_score": 0.0,
                        "snippet_score": snippet_score
                    })
                    sum_of_snippets += snippet_score
                    continue
                snippet_found = self._verify_snippet_in_rendered_page(evid.url, snippet_str)
                if not snippet_found:
                    snippet_score = -1.0
                    vericore_responses.append({
                        "url": evid.url,
                        "excerpt": evid.excerpt,
                        "domain": self._extract_domain(evid.url),
                        "snippet_found": False,
                        "local_score": 0.0,
                        "snippet_score": snippet_score
                    })
                    sum_of_snippets += snippet_score
                    continue
                domain = self._extract_domain(evid.url)
                times_used = domain_counts.get(domain, 0)
                domain_factor = 1.0 / (2 ** times_used)
                domain_counts[domain] = times_used + 1
                probs, local_score = self.quality_model.score_pair_distrib(statement, snippet_str)
                snippet_final = local_score * domain_factor
                vericore_responses.append({
                    "url": evid.url,
                    "excerpt": evid.excerpt,
                    "domain": domain,
                    "snippet_found": True,
                    "domain_factor": domain_factor,
                    "contradiction": probs["contradiction"],
                    "neutral": probs["neutral"],
                    "entailment": probs["entailment"],
                    "local_score": local_score,
                    "snippet_score": snippet_final
                })
                sum_of_snippets += snippet_final

            speed_factor = max(0.0, 1.0 - (elapsed / 15.0))
            final_score = sum_of_snippets * speed_factor
            if is_test and is_nonsense and final_score > 0.5:
                final_score -= 1.0
            final_score = max(-3.0, min(3.0, final_score))
            self._update_moving_score(miner_uid, final_score)
            response_data.append({
                "miner_hotkey": miner_hotkey,
                "miner_uid": miner_uid,
                "status": "ok",
                "speed_factor": speed_factor,
                "final_score": final_score,
                "vericore_responses": vericore_responses
            })

        result = {
            "status": "ok",
            "request_id": request_id,
            "statement": statement,
            "sources": sources,
            "results": response_data
        }
        # Write the result to a uniquely named file for the daemon.
        self.write_result_file(request_id, result)
        return result

    def write_result_file(self, request_id: str, result: dict):
        filename = os.path.join(self.results_dir, f"{request_id}.json")
        try:
            with open(filename, "w") as f:
                json.dump(result, f)
            bt.logging.info(f"Wrote result file: {filename}")
        except Exception as e:
            bt.logging.error(f"Error writing result file {filename}: {e}")

    def _update_moving_score(self, uid: int, new_raw_score: float):
        old_val = self.moving_scores[uid]
        self.moving_scores[uid] = 0.8 * old_val + 0.2 * new_raw_score

    def _select_miner_subset(self, k=5):
        all_axons = self.metagraph.axons
        if len(all_axons) <= k:
            return all_axons
        return random.sample(all_axons, k)

    def _hotkey_to_uid(self, hotkey: str) -> int:
        if hotkey in self.metagraph.hotkeys:
            return self.metagraph.hotkeys.index(hotkey)
        return None

    def _extract_domain(self, url: str) -> str:
        if "://" in url:
            parts = url.split("://", 1)[1].split("/", 1)
            return parts[0].lower()
        return url.lower()

    def _verify_snippet_in_rendered_page(self, url: str, snippet_text: str) -> bool:
        try:
            page_html = self.fetcher.fetch_entire_page(url)
            return snippet_text in page_html
        except Exception:
            return False

###############################################################################
# Set up FastAPI server
###############################################################################
app = FastAPI(title="Veridex API Server")

# Create the APIQueryHandler during startup and store it in app.state.
@app.on_event("startup")
async def startup_event():
    app.state.handler = APIQueryHandler()
    bt.logging.info("APIQueryHandler instance created at startup.")

@app.post("/veridex_query")
async def veridex_query(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    statement = data.get("statement")
    sources = data.get("sources", [])
    if not statement:
        raise HTTPException(status_code=400, detail="Missing 'statement'")
    request_id = f"req-{random.getrandbits(32):08x}"
    handler = app.state.handler
    result = await handler.handle_veridex_query(request_id, statement, sources)
    return JSONResponse(result)

if __name__ == "__main__":
    import uvicorn
    # Run uvicorn with one worker to ensure a single instance of APIQueryHandler.
    uvicorn.run("api_server:app", host="0.0.0.0", port=8080, reload=False)

