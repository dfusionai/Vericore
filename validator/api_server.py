import os
import time
import random
import argparse
import asyncio
import json
import logging
from typing import List

from bittensor import NeuronInfo
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import bittensor as bt

from shared.debug_util import DEBUG_LOCAL
from shared.veridex_protocol import (
    VericoreSynapse,
    VeridexResponse,
    VericoreMinerStatementResponse,
    VericoreQueryResponse,
    SourceEvidence,
)
from shared.scores import (
    UNREACHABLE_MINER_SCORE,
    INVALID_RESPONSE_MINER_SCORE,
    NO_STATEMENTS_PROVIDED_SCORE
)
from shared.log_data import LoggerType
from shared.proxy_log_handler import register_proxy_log_handler
from validator.snippet_validator import SnippetValidator
from validator.active_tester import StatementGenerator

from dotenv import load_dotenv
from dataclasses import asdict

# debug
bt.logging.set_trace()

load_dotenv()

REFRESH_INTERVAL_SECONDS = 60
NUMBER_OF_MINERS = 3

semaphore = asyncio.Semaphore(5)  # Limit to 10 threads at a time


LOWEST_FINAL_SCORE = -10
HIGHEST_FINAL_SCORE = 10

###############################################################################
# APIQueryHandler: handles miner queries, scores responses, and writes each
# result to its own uniquely named JSON file for later processing by the daemon.
###############################################################################
class APIQueryHandler:

    def __init__(self):
        self.config = self.get_config()
        bt.logging.info(f"__init {self.config}")
        self.setup_bittensor_objects()  # Creates dendrite, wallet, subtensor, metagraph only once.
        self.setup_logging()

        self.last_refresh_time: float = 0
        self.miners: List[NeuronInfo] = []

        self.refresh_miner_cache()

        self.my_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.statement_generator = StatementGenerator()
        # Directory to write individual result files (shared with the daemon)
        self.results_dir = "results"
        os.makedirs(self.results_dir, exist_ok=True)

    def get_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--custom", default="my_custom_value", help="Custom value")
        parser.add_argument("--netuid", type=int, default=1, help="Chain subnet uid")
        bt.subtensor.add_args(parser)
        bt.logging.add_args(parser)
        bt.wallet.add_args(parser)
        bt.axon.add_args(parser)
        config = bt.config(parser)

        bt.logging.info(f"get_config: {config}")
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
        bt_logger = logging.getLogger("bittensor")
        register_proxy_log_handler(bt_logger, LoggerType.Validator, self.wallet)

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

        self.axon = bt.axon(wallet=self.wallet, config=self.config)
        self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)

        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error("Wallet not registered on chain. Run 'btcli register'.")
            exit()
        else:
            self.my_subnet_uid = self.metagraph.hotkeys.index(
                self.wallet.hotkey.ss58_address
            )
            bt.logging.info(f"API Server running on uid: {self.my_subnet_uid}")

    async def call_axon(self, request_id, target_axon, synapse):
        start_time = time.time()
        bt.logging.info(f"{request_id} | Calling axon {target_axon.hotkey}")
        response = await self.dendrite.call(
            target_axon=target_axon, synapse=synapse, timeout=120, deserialize=True
        )
        bt.logging.info(f"{request_id} | Called axon {target_axon.hotkey}")
        end_time = time.time()
        elapsed = end_time - start_time + 1e-9
        veridex_response = VeridexResponse
        veridex_response.synapse = response
        veridex_response.elapse_time = elapsed
        return veridex_response

    def verify_miner_connection(
        self,
        miner_uid: int,
        miner_hotkey: str,
        request_id: str,
        neuron: NeuronInfo,
    ) -> VericoreMinerStatementResponse | None:
        # Could not find miner key - Shouldn't get here!
        if miner_uid is None:
            bt.logging.warning(
                f"{request_id} | Could not find miner uid for hotkey {miner_hotkey} "
            )
            miner_statement = VericoreMinerStatementResponse(
                miner_hotkey="", miner_uid=-1, status="invalid_miner", raw_score=0, final_score=0,
            )
            return miner_statement

        # Check if miner has any axon information
        if neuron.axon_info is None:
            bt.logging.warning(
                f"{request_id} | {miner_uid} | Miner doesn't have axon info"
            )
            miner_statement = VericoreMinerStatementResponse(
                miner_hotkey=miner_hotkey, miner_uid=miner_uid, status="unreachable_miner", raw_score=UNREACHABLE_MINER_SCORE, final_score=UNREACHABLE_MINER_SCORE
            )
            return miner_statement

        # Check if miner has valid ip address
        if not neuron.axon_info.is_serving:
            bt.logging.warning(
                f"{request_id} | {miner_uid} | Miner doesn't have reachable ip address"
            )
            miner_statement = VericoreMinerStatementResponse(
                miner_hotkey=miner_hotkey, miner_uid=miner_uid, status="unreachable_miner", raw_score=UNREACHABLE_MINER_SCORE, final_score=UNREACHABLE_MINER_SCORE
            )
            return miner_statement

        # miner is reachable
        return None

    def validate_miner_response(
        self,
        miner_uid: int,
        miner_hotkey: str,
        request_id: str,
        miner_response
    ) -> VericoreMinerStatementResponse | None:
        if (
            miner_response is None
            or miner_response.synapse.veridex_response is None
        ):
            bt.logging.warning(
                f"{request_id} | {miner_uid} | No miner response received"
            )
            miner_statement = VericoreMinerStatementResponse(
                miner_hotkey=miner_hotkey,
                miner_uid=miner_uid,
                status="no_response",
                raw_score=INVALID_RESPONSE_MINER_SCORE,
                final_score=INVALID_RESPONSE_MINER_SCORE,
            )
            return miner_statement

        veridex_responses: List[SourceEvidence] = miner_response.synapse.veridex_response
        if len(veridex_responses) == 0:
            bt.logging.warning(
                f"{request_id} | {miner_uid} | Miner didn't return any statements"
            )
            miner_statement = VericoreMinerStatementResponse(
                miner_hotkey=miner_hotkey,
                miner_uid=miner_uid,
                status="no_statements_provided",
                raw_score=NO_STATEMENTS_PROVIDED_SCORE,
                final_score=NO_STATEMENTS_PROVIDED_SCORE,
            )
            return miner_statement

        # Valid statements returned
        return None

    # async def process_miner_response_with_limit(self, *args):
    #     async with semaphore:
    #         return await asyncio.to_thread(self.process_miner_response, *args)

    def calculate_speed_factor(self, elapse_time: float) -> float:
        # The speed factor decreases with elapse_time:
        # - When elapse_time = 0, the score is 2.0.
        # - When elapse_time = 30, the score is 1.0.
        # - When elapse_time = 60, the score is clamped to 0.01 (min threshold).
        return max(1, 2.0 - (elapse_time / 30.0))

        # if elapse_time <= 15:
        #     return 4.0  # 0 to 15 seconds maps to a speed factor of 4
        # elif elapse_time <= 30:
        #     return 4.0 - ((elapse_time - 15) / 15) * 2  # Linearly decrease from 4 to 2 between 15 and 30 seconds
        # elif elapse_time <= 90:
        #     return 2.0 - ((elapse_time - 30) / 60) * 2  # Linearly decrease from 2 to 0 between 30 and 90 seconds
        # elif elapse_time <= 120:
        #     return 0.0 - ((elapse_time - 90) / 30) * 1  # Linearly decrease from 0 to -1 between 90 and 120 seconds
        # else:
        #     return -1.0  # For any time beyond 2 minutes, return -1

    async def process_miner_request(
        self,
        request_id: str,
        neuron : NeuronInfo,
        synapse: VericoreSynapse,
        statement: str,
        is_test: bool,
        is_nonsense: bool,
    ) -> VericoreMinerStatementResponse:
        miner_hotkey = neuron.hotkey
        miner_uid =  neuron.uid
        try:
            miner_statement = self.verify_miner_connection(
                miner_uid,
                miner_hotkey,
                request_id,
                neuron,
            )
            if miner_statement is not None:
                return miner_statement

            bt.logging.info(f"{request_id} | { miner_uid } | Calling axon ")

            # Call the miner
            try:
                miner_response = await self.call_axon(
                    target_axon=neuron.axon_info, request_id=request_id, synapse=synapse
                )
            except Exception as e:
                bt.logging.error(f"{request_id} | {miner_uid} | An error has occurred calling miner with error: {e}")
                # exception could have been from us?
                final_score = INVALID_RESPONSE_MINER_SCORE
                miner_statement = VericoreMinerStatementResponse(
                    miner_hotkey=miner_hotkey,
                    miner_uid=miner_uid,
                    status="no_response",
                    raw_score=final_score,
                    final_score=final_score,
                )
                return miner_statement

            bt.logging.info(
                f"{request_id} | { miner_uid } | Received miner information"
            )

            miner_statement = self.validate_miner_response(
                miner_uid,
                miner_hotkey,
                request_id,
                miner_response
            )
            if miner_statement is not None:
                bt.logging.warning(
                    f"{request_id} | {miner_uid} | Invalid miner response received"
                )
                return miner_statement

            # Process Vericore response data
            bt.logging.info(f"{request_id} | {miner_uid} | Verifying Miner Statements")

            # Create tasks
            validator = SnippetValidator()
            tasks = [
                validator.validate_miner_snippet(
                    request_id=request_id,
                    miner_uid=miner_uid,
                    original_statement=miner_response.synapse.statement,
                    miner_evidence=miner_vericore_response
                ) for miner_vericore_response in miner_response.synapse.veridex_response
            ]

            vericore_statement_responses = await asyncio.gather(*tasks)

            bt.logging.info(f"{request_id} | {miner_uid} | Scoring Miner Statements Based on Snippets")

            domain_counts = {}

            bt.logging.info(f"{request_id} | {miner_uid} | Calculating miner scores")

            # Check how many times the domain count was reused
            for statement_response in vericore_statement_responses:
                if statement_response.snippet_found:
                    domain_counts[statement_response.domain] = domain_counts.get(statement_response.domain, 0) + 1

            # Calculate the miner's statement score
            sum_of_snippets = 0
            for statement_response in vericore_statement_responses:
                if statement_response.snippet_found:
                    # Use times_used - 1 since we want first use to have no penalty
                    times_used = domain_counts.get(statement_response.domain, 1) - 1
                    domain_factor = 1.0 / (2**times_used)
                    statement_response.snippet_score = (
                        statement_response.local_score * domain_factor
                    )
                    statement_response.domain_factor = domain_factor

                # Add score of all snippets
                sum_of_snippets += statement_response.snippet_score

            # Calculate final score considering speed factor
            speed_factor = self.calculate_speed_factor(miner_response.elapse_time)

            bt.logging.info(f"{request_id} | {miner_uid} | Calculated Speed Factor: {speed_factor} | Miner response: {miner_response.elapse_time}")
            final_score = sum_of_snippets * speed_factor
            bt.logging.info(f"{request_id} | {miner_uid} | Final Score: {final_score} | Sum Of Snippets: {sum_of_snippets}")
            if is_test and is_nonsense and final_score > 0.5:
                final_score -= 1.0
            final_score = max(LOWEST_FINAL_SCORE, min(HIGHEST_FINAL_SCORE, final_score))

            bt.logging.info(f"{request_id} | {miner_uid} | Calculated Final Score: {final_score}")

            miner_statement = VericoreMinerStatementResponse(
                miner_hotkey=miner_hotkey,
                miner_uid=miner_uid,
                status="ok",
                speed_factor=speed_factor,
                final_score=final_score,
                raw_score=sum_of_snippets,
                elapsed_time=miner_response.elapse_time,
                vericore_responses=vericore_statement_responses,
            )
            return miner_statement
        except Exception as e:
            bt.logging.error(f"{request_id} | {miner_uid} | An error has occurred: {e}")
            # exception could have been from us?
            miner_statement = VericoreMinerStatementResponse(
                miner_hotkey=miner_hotkey,
                miner_uid=miner_uid,
                status="error",
                raw_score=INVALID_RESPONSE_MINER_SCORE,
                final_score=INVALID_RESPONSE_MINER_SCORE,
            )
            return miner_statement

    async def handle_query(
        self,
        request_id: str,
        statement: str,
        sources: list,
        is_test: bool = False,
        is_nonsense: bool = False,
    ) -> VericoreQueryResponse:
        """
        1. Query a subset of miners with the given statement.
        2. Verify that each snippet is truly on the page.
        3. Score the responses (apply domain factor, speed factor, etc.) and update
           the local moving_scores.
        4. Write the complete result (including final scores) to a uniquely named JSON file.
        """
        subset_neurons = self.select_miner_subset(k=NUMBER_OF_MINERS)

        miner_ids = [neuron.uid for neuron in subset_neurons]  # or neuron.uid
        selected_miners = ' '.join(f'[{mid}]' for mid in miner_ids)
        bt.logging.info(f"{request_id} | Selected miners: {selected_miners}")

        synapse = VericoreSynapse(
            statement=statement, sources=sources, request_id=request_id
        )
        # responses = await asyncio.gather(
        #     *[
        #         asyncio.create_task(
        #             self.process_miner_request(request_id, neuron, synapse, statement, is_test, is_nonsense)
        #         )
        #         for neuron in subset_neurons
        #     ]
        # )
        responses = await asyncio.gather(
            *[
                self.process_miner_request(request_id, neuron, synapse, statement, is_test, is_nonsense)
                for neuron in subset_neurons
            ]
        )
        bt.logging.info(f"{request_id} | Completed all miner requests")

        response = VericoreQueryResponse(
            status="ok",
            validator_uid=self.my_uid,
            validator_hotkey=self.wallet.hotkey.ss58_address,
            request_id=request_id,
            statement=statement,
            sources=sources,
            results=responses,
        )

        return response

    def write_result_file(self, request_id: str, result: VericoreQueryResponse):
        filename = os.path.join(self.results_dir, f"{request_id}.json")
        try:
            with open(filename, "w") as f:
                json.dump(asdict(result), f)
            bt.logging.info(f"{request_id} | Wrote result file: {filename}")
        except Exception as e:
            bt.logging.error(f"Error writing result file {filename}: {e}")

    def determine_miners(self, neurons: List[NeuronInfo]):
        if DEBUG_LOCAL:
            bt.logging.info("Returning all neurons since valid permit is all set to true for local")
            return neurons

        bt.logging.info("Determining miners")
        # return [n for n in neurons if not n.validator_permit]
        return [n for n in neurons]

    def refresh_miner_cache(self):
        current_time = time.time()
        if  (current_time - self.last_refresh_time) > REFRESH_INTERVAL_SECONDS:
            bt.logging.info("Refreshing metagraph")
            self.metagraph.sync()  # Fetch new data
            neurons = self.subtensor.neurons(netuid=self.config.netuid)
            bt.logging.debug(f"Found {len(neurons)} neurons")
            self.miners = self.determine_miners(neurons)
            bt.logging.info(f"Found {len(self.miners)} miners")

    def select_miner_subset(self, k=5):
        self.refresh_miner_cache()

        bt.logging.info(f"Selecting miner subset:")

        all_miners = self.miners
        if len(all_miners) <= k:
            return all_miners

        selected_miners = random.sample(all_miners, k)

        null_miners = [miner for miner in selected_miners if miner.axon_info is None or not miner.axon_info.is_serving]

        if null_miners:
            bt.logging.warning(f"Detected {len(null_miners)} miners with null axons. Fetching replacements...")

            available_replacements = [miner for miner in all_miners if miner not in selected_miners and miner.axon_info is not None and miner.axon_info.is_serving]

            # Add replacements for the miners that have null axons
            for i, null_miner in enumerate(null_miners):
                if available_replacements:
                    replacement = random.choice(available_replacements)
                    selected_miners.append(replacement)
                    available_replacements.remove(replacement)
                else:
                    break

        bt.logging.info(f"Selected {len(selected_miners)} miners with {len(null_miners)} null axons")
        return selected_miners

    def _hotkey_to_uid(self, hotkey: str) -> int:
        if hotkey in self.metagraph.hotkeys:
            return self.metagraph.hotkeys.index(hotkey)
        return None

###############################################################################
# Set up FastAPI server
###############################################################################

@asynccontextmanager
async def lifespan(app: FastAPI):
    bt.logging.info("Application is starting...")
    await startup_event()
    yield  # This keeps the app running
    bt.logging.info("Application is shutting down...")


app = FastAPI(title="Vericore API Server", lifespan=lifespan)

# DEBUG ONLY
# Allowed origins (domains that can access the API)
# origins = [
#     "http://localhost:4200",  # Allow local frontend apps
# ]
origins = [
    "*",
]


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allowed origins
    allow_credentials=True,  # Allow sending cookies (useful for auth)
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)


# Create the APIQueryHandler during startup and store it in app.state.
async def startup_event():
    print("startup_event")
    app.state.handler = APIQueryHandler()
    print("APIQueryHandler instance created at startup.")


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
    timestamp = time.time()
    handler = app.state.handler
    start_time = time.perf_counter()
    result: VericoreQueryResponse = await handler.handle_query(request_id, statement, sources)
    end_time = time.perf_counter()
    duration = end_time - start_time
    bt.logging.info(
        f"{request_id} | Finished processing at {end_time} (Duration: {duration:.4f} seconds)"
    )
    result.timestamp = timestamp
    result.total_elapsed_time = duration

    handler.write_result_file(request_id, result)

    return JSONResponse(asdict(result))


if __name__ == "__main__":
    import uvicorn

    # Run uvicorn with one worker to ensure a single instance of APIQueryHandler.
    uvicorn.run(
        "validator.api_server:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        timeout_keep_alive=500,
        workers=1,
    )
