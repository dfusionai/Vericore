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

from veridex_protocol import VeridexSynapse

app = Sanic("VeridexApp")

class VeridexValidator:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()
        self.my_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.scores = [1.0] * len(self.metagraph.S)

        # Keep track of last chain update
        self.last_update = self.subtensor.blocks_since_last_update(
            self.config.netuid, self.my_uid
        )
        self.tempo = self.subtensor.tempo(self.config.netuid)

        # We'll store the scores in a simple list
        self.alpha = 0.1
        self.moving_avg_scores = [1.0] * len(self.metagraph.S)

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

        # Basic init weights
        self.scores = [1.0] * len(self.metagraph.S)
        bt.logging.info(f"Initial Weights: {self.scores}")

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
                # We do NOT generate random queries in the loop;
                # queries come in via /veridex_query from the user.

                # Periodically update chain weights with softmax
                self.last_update = self.subtensor.blocks_since_last_update(
                    self.config.netuid, self.my_uid
                )
                if self.last_update > self.tempo + 1:
                    arr = np.array(self.moving_avg_scores)
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
                time.sleep(5)

            except KeyboardInterrupt:
                bt.logging.success("Keyboard interrupt detected. Exiting validator.")
                exit()
            except Exception as e:
                bt.logging.error(e)
                traceback.print_exc()

    def handle_veridex_query(self, statement: str, sources: list) -> dict:
        """
        Broadcast a query (statement + sources) to all miners,
        then gather and return the results. Also update moving_avg_scores
        with the aggregator logic: random factor + time + trust, then softmax later in run().
        """
        synapse = VeridexSynapse(statement=statement, sources=sources)

        start_time = time.time()
        responses = self.dendrite.query(
            axons=self.metagraph.axons, synapse=synapse, timeout=12
        )
        end_time = time.time()

        valid_responses = [
            r for r in responses if r is not None and r.veridex_response is not None
        ]
        if not valid_responses:
            return {
                "status": "no_responses",
                "message": "No miner responded in time or no valid response."
            }

        elapsed = end_time - start_time + 1e-9
        new_scores = []
        for i, resp in enumerate(valid_responses):
            # random "refutation/corroboration" in [0,1]
            random_factor = random.random()

            # incorporate response time (shorter is better); simple example
            time_score = max(0, 1 - (elapsed / 15.0))

            # trust factor if certain domains are present
            trust_factor = 1.0
            for (url, xpath) in resp.veridex_response:
                if "wikipedia.org" in url.lower() or "cointelegraph.com" in url.lower():
                    trust_factor *= 1.2

            combined_score = random_factor * time_score * trust_factor

            if i < len(self.moving_avg_scores):
                self.moving_avg_scores[i] = (
                    (1 - self.alpha) * self.moving_avg_scores[i]
                    + self.alpha * combined_score
                )
            new_scores.append(combined_score)

        # Build a response
        all_data = []
        for i, r in enumerate(valid_responses):
            all_data.append({
                "miner_index": i,
                "statement": statement,
                "sources": sources,
                "veridex_response": r.veridex_response,
            })

        return {
            "status": "ok",
            "aggregated_scores": new_scores,
            "responses": all_data
        }


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
