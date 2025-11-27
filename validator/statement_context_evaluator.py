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

You are given the output of a Natural Language Inference (NLI) model to help you decide. The model is used as follows:
- The `excerpt` is the *premise*.
- The `statement` is the *hypothesis*.
- The model returns logits for 3 labels in this order: [contradiction, neutral, entailment].
- These logits are passed through a softmax layer to obtain probabilities:
  - "contradiction": the probability that the excerpt contradicts the statement.
  - "neutral": the probability that the excerpt neither supports nor contradicts the statement.
  - "entailment": the probability that the excerpt supports the statement.

        Use:
        - local_score = contradiction + entailment (do not subtract neutrality)
        to determine confidence in classification.

        In addition to the basic classification, evaluate the following signals:

        1. **Sentiment**: Assess the positive/negative sentiment of the excerpt regarding the statement. Values: -1.0 (strongly negative) to 1.0 (strongly positive), 0.0 (neutral).
        2. **Conviction**: Measure how certain and confident the excerpt is in its position. Values: 0.0 (uncertain/hedging) to 1.0 (high conviction/definitive).
        3. **Source Credibility**: Evaluate the credibility and authority of the source based on domain, author, publication, and content quality. Values: 0.0 (low credibility/questionable) to 1.0 (high credibility/authoritative).
        4. **Narrative Momentum**: Assess whether the excerpt contributes to building a compelling narrative or story around the statement. Values: 0.0 (static/no momentum) to 1.0 (high momentum/engaging narrative).
        5. **Risk-Reward Sentiment**: Evaluate the excerpt's perspective on potential risks vs rewards related to the statement. Values: -1.0 (risk-focused/cautionary) to 1.0 (reward-focused/optimistic), 0.0 (balanced).
        6. **Catalyst Detection**: Determine if the excerpt identifies or discusses catalysts, triggers, or key events that could cause change related to the statement. Values: 0.0 (no catalyst mentioned) to 1.0 (clear catalyst identified).

        Return the reason for your answer as well as the result: Return the reason for your score.
        {{ "reason": "", "snippet_status": "SUPPORT", "is_search_url": false, "score": {{ "contradiction": 0.0, "entailment": 0.0, "neutral": 0.0 }}, "sentiment": 0.0, "conviction": 0.0, "source_credibility": 0.0, "narrative_momentum": 0.0, "risk_reward_sentiment": 0.0, "catalyst_detection": 0.0 }}

- snippet_status: One of "SUPPORT", "CONTRADICT", or "UNRELATED", or "FAKE" .
- is_search_url: true if the URL is a search page and is similar to the statement; otherwise false.
Definitions:
- SUPPORT: The excerpt clearly agrees with or provides evidence for any part of the statement. Even if it does not cover the entire statement, if it confirms one or more factual components, classify as SUPPORT.
- CONTRADICT: The excerpt clearly disagrees with or disproves any part of the statement.
- UNRELATED: The excerpt does not mention or relate to any part of the statement at all.
- FAKE: The excerpt repeats the statement verbatim or nearly verbatim, but uses vague, evasive, or overly dramatic language that obscures meaning and does not engage meaningfully with the statement. Also if the statement excerpt and webpage is being repeated.

Signal Definitions:
- sentiment: Positive/negative emotional tone toward the statement. Positive values indicate favorable sentiment, negative values indicate unfavorable sentiment.
- conviction: Level of certainty and confidence expressed. High conviction shows definitive language, low conviction shows hedging, qualifiers, or uncertainty.
- source_credibility: Trustworthiness and authority of the source. Consider domain reputation, author credentials, publication quality, and content rigor.
- narrative_momentum: Ability to build an engaging story or narrative around the statement. High momentum creates interest and forward movement in the narrative.
- risk_reward_sentiment: Focus on risks (negative) vs rewards/opportunities (positive). Risk-focused content emphasizes dangers, costs, or downsides. Reward-focused content emphasizes benefits, opportunities, or upsides.
- catalyst_detection: Identification of triggers, events, or factors that could cause change or action related to the statement. Catalysts are specific, actionable events or conditions.

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
