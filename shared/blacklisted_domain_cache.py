import bittensor as bt
import requests
import time
from shared.environment_variables import DASHBOARD_API_URL

REFRESH_BLACKLISTED_DOMAIN_TIMEOUT = 60 * 60  # one hour


class BlacklistedDomainCache:
    def __init__(self):
        dashboard_api_url = DASHBOARD_API_URL
        self.url = f"{dashboard_api_url}/blacklisted-domains"
        self.cache = self.fetch_blacklisted_domains() or set()
        self.domain_set = set()
        self.subdomain_set = set()

        self.time_refreshed = None
        result = self.fetch_blacklisted_domains()
        if result is not None:
            self.domain_set, self.subdomain_set = result

    def fetch_blacklisted_domains(self) -> tuple[set[str], set[str]] | None:
        try:
            bt.logging.info(f"VALIDATOR | Fetching blacklisted domains from {self.url}")
            response = requests.get(self.url, timeout=300)
            bt.logging.info(f"VALIDATOR | blacklisted_domains_cache fetched")
            self.time_refreshed = time.time()
            domain_set: set[str] = set()
            subdomain_set: set[str] = set()
            for record in response.json():
                d = record.get("domain")
                if not d:
                    continue
                if record.get("is_subdomain", False):
                    subdomain_set.add(d)
                else:
                    domain_set.add(d)
            return (domain_set, subdomain_set)
        except requests.exceptions.RequestException as e:
            bt.logging.error(f"VALIDATOR | Failed to fetch blacklisted domains: {e}")
            return None

    def get_cache(self) -> dict:
        return {"domain_set": self.domain_set, "subdomain_set": self.subdomain_set}

    def requires_refresh(self) -> bool:
        return (
            self.time_refreshed is None
            or time.time() > self.time_refreshed + REFRESH_BLACKLISTED_DOMAIN_TIMEOUT
        )


blacklisted_domain_cache = BlacklistedDomainCache()


def get_blacklisted_domain_cache_data() -> dict:
    if blacklisted_domain_cache.requires_refresh():
        bt.logging.info("Refreshing blacklisted domains cache")
        result = blacklisted_domain_cache.fetch_blacklisted_domains()
        if result is not None:
            blacklisted_domain_cache.domain_set, blacklisted_domain_cache.subdomain_set = result

    return blacklisted_domain_cache.get_cache()


def is_blacklisted_domain(
    request_id: str,
    miner_uid: int,
    domain: str,
    hostname: str | None = None,
) -> bool:
    bt.logging.info(f"{request_id} | {miner_uid} | Validating domain {domain}")
    cache_data = get_blacklisted_domain_cache_data()
    domain_set = cache_data["domain_set"]
    subdomain_set = cache_data["subdomain_set"]

    if hostname is not None:
        blacklisted = (hostname in subdomain_set) or (domain in domain_set)
    else:
        blacklisted = domain in domain_set

    bt.logging.info(f"{request_id} | {miner_uid} | {domain} is blacklisted : {blacklisted} ")

    return blacklisted
