import queue
import argparse
import json
import re
import bittensor as bt
from transformers import AutoTokenizer, AutoModelForCausalLM

NO_THREADS_IN_POOL = 2

class SnippetContextEvaluator:

    def __init__(self):
        # self.model_id = "microsoft/phi-4-mini-reasoning"
        self.model_id = "microsoft/phi-4-mini-instruct"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            torch_dtype="auto",
            # torch_dtype=torch.float32,
            device_map={ "": "cpu" }
        )
        # self.tokenizer = AutoTokenizer.from_pretrained("roberta-large-mnli")

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
                r'\{\s*"response"\s*:\s*"(SUPPORT|CONTRADICT|UNRELATED)"\s*,\s*"relative_percentage"\s*:\s*\d+\s*\}',
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

    def truncate_text(self, text: str, max_chars: int = 3000):
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

        prompt =  f"""
        You are a helpful assistant that returns a JSON object.

        Only respond with a valid JSON object in this format:
        {{"response": "SUPPORT",  "relative_percentage": 92}}  # response is "SUPPORT" or "CONTRADICT" or "UNRELATED"
        # relative_percentage is a percentage from 0 to 100 to say how related the webpage is related to the statement. If unrelated its 0

        Webpage:
        \"\"\"{self.truncate_text(webpage)}\"\"\"

        Statement:
        \"{statement}\"

        Answer:
        """
        # tokenizer = AutoTokenizer.from_pretrained(model_id)
        # model = AutoModelForCausalLM.from_pretrained(model_id)

        inputs = self.tokenizer(prompt, return_tensors="pt")
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=False
        )

        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        bt.logging.info(f"{ request_id} | {miner_uid} | {statement_url} | Run LLM | {response} ")
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
    parser.add_argument("--statement", type=str, default="The lifespan of a typical housefly is about 15 to 30 days, depending on environmental conditions, illustrating the brevity of life for many insects.", help="Dinosaur existed")
    parser.add_argument("--snippet", type=str, default="Ethereum is a decentralized blockchain")
    args = parser.parse_args()
    main("req-", 1, "google.co.za", args.statement, args.snippet, "")
