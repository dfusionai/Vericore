import queue
import argparse
import json
import re
import time
import asyncio
import torch
import bittensor as bt
import os
from concurrent.futures import ThreadPoolExecutor
from transformers import AutoTokenizer, AutoModelForCausalLM


# Configurable constants
NO_THREADS_IN_POOL = min(8, os.cpu_count() or 4)
MODEL_ID = "microsoft/phi-4-mini-instruct"

bt.logging.info("Initializing LLM")

TOKENIZER  = AutoTokenizer.from_pretrained(MODEL_ID)
MODEL = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,  # fp16 will fit more easily on a single V100 (32 GB)
    device_map="auto",  # accelerate will place everything on cuda:0
    low_cpu_mem_usage=True,  # cut down peak CPU RAM requirements
    # torch_dtype="auto",
    # # torch_dtype=torch.float32,
    # device_map={ "": "cpu" }
)

bt.logging.info("Initialized LLM. Model Loaded")

class SnippetContextEvaluator:

    def __init__(self):
        # self.model_id = "microsoft/phi-4-mini-reasoning"
        self.tokenizer = TOKENIZER
        self.model = MODEL

    def get_embeddings(self, text):
        return self.model.encode(text, convert_to_tensor=True)

    def safe_extract_json(text: str):
        try:
            json_str = text[text.index('{'): text.index('}') + 1]
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError):
            return None

    def extract_llm_response(self, text: str) -> dict | None:
        """
        Extracts the response and relative_percentage JSON from a block that starts with 'Answer:'.
        Returns a dictionary like: {"response": "UNRELATED", "relative_percentage": 0}
        Returns None if no valid JSON block is found.
        """
        try:
            # Start from the 'Answer:' block only
            answer_section = text.split("Answer:")[-1]

            # Match JSON format after 'Answer:'
            match = re.search(
                r'\{\s*"response"\s*:\s*"(SUPPORT|CONTRADICT|UNRELATED)"\s*,\s*"score_pair_distrib"\s*:\s*\{\s*"contradiction"\s*:\s*[\d.]+\s*,\s*"neutral"\s*:\s*[\d.]+\s*,\s*"entailment"\s*:\s*[\d.]+\s*\}\s*\}',
                answer_section,
                re.IGNORECASE | re.DOTALL
            )
            if match:
                json_str = match.group(0)
                return json.loads(json_str)
            else:
                return None
        except Exception as e:
            print(f"Error extracting LLM response: {e}")
            return None

    def truncate_text(self, text: str, max_chars: int = 1500):
        return text if len(text) <= max_chars else text[:max_chars] + "..."

    def assess_statement_context(
        self,
        request_id: str,
        miner_uid: int,
        statement_url: str,
        statement: str,
        webpage: str
    ):
        bt.logging.info(f"{ request_id} | {miner_uid} | {statement_url} | using llm to check webpage supports or contradicts statements")

        prompt =  f"""You are a helpful assistant that returns a JSON object only.

Only respond with a valid JSON object in this exact format:
{{"response": "SUPPORT", "score_pair_distrib": {{ "contradiction": 0.04,   "neutral": 0.10,   "entailment": 0.86  }} }}
- response: One of "SUPPORT", "CONTRADICT", or "UNRELATED".
- score_pair_distrib: Three floats between 0 and 1 that sum to 1. Compute the probability distribution over [contradiction, neutral, entailment]:
  - contradiction: the likelihood that the statement contradicts the webpage.
  - neutral: the likelihood that the statement is neither supported nor contradicted.
  - entailment: the likelihood that the statement is supported or entailed by the webpage.

Definitions:
- SUPPORT: The webpage clearly agrees with or provides evidence for the statement.
- CONTRADICT: The webpage clearly disagrees with or disproves the statement.
- UNRELATED: The webpage does not mention or relate to the subject of the statement at all.

Do not include explanations. Only return the JSON object.

        Webpage:
        \"{self.truncate_text(webpage)}\"

        Statement:
        \"{statement}\"

        Answer:
        """
        # tokenizer = AutoTokenizer.from_pretrained(model_id)
        # model = AutoModelForCausalLM.from_pretrained(model_id)

        inputs = self.tokenizer(prompt, return_tensors="pt")

        device = next(self.model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        start_time = time.perf_counter()

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=200,
            do_sample=False,
            eos_token_id=self.tokenizer.eos_token_id,
        )

        response = self.tokenizer.decode(outputs[0].cpu(), skip_special_tokens=True).strip()

        end_time = time.perf_counter()

        bt.logging.info(f"{ request_id} | {miner_uid} | {statement_url} | processed llm response: {end_time - start_time: .2f} seconds")

        # Extract just the model's reply
        return self.extract_llm_response(response)


class SnippetContextEvaluatorPool:
    def __init__(self, size=5):
        self.pool = queue.Queue(maxsize=size)  # Create a thread-safe queue
        for _ in range(size):
            self.pool.put(SnippetContextEvaluator())  # Fill the pool with instances of SimilarityHandler

    def get_handler(self):
        return self.pool.get()  # Get a handler from the pool (blocking if none available)

    def return_handler(self, handler):
        self.pool.put(handler)  # Return the handler to the pool

pool = SnippetContextEvaluatorPool(NO_THREADS_IN_POOL)
executor = ThreadPoolExecutor(max_workers=NO_THREADS_IN_POOL)

def assess_statement_context(
    request_id: str,
    miner_uid: int,
    statement_url: str,
    statement: str,
    webpage: str
):
    handler = pool.get_handler()
    try:
        return handler.assess_statement_context(
            request_id,
            miner_uid,
            statement_url,
            statement,
            webpage
        )
    finally:
        pool.return_handler(handler)

async def assess_statement_context_async(
    request_id: str,
    miner_uid: int,
    statement_url: str,
    statement: str,
    webpage: str
):
    loop = asyncio.get_running_loop()
    # Run blocking assess_statement_context in executor, await result asynchronously
    result = await loop.run_in_executor(
        executor,
        assess_statement_context,
        request_id,
        miner_uid,
        statement_url,
        statement,
        webpage
    )
    return result

def main(
    request_id: str,
    miner_uid: int,
    statement_url: str,
    statement:str,
    webpage: str,
    excerpt: str
):
    result = assess_statement_context(request_id, miner_uid, statement_url, statement, webpage)
    print(f"RESULT = {result}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Snippet Context Model.")
    parser.add_argument("--statement", type=str, default="""What is Ethereum (ETH) & How Does it Work? Sign In | Help Center Trading Trading Products Stocks Options Futures Crypto Futures Options ETFs Platforms & Tools Trading Platforms Mobile Desktop Web API Accounts Account
Types Pricing Resources Learn Demos & Events About Us tastytrade Courses Open an Account Beginner What is Ethereum (ETH) and How Does it Work? What is Ethereum (ETH)? Ethereum is the blockchain that is home to the native cryptoc
urrency ether (ETH). The Ethereum blockchain is also where smart contracts are developed. Smart contracts enable peer-to-peer transactions without a central authority and are essentially codes that execute automatically when spe
cific criteria are met. This is how Ethereum is seen as more of an application blockchain, hosting technology like non-fungible tokens (NFTs) that grew in popularity a few years ago. Ethereum is the second largest blockchain in
terms of market cap, only behind Bitcoin. How Does Ethereum work? Ethereum is a decentralized blockchain and platform in which developers can create smart contracts for practical applications. With a proof-of-stake (PoS) transac
tion verification process, Ethereum is known to be a much more efficient energy consumer relative to Bitcoin , and network participants are rewarded with the native cryptocurrency ether (ETH). Ethereum Smart Contracts Explained
A smart contract is a program that runs on the Ethereum blockchain. This program’s code and data are stored on the blockchain at an address, and interactions with the smart contract are irreversible. Some describe a smart contra
ct as a digital vending machine in which the correct inputs guarantee a certain output. Smart contracts are permissionless, which means anyone can write a smart contract and run it on the Ethereum network. Smart contracts furthe
r exemplify how Ethereum gets its “software” comparison. """, help="Dinosaur existed")
    parser.add_argument("--snippet", type=str, default="All mammals have wings")
    args = parser.parse_args()
    main("req-", 1, "google.co.za", args.statement, args.snippet, "")
