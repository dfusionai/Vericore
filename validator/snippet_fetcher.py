import datetime
import time
import asyncio
import httpx
from bs4 import BeautifulSoup
from aiolimiter import AsyncLimiter

import bittensor as bt
import certifi

REQUEST_TIMEOUT_SECONDS = 20


class SnippetFetcher:

    def __init__(self):
        # Initialize a shared client once
        self.client = httpx.AsyncClient(
            verify=certifi.where(),
            follow_redirects=True,
            http2=True,
            headers={
                "User-Agent":(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept-Encoding": "gzip, deflate"
            },
            timeout=REQUEST_TIMEOUT_SECONDS,  # Adjust as needed
        )
        self.limiter = AsyncLimiter(1, 10.0)  # 5 requests/second

    # Implement async context manager methods
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        print("Snippet fetcher closing")
        await self.client.aclose()

    async def send_get_request(
        self, request_id: str, miner_uid: int, endpoint: str, headers: dict = None
    ):
        start = time.perf_counter()
        try:
            bt.logging.info(
                f"{request_id} | {miner_uid} | {endpoint} | Sending request"
            )
            response = await self.client.get(
                endpoint, timeout=REQUEST_TIMEOUT_SECONDS, headers=headers
            )

            duration = time.perf_counter() - start

            bt.logging.info(
                f"{request_id} | {miner_uid} | {endpoint} | Received response {response.status_code} | {duration:.4f} seconds"
            )

            return response
        except Exception as e:
            duration = time.perf_counter() - start
            bt.logging.warning(
                f"{request_id} | {miner_uid} | {endpoint} | Error {e} | {duration:.4f} seconds"
            )

    async def clean_html(
        self, request_id: str, miner_uid: int, url: str, html: str
    ) -> str:
        bt.logging.info(f"{request_id} | {miner_uid} | {url} | Cleaning html")
        soup = BeautifulSoup(html, "lxml")  # 5-10x faster than html.parser

        bt.logging.info(f"{request_id} | {miner_uid} | {url} | Decomposing  html")

        # Single-pass removal using CSS selectors
        for tag in soup.select("script, iframe, ins, aside, noscript"):
            tag.decompose()

        return await asyncio.to_thread(soup.getText, separator=" ", strip=True)

    async def fetch_entire_page(
        self, request_id: str, miner_uid: int, url: str
    ) -> str | None:
        """
        Pull the final rendered HTML (post-JS) using http request.
        Return it as a string.
        """
        # headers = { "User-Agent": "Mozilla/5.0" }  # Mimic a real browser

        bt.logging.info(f"{request_id} | {miner_uid} | {url} | Fetching entire page")
        try:
            start = time.perf_counter()

            response = await self.send_get_request(
                request_id, miner_uid, url
            )  # requests.get(url, headers=headers)

            if response is None or response.status_code != 200:
                bt.logging.info(f"{request_id} | {miner_uid} | {url} | Returning empty html")
                return ""

            cleaned_html: str = await self.clean_html(
                request_id, miner_uid, url, response.text
            )

            duration = time.perf_counter() - start
            bt.logging.info(
                f"{request_id} | {miner_uid} | {url} | Fetched html | {duration:.4f} seconds"
            )
            return cleaned_html
        except Exception as e:
            bt.logging.error(
                f"{request_id} | {miner_uid} | {url} | Failed to fetch html {e}"
            )
            return ""

        # self.driver = webdriver.Chrome(service=self.service, options=self.chrome_options)
        # try:
        #     bt.logging.info(f"Fetching url: {url}")
        #     self.driver.get(url)
        #     page_source = self.driver.page_source
        #     return page_source
        # except Exception as e:
        #     bt.logging.error(f"Failed to fetch {url} - {e}")
        #     return ""
        # # finally:
        #    # self.driver.quit()
