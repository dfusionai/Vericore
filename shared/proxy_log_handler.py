from shared.log_data import LoggerType, JSONFormatter
import logging
import requests

def registerProxyLogHandler(logger, proxy_url, logger_type: LoggerType, wallet ):
    # Use the actual Bittensor logger
    logger.setLevel(logging.DEBUG)  # Capture all logs

    proxy_handler = ProxyLogHandler(proxy_url, logger_type, wallet)
    proxy_handler.setLevel(logging.DEBUG)  # Only send warnings and above
    proxy_handler.setFormatter(JSONFormatter())

    logger.addHandler(proxy_handler)


class ProxyLogHandler(logging.Handler):
    """Custom log handler to send logs to a proxy server ."""

    def __init__(self, proxy_url, logger_type: LoggerType, wallet):
        super().__init__()
        self.proxy_url = proxy_url + '/log'
        self.logger_type = logger_type
        self.wallet = wallet

    def emit(self, record):
        log_entry = self.format(record)
        try:
            #add signature
            message = f"{record.levelname}.{record.created}.{self.wallet.hotkey.ss58_address}.log"
            encoded_message = message.encode('utf-8')
            signature = self.wallet.hotkey.sign(encoded_message).hex()

            headers = {
                'Content-Type': 'application/json',
                'wallet': self.wallet.hotkey.ss58_address,
                'signature': signature,
            }
            requests.post(self.proxy_url, json=log_entry, timeout=5, headers=headers)
        except requests.exceptions.RequestException as e:
            #todo - not sure what to do here - can we miss a few logs
            # Not using bittensor logging here - otherwise we will go into a loop!
            print(f"Failed to send log to proxy: {e}")
