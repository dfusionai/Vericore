import os
import time
import argparse
import traceback
import bittensor as bt
from typing import Tuple, List
import json

from veridex_protocol import VeridexSynapse, SourceEvidence

# Suppose you installed "perplexity-openai" or an equivalent package:
#   pip install perplexity-openai
# or you have the "openai" style client from perplexity
from openai import OpenAI

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from lxml import html

class Miner:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()

        # Load your Perplexity AI key from config or environment
        self.perplexity_api_key = os.environ.get("PERPLEXITY_API_KEY", "YOUR_API_KEY_HERE")
        if not self.perplexity_api_key or self.perplexity_api_key.startswith("YOUR_API_KEY_HERE"):
            bt.logging.warning("No PERPLEXITY_API_KEY found in environment. Please set it to use Perplexity.")
        
        # Initialize the "openai"-like client for Perplexity
        # base_url="https://api.perplexity.ai" as per your instructions
        self.perplexity_client = OpenAI(
            api_key=self.perplexity_api_key,
            base_url="https://api.perplexity.ai"
        )

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
        bt.logging.info(
            f"Running miner for subnet: {self.config.netuid} on network: {self.config.subtensor.network} with config:"
        )
        bt.logging.info(self.config)

    def setup_bittensor_objects(self):
        bt.logging.info("Setting up Bittensor objects.")
        self.wallet = bt.wallet(config=self.config)
        bt.logging.info(f"Wallet: {self.wallet}")

        self.subtensor = bt.subtensor(config=self.config)
        bt.logging.info(f"Subtensor: {self.subtensor}")

        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        bt.logging.info(f"Metagraph: {self.metagraph}")

        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error(
                f"\nYour miner: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            self.my_subnet_uid = self.metagraph.hotkeys.index(
                self.wallet.hotkey.ss58_address
            )
            bt.logging.info(f"Running miner on uid: {self.my_subnet_uid}")

    def blacklist_fn(self, synapse: VeridexSynapse) -> Tuple[bool, str]:
        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            bt.logging.trace(
                f"Blacklisting unrecognized hotkey {synapse.dendrite.hotkey}"
            )
            return True, None
        bt.logging.trace(
            f"Not blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )
        return False, None

    def veridex_forward(self, synapse: VeridexSynapse) -> VeridexSynapse:
        """
        1) Query Perplexity AI with your exact system+user messages format.
        2) Parse the JSON from the response (a string with "url", "snippet").
        3) For each snippet, fetch the snippet in the DOM and build SourceEvidence.
        """
        statement = synapse.statement
        # 1) Call Perplexity
        perplexity_results = self.call_perplexity_ai(statement)
        if not perplexity_results:
            # fallback in case of error or empty result
            synapse.veridex_response = []
            return synapse

        # 2) For each snippet, attempt to fetch + locate snippet
        final_responses = []
        for item in perplexity_results:
            url = item.get("url", "").strip()
            snippet_text = item.get("snippet", "").strip()
            if not url or not snippet_text:
                continue
            try:
                xpath, start_char, end_char = self.fetch_xpath_offset(url, snippet_text)
                se = SourceEvidence(
                    url=url,
                    xpath=xpath,
                    start_char=start_char,
                    end_char=end_char,
                    excerpt=snippet_text
                )
                final_responses.append(se)
            except Exception as e:
                bt.logging.warn(f"Could not fetch snippet from {url}: {e}")
                continue

        synapse.veridex_response = final_responses
        return synapse

    def call_perplexity_ai(self, statement: str) -> List[dict]:
        """
        Use the exact 'messages' structure with system + user roles.
        Model = 'sonar-pro'
        Then parse the text of the completion as JSON.
        Return a list of {url, snippet} dicts or empty on error.
        """
        system_content = """
You are a helpful AI assistant that fact checks statements.

Rules:
1. Provide only a list of final URLs and the snippets in json form [{\"url\": <source url>, \"snippet\": <snippet that directly agrees with or contradicts statement>}]. It is important that you do not include any explanation on the steps below.
2. Do not show the intermediate steps information.

Steps:
1. Find sources / text segments that either contradict or agree with the user provided statement.
2. Pick and extract the segments that most strongly agree or contradict the statement.
3. Do not return urls or segments that do not directly support or disagree with the statement. (no intermediate definitions even if used to pull your statement)
4. Do not change any text in the segments, but do shorten the segment to get only the part that directly agrees or disagrees with the statement. (Don't need the surrounding paragraph)
5. Create the json object for each source and statement and collect them into a list.
"""
        user_content = (
            f"Return snippets that strongly agree with or reject the following statement:\n{statement}"
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        try:
            # chat completion call
            response = self.perplexity_client.chat.completions.create(
                model="sonar-pro",
                messages=messages,
                stream=False  # We do not want streaming
            )

            # 'response' is typically an object with .choices, etc.
            # We'll assume the final text is in response.choices[0].message.content
            if not hasattr(response, "choices") or len(response.choices) == 0:
                bt.logging.warn(f"Perplexity returned no choices: {response}")
                return []
            raw_text = response.choices[0].message.content.strip()

            # The raw_text should be a JSON array as we requested
            # Attempt to parse
            data = json.loads(raw_text)
            if not isinstance(data, list):
                bt.logging.warn(f"Perplexity response is not a list: {data}")
                return []
            return data
        except Exception as e:
            bt.logging.error(f"Error calling Perplexity AI: {e}")
            return []

    def fetch_xpath_offset(self, url: str, snippet_text: str):
        """
        Launch headless Chrome, get page content, find snippet_text in DOM text nodes,
        return (xpath, start_char, end_char).
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        html_content = driver.page_source
        driver.quit()

        tree = html.fromstring(html_content)
        text_nodes = tree.xpath("//text()")

        for node in text_nodes:
            full_text = node
            if not isinstance(full_text, str):
                continue
            full_text_str = full_text.strip()
            if not full_text_str:
                continue

            idx = full_text_str.find(snippet_text)
            if idx != -1:
                element = node.getparent()  # The parent element
                xpath = tree.getpath(element)
                start_char = idx
                end_char = idx + len(snippet_text)
                return xpath, start_char, end_char

        raise ValueError("Snippet not found in DOM")

    def setup_axon(self):
        self.axon = bt.axon(wallet=self.wallet, config=self.config)
        bt.logging.info("Attaching forward function to axon.")
        self.axon.attach(
            forward_fn=self.veridex_forward,
            blacklist_fn=self.blacklist_fn,
        )
        bt.logging.info(
            f"Serving axon on network: {self.config.subtensor.network} with netuid: {self.config.netuid}"
        )
        self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
        bt.logging.info(f"Axon: {self.axon}")

        bt.logging.info(f"Starting axon server on port: {self.config.axon.port}")
        self.axon.start()

    def run(self):
        self.setup_axon()
        bt.logging.info("Starting main loop")
        step = 0
        while True:
            try:
                # periodically update metagraph
                if step % 60 == 0:
                    self.metagraph.sync()
                    log = (
                        f"Block: {self.metagraph.block.item()} | "
                        f"Incentive: {self.metagraph.I[self.my_subnet_uid]} | "
                    )
                    bt.logging.info(log)
                step += 1
                time.sleep(1)

            except KeyboardInterrupt:
                self.axon.stop()
                bt.logging.success("Miner killed by keyboard interrupt.")
                break
            except Exception as e:
                bt.logging.error(traceback.format_exc())
                continue

if __name__ == "__main__":
    miner = Miner()
    miner.run()
