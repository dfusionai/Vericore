import bittensor as bt
import requests
import time
from shared.environment_variables import DASHBOARD_API_URL

REFRESH_BLACKLISTED_DOMAIN_TIMEOUT = 60 * 60 # one hour

class BlacklistedDomainCache:
    def __init__(self):
        dashboard_api_url = DASHBOARD_API_URL
        self.url = f"{dashboard_api_url}/blacklisted-domains"
        self.cache = self.fetch_blacklisted_domains()
        self.time_refreshed = None


    def fetch_blacklisted_domains(self) :
        try:
            bt.logging.info(f"VALIDATOR | Fetching blacklisted domains from {self.url}")
            response = requests.get(self.url, timeout=300)
            bt.logging.info(f"VALIDATOR | blacklisted_domains_cache fetched")
            # set time refreshed
            self.time_refreshed = time.time()
            return {record["domain"] for record in response.json()}
        except requests.exceptions.RequestException as e:
            bt.logging.error(f"VALIDATOR | Failed to fetch blacklisted domains: {e}")

    def get_cache(self):
        return self.cache

    def requires_refresh(self) -> bool:
        if blacklisted_domain_cache.cache is None:
            return True

        return self.time_refreshed is None or self.time_refreshed + REFRESH_BLACKLISTED_DOMAIN_TIMEOUT > time.time()

blacklisted_domain_cache = BlacklistedDomainCache()

def get_blacklisted_domain_cache_data():
    if blacklisted_domain_cache.requires_refresh():
        bt.logging.info("Refreshing blacklisted domains cache")
        blacklisted_domain_cache.cache = blacklisted_domain_cache.fetch_blacklisted_domains()


    return blacklisted_domain_cache.cache


def is_blacklisted_domain(request_id: str, miner_uid: int, domain: str):
    bt.logging.info(f"{request_id} | {miner_uid} | Validating domain {domain}")
    cache_data = get_blacklisted_domain_cache_data()

    blacklisted_domain = domain in cache_data

    bt.logging.info(f"{request_id} | {miner_uid} | {domain} is blacklisted : {blacklisted_domain} ")

    return blacklisted_domain
