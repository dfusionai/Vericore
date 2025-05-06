import bittensor as bt
import requests
from shared.environment_variables import DASHBOARD_API_URL



class TopLevelDomainCache:
    def __init__(self):
        dashboard_api_url = DASHBOARD_API_URL
        self.url = f"{dashboard_api_url}/acceptable-top-level-domains"
        self.cache = self.fetch_top_level_domains()


    def fetch_top_level_domains(self) :
        try:
            bt.logging.info(f"VALIDATOR | Fetching top level domains from {self.url}")
            response = requests.get(self.url, timeout=300)
            bt.logging.info(f"VALIDATOR | Top level domain cache fetched")
            return {record["tld"] for record in response.json()}
        except requests.exceptions.RequestException as e:
            bt.logging.error(f"VALIDATOR | Failed to fetch top level domains: {e}")

    def get_cache(self):
        return self.cache


tld_cache = TopLevelDomainCache()

def get_tld_cache_data():
    if tld_cache.cache is None:
        tld_cache.cache = tld_cache.fetch_top_level_domains()

    return tld_cache.cache


def is_valid_domain(request_id: str, miner_uid: int , domain: str):
    bt.logging.info(f"{request_id} | {miner_uid} | Validating domain {domain}")
    cache_data = get_tld_cache_data()

    valid_domain = domain in cache_data

    bt.logging.info(f"{request_id} | {miner_uid} | {domain} is acceptable : {valid_domain} ")

    return valid_domain
