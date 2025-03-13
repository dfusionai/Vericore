import os
import time
import random
import argparse
import asyncio
import json
import logging
from typing import List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import bittensor as bt

from shared.veridex_protocol import VericoreSynapse, SourceEvidence, VeridexResponse, VericoreStatementResponse,  VericoreMinerStatementResponse, VericoreQueryResponse
from shared.log_data import LoggerType
from shared.proxy_log_handler import register_proxy_log_handler
from validator.quality_model import VeridexQualityModel
from validator.verify_context_quality_model import VerifyContextQualityModel
from validator.active_tester import StatementGenerator
from validator.snippet_fetcher import SnippetFetcher
from validator.domain_validator import domain_is_recently_registered
# from fuzzywuzzy import fuzz
# import lxml.html

from dotenv import load_dotenv

from dataclasses import asdict

from bs4 import BeautifulSoup

# debug
bt.logging.set_trace()

# debug
load_dotenv()


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

        self.my_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        # Local moving scores (for tracking locally; the daemon aggregates independently)
        self.moving_scores = [1.0] * len(self.metagraph.S)
        self.quality_model = VeridexQualityModel()
        self.verify_quality_model =  VerifyContextQualityModel()
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
        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error("Wallet not registered on chain. Run 'btcli register'.")
            exit()
        else:
            self.my_subnet_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            bt.logging.info(f"API Server running on uid: {self.my_subnet_uid}")

    async def call_axon(self, request_id, target_axon, synapse):
        start_time = time.time()
        bt.logging.info(f"{request_id} | Calling axon {target_axon.hotkey}")
        response =  await self.dendrite.call(target_axon=target_axon, synapse=synapse, timeout=120, deserialize=True)
        bt.logging.info(f"{request_id} | Called axon {target_axon.hotkey}")
        end_time = time.time()
        elapsed = end_time - start_time + 1e-9
        veridex_response = VeridexResponse
        veridex_response.synapse = response
        veridex_response.elapse_time = elapsed
        return veridex_response

    def process_miner_response(self, request_id, evid, statement):
      start_time = time.time()
      bt.logging.info(f"{request_id} | Started miner response at {start_time}")

      domain = self._extract_domain(evid.url)

      bt.logging.info(f"{request_id} | Verifying miner statement ")
      snippet_str = evid.excerpt.strip()
      # snippet was not processed - Score: -1
      if not snippet_str:
        snippet_score = -1.0
        vericore_miner_response = VericoreStatementResponse(
	        url=evid.url,
          excerpt = evid.excerpt,
          domain = domain,
          snippet_found = False,
          local_score = 0.0,
          snippet_score = snippet_score
        )
        return vericore_miner_response

      bt.logging.info(f'{request_id} | Verifying Snippet')

      # Fetch page text
      page_text = self._fetch_page_text(evid.url)

      # Verify that the snippet is actually within the provided url
      # #todo - ask patrick - should we split score between url exists and whether the web-page does include the snippet
      snippet_found = self._verify_snippet_in_rendered_page(request_id, page_text, snippet_str)

      bt.logging.info(f'{request_id} | Url: {evid.url} | Snippet: {snippet_str} | Snippet Verified  {snippet_found}')

      # Snippet was not found from the provided url
      # #todo - ask patrick - should we penalise more for provided urls without the extracted snippet
      if not snippet_found:
        snippet_score = -1.0
        vericore_miner_response = VericoreStatementResponse(
  	      url=evid.url,
          excerpt = evid.excerpt,
          domain = domain,
          snippet_found = False,
          local_score = 0.0,
          snippet_score = snippet_score
        )
        return vericore_miner_response

      # Dont score if domain was registered within 30 days.
      domain_registered_recently = domain_is_recently_registered(domain)
      bt.logging.info(f'{request_id} | Is domain registered recently: {domain_registered_recently}')
      if domain_registered_recently:
        snippet_score = -1.0
        vericore_miner_response = VericoreStatementResponse(
		      url=evid.url,
		      excerpt=evid.excerpt,
		      domain=domain,
		      snippet_found=False,
		      local_score=0.0,
		      snippet_score=snippet_score
	      )
        return vericore_miner_response

      probs, local_score = self.quality_model.score_pair_distrib(statement, snippet_str)
      vericore_miner_response = VericoreStatementResponse(
        url = evid.url,
        excerpt = evid.excerpt,
        domain = domain,
        snippet_found = True,
        domain_factor = 0,
        contradiction = probs["contradiction"],
        neutral = probs["neutral"],
        entailment = probs["entailment"],
        local_score = local_score,
        snippet_score = 0
      )
      end_time = time.time()
      bt.logging.info(f"{request_id} | Finished miner snippet at {end_time} (Duration: {end_time - start_time})")
      return vericore_miner_response

    async def process_miner_request(
		    self,
		    request_id: str,
		    axon,
		    synapse: VericoreSynapse,
		    statement: str,
		    is_test: bool,
		    is_nonsense: bool
    )-> VericoreMinerStatementResponse:

       miner_hotkey = axon.hotkey
       miner_uid = self._hotkey_to_uid(miner_hotkey)

       bt.logging.info(f'{request_id} | { miner_uid } | Calling axon ')
       # Call the miner
       miner_response = await self.call_axon(target_axon=axon, request_id=request_id, synapse=synapse)

       bt.logging.info(f'{request_id} | { miner_uid } | Received miner information')
       if miner_uid is None:
         miner_statement = VericoreMinerStatementResponse(
		       miner_hotkey='',
		       miner_uid=-1,
		       status="no_response",
		       raw_score=0
	       )
         return miner_statement

       if miner_response is None or miner_response.synapse.veridex_response is None:
          final_score = -5.0
          self._update_moving_score(miner_uid, final_score)
          miner_statement = VericoreMinerStatementResponse(
             miner_hotkey=miner_hotkey,
		         miner_uid=miner_uid,
		         status="no_response",
		         raw_score=final_score
	        )
          return miner_statement

       # Process Vericore response data
       bt.logging.info(f'{request_id} | {miner_uid} | Verifying Miner Statements')

       vericore_statement_responses = await asyncio.gather(*[
	       asyncio.to_thread(
		       self.process_miner_response, request_id, miner_veridex_response, statement
	       ) for miner_veridex_response in miner_response.synapse.veridex_response
       ])

       bt.logging.info(f'{request_id} | {miner_uid} | Scoring Miner Statements')

       domain_counts = { }
       sum_of_snippets = 0.0

       # Check how many times the domain count was reused
       for statement_response in vericore_statement_responses:
          if statement_response.snippet_found:
             times_used = domain_counts.get(statement_response.domain, 0)
             domain_counts[statement_response.domain] = times_used + 1

       # Calculate the miner's statement score
       for statement_response in vericore_statement_responses:
          if statement_response.snippet_found:
             times_used = domain_counts.get(statement_response.domain, 0)
             domain_factor = 1.0 / (2 ** times_used)
             statement_response.snippet_score = statement_response.local_score * domain_factor

          sum_of_snippets += statement_response.snippet_score

       # Calculate final score considering speed factor
       speed_factor = max(0.0, 1.0 - (miner_response.elapse_time / 15.0))
       final_score = sum_of_snippets * speed_factor
       if is_test and is_nonsense and final_score > 0.5:
           final_score -= 1.0
       final_score = max(-3.0, min(3.0, final_score))
       self._update_moving_score(miner_uid, final_score)

       bt.logging.info(f'{request_id} | {miner_uid} | Calculated Final Scores')

       miner_statement = VericoreMinerStatementResponse(
	        miner_hotkey=miner_hotkey,
	        miner_uid=miner_uid,
	        status="ok",
	        speed_factor=speed_factor,
	        final_score=final_score,
	        vericore_responses=vericore_statement_responses
       )
       return miner_statement

    async def handle_query(self, request_id: str, statement: str, sources: list,
                           is_test: bool = False, is_nonsense: bool = False) -> VericoreQueryResponse:
        """
        1. Query a subset of miners with the given statement.
        2. Verify that each snippet is truly on the page.
        3. Score the responses (apply domain factor, speed factor, etc.) and update
           the local moving_scores.
        4. Write the complete result (including final scores) to a uniquely named JSON file.
        """
        subset_axons = self._select_miner_subset(k=5)
        bt.logging.info(f'{request_id} | subset_axons ')

        synapse = VericoreSynapse(statement=statement, sources=sources, request_id=request_id)
        responses = await asyncio.gather(*[
	        asyncio.create_task(
		        self.process_miner_request(
			        request_id,
			        axon,
			        synapse,
			        statement,
			        is_test,
			        is_nonsense
		        )
          )	for axon in subset_axons
        ])

        bt.logging.info(f'{request_id} | Processed Miner Request')

        response = VericoreQueryResponse(
          status = "ok",
          request_id = request_id,
          statement = statement,
          sources = sources,
          results = responses
        )
        # Write the result to a uniquely named file for the daemon.
        self.write_result_file(request_id, response)
        return response

    def write_result_file(self, request_id: str, result: VericoreQueryResponse):
        filename = os.path.join(self.results_dir, f"{request_id}.json")
        try:
            with open(filename, "w") as f:
                json.dump(asdict(result), f)
            bt.logging.info(f"Wrote result file: {filename}")
        except Exception as e:
            bt.logging.error(f"Error writing result file {filename}: {e}")

    def _update_moving_score(self, uid: int, new_raw_score: float):
        old_val = self.moving_scores[uid]
        self.moving_scores[uid] = 0.8 * old_val + 0.2 * new_raw_score

    def _select_miner_subset(self, k=5):
        all_axons = self.metagraph.axons
        bt.logging.info(f"Selecting miner subset:")
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

    # def _verify_snippet_in_rendered_page(self, url: str, snippet_text: str) -> bool:
    #   try:
    #       page_html = self.fetcher.fetch_entire_page(url)
    #       return snippet_text in page_html
    #   except Exception:
    #       return False

    def _fetch_page_text(self, url: str) -> str:
      try:
        fetcher = SnippetFetcher()
        page_html = fetcher.fetch_entire_page(url)

        soup = BeautifulSoup(page_html, 'html.parser')

        page_text = soup.getText(separator=" ", strip=True)

        return page_text

      except Exception:
        bt.logging.error("Fetch Page Text")
        # logging.error(f"Error verifying snippet in rendered page: {e}")
        return ''

    def _verify_snippet_in_rendered_page(self, request_id: str, page_text: str, snippet_text: str) -> bool:
      try:
        return self.verify_quality_model.verify_context(snippet_text, page_text)

        # tree = lxml.html.fromstring(page_html)
				#
        # # Perform fuzzy matching
        # matches = [elem for elem in tree.xpath("//*[not(self::script or self::style)]") if fuzz.ratio(snippet_text, elem.text_content().strip()) > 80]
        # if not matches:
        #   bt.logging.info(f"{request_id} | url: {url} | No matches found using fuzzy ratio")
        #   return False
				#
        # # Check whether the snippet does exist within the provided context
        # for match in matches:
        #   context = match.text_content().strip()
        #   if self.verify_quality_model.verify_context(snippet_text, context):
        #     bt.logging.info(f"{request_id} | url: {url} | FOUND snippet  within the page.")
        #     return True
				#
        # bt.logging.info(f"{request_id} | url: {url} | CANNOT FIND snippet within the page")
        # return False
      except Exception:
        bt.logging.error("Error verifying snippet")
        # logging.error(f"Error verifying snippet in rendered page: {e}")
        return False

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
    print('startup_event')
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
    handler = app.state.handler
    start_time = time.time()
    result = await handler.handle_query(request_id, statement, sources)
    end_time = time.time()
    print(f"{request_id} | Finished processing at {end_time} (Duration: {end_time - start_time})")
    return JSONResponse(asdict(result))

if __name__ == "__main__":
    import uvicorn

    # Run uvicorn with one worker to ensure a single instance of APIQueryHandler.
    uvicorn.run("validator.api_server:app", host="0.0.0.0", port=8080, reload=False, timeout_keep_alive=500)

