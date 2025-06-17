import asyncio
import httpx
import json
import bittensor as bt

from shared.environment_variables import AI_API_URL
import argparse

class AiChatHandler:
    def __init__(self):
        self.url = f"{AI_API_URL}/ai-chat"
        self.client = httpx.AsyncClient(timeout=30.0)  # create one client for reuse
        self.setup_bittensor_objects()

    def get_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--custom", default="my_custom_value", help="Custom value")
        parser.add_argument("--netuid", type=int, default=1, help="Chain subnet uid")
        bt.wallet.add_args(parser)
        return bt.config(parser)


    def setup_bittensor_objects(self):
        config = self.get_config()
        bt.logging.info("Setting up Bittensor objects for AI Chat.")
        self.wallet = bt.wallet(config=config)

    async def run(self, messages):
        try:
            bt.logging.info(f"Running AI chat for url: {self.url}")
            # #add signature
            message = f"{self.wallet.hotkey.ss58_address}.validator_chat_api"
            encoded_message = message.encode('utf-8')
            signature = self.wallet.hotkey.sign(encoded_message).hex()

            headers = {
                'Content-Type': 'application/json',
                'wallet': self.wallet.hotkey.ss58_address,
                'signature': signature
                # , 'type': self.logger_type,
            }

            response = await self.client.post(self.url, json=messages, headers=headers)
            response.raise_for_status()
            json_text = response.json()
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                bt.logging.debug("Failed to parse JSON:", json)
                return None

            # content_str = data["choices"][0]["message"]["content"]
            # # Remove ```json ``` if it is there
            # content_str = content_str.removeprefix("```json").removesuffix("```").strip()
            # # Parse the JSON string returned inside content
            # try:
            #     return json.loads(content_str)
            # except json.JSONDecodeError:
            #     print("Failed to parse JSON:", content_str)
            #     return None
        except httpx.HTTPError as e:
            print(f"HTTP error: {e}")
            return None

    async def close(self):
        await self.client.aclose()

# Global singleton
global_handler = AiChatHandler()

async def assess_statement_async(request_id: str, miner_uid: int, statement_url: str, statement: str, webpage: str, miner_excerpt: str):
    bt.logging.info(f"{request_id} | {miner_uid} | {statement_url} | Assessing statement")
    # update to be more positive - change to say what to expect.
    # check to see what web-page is being passed with beautifulsoup
    messages = [
        {"role": "system",
         "content": f"""You are a helpful assistant that checks whether the excerpt agrees or disagrees with the statement or the statement is unrelated.
        You need to also check whether the excerpt might be fake. The excerpt repeats the statement verbatim or nearly verbatim, but uses vague, evasive, or overly dramatic language that obscures meaning and does not engage meaningfully with the statement
        Additionally, check if the URL looks like a search results page (for example, if it contains 'search', 'q=', or comes from a search engine domain) and if the search query or URL content is similar to the statement or excerpt content.

        Return the reason for your answer as well as the result:
        {{ "reason:"", "snippet_status": "SUPPORT", "is_search_url": false  }}

- snippet_status: One of "SUPPORT", "CONTRADICT", or "UNRELATED", or "FAKE" .
- is_search_url: true if the URL is a search page and is similar to the statement; otherwise false.
Definitions:
- SUPPORT: The excerpt clearly agrees with or provides evidence for the statement.
- CONTRADICT: The excerpt clearly disagrees with or disproves the statement.
- UNRELATED: The excerpt does not mention or relate to the subject of the statement at all.
- FAKE: The excerpt repeats the statement verbatim or nearly verbatim, but uses vague, evasive, or overly dramatic language that obscures meaning and does not engage meaningfully with the statement. Also if the statement excerpt and webpage is being repeated.

Do not include explanations. Only return the JSON object.
"""

                                      },
        {"role": "user", "content": f"""
        Webpage Excerpt: {webpage[:1500]}
        Statement: {statement}
        Excerpt:{miner_excerpt}
        Url: {statement_url}
        """},
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
    # request_id: str, miner_uid: int, statement_url: str, statement: str, webpage: str, miner_excerpt: str
    # temp_list.append(SourceEvidence(
    #     url="https://www.sciencealert.com/search/Thehumanbodyhasmorebacteriacellsthan%20humancellswithestimatessuggestingaratioof%20about10to1highlightingthecomplexrelationshipbetweenhumansandtheirmicrobiomeisawellknownfact",
    #     excerpt="Thehumanbodyhasmorebacteriacellsthan humancellswithestimatessuggestingaratioof about10to1highlightingthecomplexrelationshipbetweenhumansandtheirmicrobiomeisawellknownfact"))
    #
    # temp_list.append(SourceEvidence(
    #     url="https://www.sciencealert.com/search/Without-a-doubt-A-group-of-hedgehogs-is-known-as-an-array-reflecting-their-unique-social-gatherings-and-their-intriguing-adaptations-in-the-wild",
    #     excerpt="Without-a-doubt-A-group-of-hedgehogs-is-known-as-an-array-reflecting-their-unique-social-gatherings-and-their-intriguing-adaptations-in-the-wild"))

    batch = [
        (
            "req1",
            1,
            "https://www.sciencealert.com/search/Thehumanbodyhasmorebacteriacellsthan%20humancellswithestimatessuggestingaratioof%20about10to1highlightingthecomplexrelationshipbetweenhumansandtheirmicrobiomeisawellknownfact",
            "A group of hedgehogs is known as an \"array,\" reflecting their unique social gatherings and their intriguing adaptations in the wild",
            "",
            "Thehumanbodyhasmorebacteriacellsthan humancellswithestimatessuggestingaratioof about10to1highlightingthecomplexrelationshipbetweenhumansandtheirmicrobiomeisawellknownfact"
        ),
        # ("req2", 2, "url2", "Does Bitcoin use proof-of-stake?", "Bitcoin uses proof-of-work ..."),
    ]
    results = asyncio.run(assess_multiple_statements_async(batch))
    for res in results:
        print(res)
