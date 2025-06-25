import httpx
import json
import bittensor as bt

from shared.environment_variables import AI_API_URL
import argparse

class OpenAiProxyServerHandler:
    def __init__(self):
        self.url = f"{AI_API_URL}/ai-chat"
        self.client = httpx.AsyncClient(timeout=30.0)  # create one client for reuse
        self.setup_bittensor_objects()

    async def close(self):
        bt.logging.info("Closing AI Chat client.")
        await self.client.aclose()

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

    async def send_ai_request(self, messages):
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

        except httpx.HTTPError as e:
            print(f"HTTP error: {e}")
            return None

