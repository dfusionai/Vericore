from shared.log_data import LoggerType, JSONFormatter
import logging
import requests
from dataclasses import asdict

def registerProxyLogHander(logger, proxy_url, logger_type: LoggerType, logger_reference: str):
	# Use the actual Bittensor logger
	logger.setLevel(logging.DEBUG)  # Capture all logs

	proxy_handler = ProxyLogHandler(proxy_url, logger_type, logger_reference)
	proxy_handler.setLevel(logging.DEBUG)  # Only send warnings and above
	proxy_handler.setFormatter(JSONFormatter())

	logger.addHandler(proxy_handler)


class ProxyLogHandler(logging.Handler):
	"""Custom log handler to send logs to a proxy server ."""

	def __init__(self, proxy_url, logger_type: LoggerType, logger_reference: str):
		super().__init__()
		self.proxy_url = proxy_url
		self.logger_type = logger_type
		self.logger_reference = logger_reference

	def emit(self, record):
		log_entry = self.format(record)
		print(f"ProxyLogHandler log (name={self.name}): {log_entry}")
	# try:
	#     headers = {
	#        "Content-Type": "application/json",
	#       "Logger-Type": self.logger_type,
	#       "Logger-Reference": self.logger_reference,
	#     }
	#     requests.post(self.proxy_url, json={"log": log_entry}, timeout=5, headers=headers)
	# except requests.exceptions.RequestException as e:
	#     print(f"Failed to send log to proxy: {e}")
