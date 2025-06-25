import asyncio
import bittensor as bt

from shared.environment_variables import USE_AI_API

from validator.open_ai_client_handler import OpenAiClientHandler
from validator.open_ai_proxy_server_handler import OpenAiProxyServerHandler


class AiChatHandler:
    def __init__(self):
        if USE_AI_API:
            self.client = OpenAiProxyServerHandler()
        else:
            self.client = OpenAiClientHandler()

    async def run(self, messages):
        return await self.client.send_ai_request(messages)

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
