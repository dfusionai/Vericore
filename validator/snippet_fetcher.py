import time
import asyncio
import httpx
from bs4 import BeautifulSoup
from aiolimiter import AsyncLimiter

import bittensor as bt
import certifi

from shared.environment_variables import HTML_PARSER_API_URL, USE_HTML_PARSER_API

REQUEST_TIMEOUT_SECONDS = 60

class SnippetFetcher:

    def __init__(self):
        bt.logging.info("SnippetFetcher created")

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
        # self.limiter = AsyncLimiter(max_rate=5, time_period=10.0)  # 10 seconds per 10 seconds
        self.limiter = asyncio.Semaphore(10) # Max 10 concurrent threads

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

    async def send_html_parser_api_request(
        self, request_id: str, miner_uid: int, endpoint: str, headers: dict = None
    ):
        start = time.perf_counter()
        try:
            bt.logging.info(
                f"{request_id} | {miner_uid} | {endpoint} | Snippet Fetcher: Sending request"
            )
            request = {
                "url" : endpoint
            }
            response = await self.client.post(
                f"{HTML_PARSER_API_URL}/render",
                json=request,
                timeout=REQUEST_TIMEOUT_SECONDS
            )

            duration = time.perf_counter() - start

            bt.logging.success(
                f"{request_id} | {miner_uid} | {endpoint} | Snippet Fetcher: Received response {response.status_code} | {duration:.4f} seconds"
            )

            return response
        except Exception as e:
            duration = time.perf_counter() - start
            bt.logging.error(
                f"{request_id} | {miner_uid} | {endpoint} | Snippet Fetcher: Error {e} | {duration:.4f} seconds"
            )

    async def render_page(self, request_id: str, miner_uid: int, endpoint: str, headers: dict = None):
        bt.logging.info(
            f"{request_id} | {miner_uid} | {endpoint} | Snippet Fetcher: Rendering page - waiting for semaphore"
        )

        async with self.limiter:
            bt.logging.info(
                f"{request_id} | {miner_uid} | {endpoint} | Snippet Fetcher: Rendering page - fetching snippet - passed semaphore"
            )

            if USE_HTML_PARSER_API:
                return await self.send_html_parser_api_request(request_id, miner_uid, endpoint, headers)
            else:
                return await self.send_get_request(request_id, miner_uid, endpoint, headers)

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

            response = await self.render_page(
                request_id, miner_uid, url
            )

            if response is None or response.status_code != 200:
                bt.logging.error(f"{request_id} | {miner_uid} | {url} | Error occurred | Returning empty html : {response}")
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

snippet_fetcher = SnippetFetcher()

async def fetch_entire_page(
    request_id: str, miner_uid: int, url: str
) -> str | None:
    return await snippet_fetcher.fetch_entire_page(request_id, miner_uid, url)




