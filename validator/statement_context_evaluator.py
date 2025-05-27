import asyncio
import httpx
import json
import bittensor as bt

from shared.environment_variables import VLLM_API_URL


class VLLMChatHandler:
    def __init__(self):
        self.url = f"{VLLM_API_URL}/v1/chat/completions"
        self.client = httpx.AsyncClient(timeout=30.0)  # create one client for reuse

    async def run(self, messages):
        payload = {
            "model": "microsoft/phi-4-mini-instruct",
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 300,
        }
        try:
            response = await self.client.post(self.url, json=payload)
            response.raise_for_status()
            data = response.json()
            content_str = data["choices"][0]["message"]["content"]
            # Remove ```json ``` if it is there
            content_str = content_str.removeprefix("```json").removesuffix("```").strip()
            # Parse the JSON string returned inside content
            try:
                return json.loads(content_str)
            except json.JSONDecodeError:
                print("Failed to parse JSON:", content_str)
                return None
        except httpx.HTTPError as e:
            print(f"HTTP error: {e}")
            return None

    async def close(self):
        await self.client.aclose()

# Global singleton
global_handler = VLLMChatHandler()

async def assess_statement_async(request_id, miner_uid, statement_url, statement, webpage):
    bt.logging.info(f"{request_id} | {miner_uid} | {statement_url} | Assessing statement")

    messages = [
        {"role": "system", "content": f"""You are a helpful assistant that returns a JSON object only.
        Return only a single line of valid JSON with this exact structure and no explanation or formatting:
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
"""
                                      },
        {"role": "user", "content": f"Webpage:\n\"{webpage[:1500]}\"\n\nStatement:\n\"{statement}\"\n\n"},
    ]
    return await global_handler.run(messages)


async def assess_multiple_statements_async(statements):
    # statements is a list of tuples: (request_id, miner_uid, statement_url, statement, webpage)
    tasks = [
        assess_statement_async(*args)
        for args in statements
    ]
    results = await asyncio.gather(*tasks)
    return results

# Example usage
if __name__ == "__main__":
    batch = [
        ("req1", 1, "url1", "Is Ethereum decentralized?", "Ethereum is a decentralized blockchain ..."),
        ("req2", 2, "url2", "Does Bitcoin use proof-of-stake?", "Bitcoin uses proof-of-work ..."),
    ]
    results = asyncio.run(assess_multiple_statements_async(batch))
    for res in results:
        print(res)
