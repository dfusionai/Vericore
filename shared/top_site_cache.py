import bittensor as bt
import requests
from shared.environment_variables import DASHBOARD_API_URL

class TopSitesCache:
    def __init__(self):
        dashboard_api_url = DASHBOARD_API_URL
        self.url = f"{dashboard_api_url}/acceptable-top-level-domains"
        self.cache = self.fetch_top_sites()


    def fetch_top_sites(self) :
        try:
            bt.logging.info(f"VALIDATOR | Fetching domains from {self.url}")
            response = requests.get(self.url, timeout=300)
            bt.logging.info(f"VALIDATOR | Top domain cache fetched")
            return {record["tld"] for record in response.json()}
        except requests.exceptions.RequestException as e:
            bt.logging.error(f"VALIDATOR | Failed to fetch domains: {e}")

    def get_cache(self):
        return self.cache


top_sites_cache = TopSitesCache()

def get_top_site_cache_data():
    if top_sites_cache.cache is None:
        top_sites_cache.cache = top_sites_cache.fetch_top_sites()

    return top_sites_cache.cache


def is_approved_site(request_id: str, miner_uid: int, site: str):
    bt.logging.info(f"{request_id} | {miner_uid} | Validating site {site}")
    cache_data = get_top_site_cache_data()

    valid_site = site in cache_data

    bt.logging.info(f"{request_id} | {miner_uid} | {site} is acceptable : {valid_site} ")

    return valid_site
