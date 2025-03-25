import json
import requests
import os
import bittensor as bt

from shared.veridex_protocol import VericoreQueryResponse


def register_store_response(wallet):
    enable_logging = os.environ.get("ENABLE_STORE_JSON", "true").lower() == "true"

    bt.logging.info(f"Storing Response enabled:  {enable_logging}")

    if not enable_logging:
        return None

    proxy_url = os.environ.get("LOGGER_API_URL", 'http://localhost:8086')

    bt.logging.info(f"Registered STORE JSON logging on url:  {proxy_url}")

    # Use the actual Bittensor logger
    store_response_handler = StoreJsonResponseHandler(proxy_url, wallet)
    return store_response_handler

class StoreJsonResponseHandler():

    def __init__(self, proxy_url, wallet):
        super().__init__()
        self.proxy_url = proxy_url + '/store_json_response'
        self.wallet = wallet

    def send_json(self, json_data: dict ):

        response = VericoreQueryResponse(**json_data)
        try:
            #add signature
            message = f"{response.request_id}.{self.wallet.hotkey.ss58_address}.data"
            encoded_message = message.encode('utf-8')
            signature = self.wallet.hotkey.sign(encoded_message).hex()

            headers = {
                'Content-Type': 'application/json',
                'wallet': self.wallet.hotkey.ss58_address,
                'signature': signature,
            }
            print(f'Sending json response to {self.proxy_url}')
            requests.post(self.proxy_url, json= json_data, timeout=5, headers=headers)
            print(f'Storing json response: {json_data}')
        except requests.exceptions.RequestException as e:
            #todo - not sure what to do here - can we miss a few logs
            # Not using bittensor logging here - otherwise we will go into a loop!
            print(f"Failed to store json responses: {e}")
