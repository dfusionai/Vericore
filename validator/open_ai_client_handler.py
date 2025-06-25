import os
import ast
import json
from openai import AsyncAzureOpenAI
import bittensor as bt
from dotenv import load_dotenv

# debug
load_dotenv()

OPEN_AI_ENDPOINT= os.getenv("OPEN_AI_ENDPOINT", "TO_BE_UPDATED_OPEN_AI_ENDPOINT")
OPEN_AI_API_VERSION= os.getenv("OPEN_AI_API_VERSION", "TO_BE_UPDATED_OPEN_AI_API_VERSION")
OPEN_AI_API_KEY= os.getenv("OPENAI_AI_API_KEY", "TO_BE_UPDATED_OPENAI_AI_API_KEY")

###############################################################################
# Configure your Azure OpenAI credentials here (or via environment variables):
###############################################################################

# The name of your Azure OpenAI deployment
AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-4o-mini"

###############################################################################

class OpenAiClientHandler:

    def __init__(self):
        self.client = AsyncAzureOpenAI(
            azure_endpoint=OPEN_AI_ENDPOINT,
            api_version=OPEN_AI_API_VERSION,
            api_key=OPEN_AI_API_KEY
        )

    async def send_ai_request(self, messages) :
        try:
            bt.logging.info(f"Calling Open AI directly")

            response = await self.client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.0,
                max_tokens=1000
            )

            ai_chat_text = response.choices[0].message.content.strip()

            bt.logging.info(f"Received response from Open AI")

            try:
                return json.loads(ai_chat_text)
            except json.JSONDecodeError:
                bt.logging.debug("Failed to parse JSON:", json)
                return None

        except Exception as e:
            try:
                error_str = str(e)
                if "Error code: 400 - " in error_str:
                    # Split and parse the embedded dictionary
                    _, dict_like = error_str.split(" - ", 1)
                    error_dict = ast.literal_eval(dict_like.strip())

                    error = error_dict.get("error", {})
                    if error.get("code") == "content_filter":
                        filter_result = error.get("innererror", {}).get("content_filter_result", {})

                        # Check all filter categories for 'filtered: True'
                        for category, result in filter_result.items():
                            if result.get("filtered", False):
                                bt.logging.warning(f"Filtered by Azure: Policy violation in category '{category}'")
                                return json.dumps({
                                    "reason": f"Prompt was filtered due to policy violation in category '{category}'.",
                                    "snippet_status": "FAKE",
                                    "is_search_url": False
                                })
                else:
                    # Fallback: generic failure message
                    return json.dumps({
                        "reason": f"Error: {error_str}.",
                        "snippet_status": "ERROR",
                        "is_search_url": False
                    })

            except Exception as parse_error:
                bt.logging.warning(f"Failed to parse error content: {parse_error}")

                # Fallback: generic failure message
                return json.dumps({
                    "reason": f"Error Parsing Json: {e}.",
                    "snippet_status": "ERROR",
                    "is_search_url": False
                })
