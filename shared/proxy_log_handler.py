import atexit
import threading
import logging
import requests
import os
import json
import bittensor as bt
from shared.log_data import LoggerType, JSONFormatter

MAX_LOG_SIZE = 500

proxy_handler = None

def register_proxy_log_handler(logger, logger_type: LoggerType, wallet):
    enable_logging = os.environ.get("ENABLE_PROXY_LOGGING", "true").lower() == "true"

    bt.logging.info(f"Logging enabled:  {enable_logging}")

    if not enable_logging:
        return

    proxy_url = os.environ.get("LOGGER_API_URL", 'https://api.logger.vericore.dfusion.ai')

    bt.logging.info(f"Registered proxy logging on url:  {proxy_url}")

    # Use the actual Bittensor logger
    logger.setLevel(logging.DEBUG)  # Capture all logs
    proxy_handler = ProxyLogHandler(proxy_url, logger_type, wallet)
    proxy_handler.setLevel(logging.DEBUG)  # Only send warnings and above
    proxy_handler.setFormatter(JSONFormatter())
    logger.addHandler(proxy_handler)

    atexit.register(proxy_handler.cleanup)



class ProxyLogHandler(logging.Handler):
    """Custom log handler to send logs to a proxy server ."""

    def __init__(self, proxy_url, logger_type: LoggerType, wallet):
        super().__init__()
        self.proxy_url = proxy_url + '/log'
        self.logger_type = logger_type
        self.wallet = wallet
        self.logging_cache = []
        self.cache_lock = threading.Lock()


    def send_log(self, log_entries: []):
        try:
            #add signature
            message = f"{self.wallet.hotkey.ss58_address}.{len(log_entries)}.logger"
            encoded_message = message.encode('utf-8')
            signature = self.wallet.hotkey.sign(encoded_message).hex()

            headers = {
                'Content-Type': 'application/json',
                'wallet': self.wallet.hotkey.ss58_address,
                'signature': signature
                # , 'type': self.logger_type,
            }
            requests.post(self.proxy_url, json=json.dumps(log_entries), timeout=5, headers=headers)
        except requests.exceptions.RequestException as e:
            #todo - not sure what to do here - can we miss a few logs
            # Not using bittensor logging here - otherwise we will go into a loop!
            print(f"Failed to send log to proxy: {e}")

    def add_log_entry_to_cache(self, log_entry):
        with self.cache_lock:
            self.logging_cache.append(log_entry)
            if len(self.logging_cache) > MAX_LOG_SIZE:
                self.send_log(self.logging_cache)
                self.logging_cache = []

    def emit(self, json_data):
        log_entry = self.format(json_data)
        self.add_log_entry_to_cache(log_entry)

    def cleanup(self):
        print("Cleaning up log")
        with self.cache_lock:
            self.send_log(self.logging_cache)
            self.logging_cache = []

