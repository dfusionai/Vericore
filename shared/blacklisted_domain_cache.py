import bittensor as bt
import requests
from shared.environment_variables import DASHBOARD_API_URL

class BlacklistedDomainCache:
    def __init__(self):
        dashboard_api_url = DASHBOARD_API_URL
        self.url = f"{dashboard_api_url}/blacklisted-domains"
        self.cache = self.fetch_blacklisted_domains()


    def fetch_blacklisted_domains(self) :
        try:
            bt.logging.info(f"VALIDATOR | Fetching blacklisted domains from {self.url}")
            response = requests.get(self.url, timeout=300)
            bt.logging.info(f"VALIDATOR | blacklisted_domains_cache fetched")
            return {record["domain"] for record in response.json()}
        except requests.exceptions.RequestException as e:
            bt.logging.error(f"VALIDATOR | Failed to fetch blacklisted domains: {e}")

    def get_cache(self):
        return self.cache


blacklisted_domain_cache = BlacklistedDomainCache()

def get_blacklisted_domain_cache_data():
    if blacklisted_domain_cache.cache is None:
        blacklisted_domain_cache.cache = blacklisted_domain_cache.fetch_blacklisted_domains()

    return blacklisted_domain_cache.cache


def is_blacklisted_domain(request_id: str, miner_uid: int, domain: str):
    bt.logging.info(f"{request_id} | {miner_uid} | Validating domain {domain}")
    cache_data = get_blacklisted_domain_cache_data()

    blacklisted_domain = domain in cache_data

    bt.logging.info(f"{request_id} | {miner_uid} | {domain} is blacklisted : {blacklisted_domain} ")

    return blacklisted_domain
