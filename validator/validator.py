import os
import time
import random
import argparse
import traceback
import threading
import numpy as np

import bittensor as bt

# Sanic imports
from sanic import Sanic
from sanic.request import Request
from sanic.response import json

from veridex_protocol import VeridexSynapse, SourceEvidence
from validator.quality_model import VeridexQualityModel
from validator.active_tester import StatementGenerator
from validator.snippet_fetcher import SnippetFetcher

app = Sanic("VeridexApp")

class VeridexValidator:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()
        self.my_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        
        # The raw "scores" for each miner. We'll update them after each query.
        self.moving_scores = [1.0] * len(self.metagraph.S)

        # For chain updates
        self.last_update = self.subtensor.blocks_since_last_update(
            self.config.netuid, self.my_uid
        )
        self.tempo = self.subtensor.tempo(self.config.netuid)

        # Our RoBERTa-based model for scoring snippet alignment
        self.quality_model = VeridexQualityModel()

        # For generating random statements
        self.statement_generator = StatementGenerator()

        # For fetching snippet text
        self.fetcher = SnippetFetcher()

        # Probability of “active test” in each cycle
        self.active_test_prob = 0.3

    def get_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--custom",
            default="my_custom_value",
            help="Adds a custom value to the parser.",
        )
        parser.add_argument(
            "--netuid", type=int, default=1, help="The chain subnet uid."
        )
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
        bt.logging.info(
            f"Running VeridexValidator for subnet: {self.config.netuid} on network: {self.config.subtensor.network} with config:"
        )
        bt.logging.info(self.config)

    def setup_bittensor_objects(self):
        bt.logging.info("Setting up Bittensor objects.")
        self.wallet = bt.wallet(config=self.config)
        bt.logging.info(f"Wallet: {self.wallet}")

        self.subtensor = bt.subtensor(config=self.config)
        bt.logging.info(f"Subtensor: {self.subtensor}")

        self.dendrite = bt.dendrite(wallet=self.wallet)
        bt.logging.info(f"Dendrite: {self.dendrite}")

        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        bt.logging.info(f"Metagraph: {self.metagraph}")

        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error(
                f"Your validator: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            self.my_subnet_uid = self.metagraph.hotkeys.index(
                self.wallet.hotkey.ss58_address
            )
            bt.logging.info(f"Running validator on uid: {self.my_subnet_uid}")

        bt.logging.info(f"Initial Scores: {self.moving_scores}")

    def run(self):
        # Start the Sanic server in a separate thread so the main loop can keep running
        server_thread = threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=8080, debug=False, access_log=False),
            daemon=True
        )
        server_thread.start()

        bt.logging.info("Starting validator main loop.")

        while True:
            try:
                # Occasionally do "active testing" on some subset of miners
                if random.random() < self.active_test_prob:
                    self._perform_active_test()

                # Periodically update chain weights 
                self.last_update = self.subtensor.blocks_since_last_update(
                    self.config.netuid, self.my_uid
                )
                if self.last_update > self.tempo + 1:
                    self._sync_and_set_weights()

                time.sleep(5)

            except KeyboardInterrupt:
                bt.logging.success("Keyboard interrupt detected. Exiting validator.")
                exit()
            except Exception as e:
                bt.logging.error(e)
                traceback.print_exc()

    def _perform_active_test(self):
        """
        Generate a random statement (maybe nonsense, maybe real).
        Query a subset of miners. Score their responses.
        """
        statement, is_nonsense = self.statement_generator.generate_statement()
        # We'll pass an empty 'sources' or some random sources
        sources = []

        bt.logging.info(f"[Active Test] Generated statement: '{statement}' (nonsense={is_nonsense})")
        _ = self.handle_veridex_query(statement, sources, is_test=True, is_nonsense=is_nonsense)

    def _sync_and_set_weights(self):
        # Convert raw scores to a softmax distribution
        arr = np.array(self.moving_scores)
        exp_arr = np.exp(arr)
        weights = (exp_arr / np.sum(exp_arr)).tolist()

        bt.logging.info(f"[blue]Setting weights via softmax: {weights}[/blue]")
        self.subtensor.set_weights(
            netuid=self.config.netuid,
            wallet=self.wallet,
            uids=self.metagraph.uids,
            weights=weights,
            wait_for_inclusion=True,
        )
        self.metagraph.sync()

    def handle_veridex_query(self, statement: str, sources: list, 
                             is_test: bool=False, is_nonsense: bool=False) -> dict:
        """
        Broadcast a query (statement + sources) to a subset of miners,
        gather and return results. 
        Also update moving_scores for each miner in that subset.

        If is_test==True and is_nonsense==True, we penalize miners 
        that strongly claim "corroboration" or "refutation".
        """
        subset_axons = self._select_miner_subset(k=5)  # pick e.g. 5 random miners

        synapse = VeridexSynapse(statement=statement, sources=sources)

        start_time = time.time()
        responses = self.dendrite.query(
            axons=subset_axons, 
            synapse=synapse, 
            timeout=12
        )
        end_time = time.time()
        elapsed = end_time - start_time + 1e-9  # for speed calc

        # For returning data to the user
        response_data = []

        # Keep track of which hotkeys responded
        responded_hotkeys = set()

        # For each axon, see if they responded in time with a valid response
        for axon_info, resp in zip(subset_axons, responses):
            miner_hotkey = axon_info.hotkey
            miner_uid = self._hotkey_to_uid(miner_hotkey)
            if miner_uid is None:
                # Shouldn't happen if they're in the subgraph, but just in case
                continue

            if resp is None or resp.veridex_response is None:
                # Did not respond or invalid response => big penalty
                final_score = -2.0
                self._update_moving_score(miner_uid, final_score)
                response_data.append({
                    "miner_hotkey": miner_hotkey,
                    "miner_uid": miner_uid,
                    "status": "no_response",
                    "raw_score": final_score
                })
                continue

            # Mark as responded
            responded_hotkeys.add(miner_hotkey)

            # 1) Collect snippet texts
            snippet_texts = []
            domain_counts = {}
            snippet_details = []  # we'll store snippet-level info for the final JSON

            for evid in resp.veridex_response:
                # fetch snippet (or use excerpt if present)
                snippet_str = evid.excerpt.strip()
                if not snippet_str:
                    snippet_str = self.fetcher.fetch_snippet_text(
                        evid.url, evid.xpath, evid.start_char, evid.end_char
                    )
                # figure out domain factor
                domain = self._extract_domain(evid.url)
                times_used = domain_counts.get(domain, 0)
                # diminishing returns: e.g. 1.0 if first time, 0.5 if second, 0.25 if third, etc.
                domain_factor = 1.0 / (2**times_used)
                domain_counts[domain] = times_used + 1

                snippet_texts.append((snippet_str, domain_factor, domain))

            # 2) For each snippet, compute local_score from RoBERTa, multiply by domain_factor
            sum_of_snippets = 0.0
            snippet_distribs_combined = []  # store the distribution + final snippet_score

            for snippet_str, dom_factor, domain in snippet_texts:
                # Evaluate snippet quality
                probs, local_score = self.quality_model.score_pair_distrib(statement, snippet_str)
                # snippet_final = local_score * dom_factor
                snippet_final = local_score * dom_factor

                snippet_distribs_combined.append({
                    "domain": domain,
                    "domain_factor": dom_factor,
                    "contradiction": probs["contradiction"],
                    "neutral": probs["neutral"],
                    "entailment": probs["entailment"],
                    "local_score": local_score,
                    "snippet_score": snippet_final
                })
                sum_of_snippets += snippet_final

            # 3) speed factor: let's define in [0,1], so if you take too long you get hammered
            # e.g. speed_factor = max(0.0, 1.0 - elapsed/15)
            # If they answered in < 15s => partial credit, >15 => 0
            speed_factor = max(0.0, 1.0 - (elapsed / 15.0))

            # 4) final_score before nonsense penalty
            final_score = sum_of_snippets * speed_factor

            # 5) nonsense penalty if statement is nonsense but final_score is suspiciously high
            if is_test and is_nonsense and final_score > 0.5:
                final_score -= 1.0

            # 6) clamp final score
            final_score = max(-3.0, min(3.0, final_score))

            # 7) update the moving score
            self._update_moving_score(miner_uid, final_score)

            # 8) record data
            response_data.append({
                "miner_hotkey": miner_hotkey,
                "miner_uid": miner_uid,
                "status": "ok",
                "sum_of_snippets": sum_of_snippets,
                "speed_factor": speed_factor,
                "final_score": final_score,
                "veridex_response": [
                    {
                        "url": e.url,
                        "xpath": e.xpath,
                        "start_char": e.start_char,
                        "end_char": e.end_char
                    } for e in resp.veridex_response
                ],
                # Include snippet-level distributions, domain factor usage
                "snippet_distributions": snippet_distribs_combined
            })

        return {
            "status": "ok",
            "statement": statement,
            "sources": sources,
            "results": response_data
        }

    def _update_moving_score(self, uid: int, new_raw_score: float):
        """
        Momentum update:
          new_val = 0.8 * old_val + 0.2 * new_raw_score
        """
        old_val = self.moving_scores[uid]
        self.moving_scores[uid] = 0.8 * old_val + 0.2 * new_raw_score

    def _select_miner_subset(self, k=5):
        """
        Naive approach:
          - Randomly pick k axons from the entire metagraph
        Could do weighted picks based on self.moving_scores, etc.
        """
        all_axons = self.metagraph.axons
        if len(all_axons) <= k:
            return all_axons
        return random.sample(all_axons, k)

    def _hotkey_to_uid(self, hotkey: str) -> int:
        """
        Return the UID for a given hotkey or None if not found.
        """
        if hotkey in self.metagraph.hotkeys:
            return self.metagraph.hotkeys.index(hotkey)
        return None

    def _extract_domain(self, url: str) -> str:
        """
        A quick hack to parse domain from URL. 
        You might prefer using the standard library 'urllib.parse' or 'tldextract'.
        """
        if "://" in url:
            parts = url.split("://", 1)[1].split("/", 1)
            return parts[0].lower()
        return url.lower()

# Global reference to the validator instance
validator_instance: VeridexValidator = None

@app.post("/veridex_query")
async def veridex_query(request: Request):
    """
    Expects JSON like:
    {
       "statement": "Bitcoin is digital gold",
       "sources": ["https://en.wikipedia.org/wiki/Bitcoin"]
    }
    Returns a JSON dict with:
      - "statement", "sources"
      - "results": a list of responses from each miner in the subset
        including snippet-level distributions and final scores
    """
    if not request.json or "statement" not in request.json:
        return json({"status": "error", "message": "Missing 'statement' in JSON"}, status=400)

    statement = request.json["statement"]
    sources = request.json.get("sources", [])

    global validator_instance
    if validator_instance is None:
        return json({"status": "error", "message": "Validator not initialized"}, status=500)

    result = validator_instance.handle_veridex_query(statement, sources)
    return json(result)

if __name__ == "__main__":
    validator_instance = VeridexValidator()
    validator_instance.run()
