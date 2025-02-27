import os
import time
import random
import traceback
import argparse
import threading
import numpy as np
import string
import multiprocessing
import queue
import asyncio

# Sanic
from sanic import Sanic
from sanic.request import Request
from sanic.response import json
from sanic_ext import Extend
# Bittensor and Validator
import bittensor as bt
from veridex_protocol import VericoreSynapse, SourceEvidence
from validator.quality_model import VeridexQualityModel
from validator.active_tester import StatementGenerator
from validator.snippet_fetcher import SnippetFetcher



########################################
# The main validator code
########################################
class VeridexValidator:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()
        self.my_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)

        # We'll store a "score" for each miner (UID)
        self.moving_scores = [1.0] * len(self.metagraph.S)

        # For chain updates
        self.last_update = self.subtensor.blocks_since_last_update(self.config.netuid, self.my_uid)
        self.tempo = self.subtensor.tempo(self.config.netuid)

        # Our RoBERTa-based model for snippet alignment
        self.quality_model = VeridexQualityModel()

        # For generating random statements
        self.statement_generator = StatementGenerator()

        # For fetching page HTML (rendered)
        self.fetcher = SnippetFetcher()

        # Probability of “active test” each cycle
        self.active_test_prob = 0.3

    def get_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--custom", default="my_custom_value", help="Adds a custom value to the parser.")
        parser.add_argument("--netuid", type=int, default=1, help="The chain subnet uid.")
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
            f"Running VeridexValidator for subnet: {self.config.netuid} "
            f"on network: {self.config.subtensor.network} with config:"
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
                f"Your validator: {self.wallet} is not registered to chain connection: {self.subtensor}.\n"
                f"Run 'btcli register' and try again."
            )
            exit()
        else:
            self.my_subnet_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            bt.logging.info(f"Running validator on uid: {self.my_subnet_uid}")

    def run_main_loop_with_queue(self, task_queue, result_dict):
        """
        Main loop that:
          1) Periodically does active tests & chain updates
          2) Polls the queue for incoming requests
             (request_id, statement, sources)
          3) Processes them with handle_veridex_query
          4) Puts result in result_dict
        """
        bt.logging.info("Starting validator main loop (queue-based).")

        while True:
            try:
                # 1) Possibly run an active test
                if random.random() < self.active_test_prob:
                    self._perform_active_test()

                # 2) Periodically update chain weights
                self.last_update = self.subtensor.blocks_since_last_update(self.config.netuid, self.my_uid)
                if self.last_update > self.tempo + 1:
                    self._sync_and_set_weights()

                # 3) Poll the queue for tasks
                #    We'll use nowait + try/except so we can keep looping,
                #    or a small batch. If we want to handle multiple tasks, we can do so.
                handled_something = False
                while True:
                    try:
                        request_id, statement, sources = task_queue.get_nowait()
                    except queue.Empty:
                        break  # no more tasks
                    except Exception as e:
                        bt.logging.error(f"Queue error: {e}")
                        break
                    else:
                        # We got a task: handle it
                        bt.logging.info(f"Got request_id={request_id} from queue.")
                        result = self.handle_veridex_query(statement, sources)
                        # Put the result in the dict
                        result_dict[request_id] = result
                        handled_something = True

                # If we handled tasks or not, let's just do a short sleep
                # so we don't spin too fast.
                time.sleep(0.1)

            except KeyboardInterrupt:
                bt.logging.success("Keyboard interrupt in validator. Exiting.")
                return
            except Exception as e:
                bt.logging.error(f"Error in validator loop: {e}")
                traceback.print_exc()
                # keep going or break as needed

    def _perform_active_test(self):
        """Generate random statement, query subset, score responses."""
        statement, is_nonsense = self.statement_generator.generate_statement()
        sources = []
        bt.logging.info(f"[Active Test] Generated statement: '{statement}' (nonsense={is_nonsense})")
        _ = self.handle_veridex_query(statement, sources, is_test=True, is_nonsense=is_nonsense)

    def _sync_and_set_weights(self):
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
        1) Query subset of miners with the statement.
        2) For each valid response, verify snippet is truly on page (with Selenium).
        3) Apply domain factor, speed factor, nonsense penalty, etc.
        """
        subset_axons = self._select_miner_subset(k=5)
        synapse = VericoreSynapse(statement=statement, sources=sources)

        start_time = time.time()
        responses = self.dendrite.query(axons=subset_axons, synapse=synapse, timeout=12)
        end_time = time.time()
        elapsed = end_time - start_time + 1e-9

        response_data = []

        for axon_info, resp in zip(subset_axons, responses):
            miner_hotkey = axon_info.hotkey
            miner_uid = self._hotkey_to_uid(miner_hotkey)
            if miner_uid is None:
                # Not found or invalid
                continue

            if resp is None or resp.veridex_response is None:
                # No or invalid response => penalty
                final_score = -2.0
                self._update_moving_score(miner_uid, final_score)
                response_data.append({
                    "miner_hotkey": miner_hotkey,
                    "miner_uid": miner_uid,
                    "status": "no_response",
                    "raw_score": final_score
                })
                continue

            # We'll do domain factor, roberta scoring, snippet-check, etc.
            vericore_responses = []
            domain_counts = {}
            sum_of_snippets = 0.0

            for evid in resp.veridex_response:
                snippet_str = evid.excerpt.strip()
                if not snippet_str:
                    # If snippet is empty, penalize
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

                # Domain factor
                domain = self._extract_domain(evid.url)
                times_used = domain_counts.get(domain, 0)
                domain_factor = 1.0 / (2 ** times_used)
                domain_counts[domain] = times_used + 1

                # Score snippet with RoBERTa
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

            # speed factor
            # todo elapsed time should be per miner and not total time elapsed
            speed_factor = max(0.0, 1.0 - (elapsed / 15.0))

            # final_score
            final_score = sum_of_snippets * speed_factor

            # nonsense penalty
            if is_test and is_nonsense and final_score > 0.5:
                final_score -= 1.0

            # clamp
            final_score = max(-3.0, min(3.0, final_score))

            # update moving score
            self._update_moving_score(miner_uid, final_score)

            response_data.append({
                "miner_hotkey": miner_hotkey,
                "miner_uid": miner_uid,
                "status": "ok",
                "speed_factor": speed_factor,
                "final_score": final_score,
                "vericore_responses": vericore_responses
            })

        return {
            "status": "ok",
            "statement": statement,
            "sources": sources,
            "results": response_data
        }

    def _verify_snippet_in_rendered_page(self, url: str, snippet_text: str) -> bool:
        try:
            page_html = self.fetcher.fetch_entire_page(url)
            return snippet_text in page_html
        except:
            return False

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


########################################
# Sanic server code (main process)
########################################
app = Sanic("VeridexQueueApp")

# DEBUG ONLY
app.config.CORS_ORIGIN = "http://localhost:4200"
app.config.REQUEST_TIMEOUT = 300  # 5 minutes
app.config.RESPONSE_TIMEOUT = 300  # 5 minutes
Extend(app)

# We'll keep references to the queue + result_dict (populated by the validator).
task_queue = None
result_dict = None


@app.middleware("response")
async def update_headers(request, response):
    origin = request.headers.get("origin")
    response.headers.update({"Access-Control-Allow-Origin": origin})

@app.post("/veridex_query")
async def veridex_query(request: Request):
    """
    Receives a statement + sources. Enqueues them with a request_id.
    Waits for the validator process to produce a result, then returns JSON.
    """
    global task_queue, result_dict

    data = request.json or {}
    statement = data.get("statement")
    sources = data.get("sources", [])

    if not statement:
        return json({"status": "error", "message": "Missing 'statement' in JSON"}, status=400)

    # Generate a unique request_id for tracking
    request_id = f"req-{random.getrandbits(32):08x}"  # or any unique generator

    # Place the task on the queue
    task_queue.put((request_id, statement, sources))

    # Poll for the result
    # We'll do a simple async loop waiting for the validator to fill it
    while request_id not in result_dict:
        await asyncio.sleep(0.1)

    # Retrieve the result
    result = result_dict[request_id]
    # Optionally remove from dict to not accumulate data
    del result_dict[request_id]

    return json(result)


########################################
# Main entry point
########################################
if __name__ == "__main__":
    # We use a multiprocessing.Manager to create shared objects (queue, dict)
    with multiprocessing.Manager() as manager:
        # Create the queue and dict
        task_queue = manager.Queue()
        result_dict = manager.dict()

        # Save references into the global variables so the route can use them
        globals()["task_queue"] = task_queue
        globals()["result_dict"] = result_dict

        # Spawn the validator in its own process
        def validator_process():
            # Construct the validator
            validator = VeridexValidator()
            # Run its loop, which also checks the queue for tasks
            validator.run_main_loop_with_queue(task_queue, result_dict)

        p = multiprocessing.Process(target=validator_process, daemon=True)
        p.start()

        # Now run the Sanic server in the main process
        # single_process=True ensures we don't fork again
        app.run(
            host="0.0.0.0",
            port=8080,
            debug=False,
            workers=1,
            single_process=True
        )

        # If the server exits for some reason, kill the validator process
        p.terminate()
        p.join()

