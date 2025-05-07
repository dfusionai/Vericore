import json
from dataclasses import asdict

import requests

import bittensor as bt

from shared.environment_variables import DASHBOARD_API_URL
from shared.validator_results_data import ValidatorResultsData
from shared.log_data import LoggerType


class ValidatorResultsDataHandler:

    def __init__(self, proxy_url: str, validator_uid: int, wallet: str):
        super().__init__()
        self.proxy_url = proxy_url + "/store_json_response"
        self.validator_uid = validator_uid
        self.wallet = wallet

    def send_json(self, results_data: ValidatorResultsData):
        try:
            results_data.validator_uid = self.validator_uid
            results_data.validator_hotkey = self.wallet.hotkey.ss58_address
            # add signature
            message = (
                f"{results_data.validator_uid}.{self.wallet.hotkey.ss58_address}.data"
            )
            encoded_message = message.encode("utf-8")
            signature = self.wallet.hotkey.sign(encoded_message).hex()

            headers = {
                "Content-Type": "application/json",
                "wallet": self.wallet.hotkey.ss58_address,
                "signature": signature,
                "type": LoggerType.Validator.value,
            }
            json_data = json.dumps(asdict(results_data))
            bt.logging.info(f"DAEMON | {self.validator_uid} |  Sending json response to {self.proxy_url}")
            requests.post(self.proxy_url, json=json_data, timeout=300, headers=headers)
            bt.logging.info(f"DAEMON | {self.validator_uid} | Sent to store response data")
        except requests.exceptions.RequestException as e:
            bt.logging.error(f"DAEMON | {self.validator_uid} | Failed to store json responses: {e}")


def register_validator_results_data_handler(
    validator_uid: int, wallet: str
) -> ValidatorResultsDataHandler:
    dashboard_api_url = DASHBOARD_API_URL

    bt.logging.info(f"Registered STORE JSON logging on url:  {dashboard_api_url}")

    # Use the actual Bittensor logger
    store_results_handler = ValidatorResultsDataHandler(
        dashboard_api_url, validator_uid, wallet
    )

    return store_results_handler
