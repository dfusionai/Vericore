import time
import asyncio
import httpx
import random
from bs4 import BeautifulSoup
from urllib.parse import urlparse

import bittensor as bt
import certifi

from shared.environment_variables import HTML_PARSER_API_URL, USE_HTML_PARSER_API

REQUEST_TIMEOUT_SECONDS = 60

# Rotating User-Agents to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

class SnippetFetcher:

    def __init__(self):
        bt.logging.info("SnippetFetcher created")

        # Initialize a shared client with cookie support
        self.client = httpx.AsyncClient(
            verify=certifi.where(),
            follow_redirects=True,
            http2=True,
            cookies=httpx.Cookies(),  # Enable cookie jar
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        # self.limiter = AsyncLimiter(max_rate=5, time_period=10.0)  # 10 seconds per 10 seconds
        self.limiter = asyncio.Semaphore(5) # Max 5 concurrent threads

    def _get_browser_headers(self, url: str = None, referer: str = None) -> dict:
        """
        Generate realistic browser headers to avoid bot detection.

        Args:
            url: The target URL (for generating referer if needed)
            referer: Optional referer URL

        Returns:
            Dictionary of browser headers
        """
        # Randomize user agent
        user_agent = random.choice(USER_AGENTS)

        # Generate referer if not provided but URL is available
        if referer is None and url:
            parsed = urlparse(url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"

        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",  # Do Not Track
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none" if referer is None else "cross-site",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        # Add referer if available
        if referer:
            headers["Referer"] = referer

        return headers

    # Implement async context manager methods
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        print("Snippet fetcher closing")
        await self.client.aclose()

    async def send_get_request(
        self, request_id: str, miner_uid: int, endpoint: str, headers: dict = None, referer: str = None
    ):
        """
        Send GET request with anti-bot detection measures.

        Args:
            request_id: Request identifier for logging
            miner_uid: Miner UID for logging
            endpoint: URL to fetch
            headers: Optional custom headers (will be merged with browser headers)
            referer: Optional referer URL

        Returns:
            httpx.Response if successful, None if failed
        """
        start = time.perf_counter()

        # Get realistic browser headers
        browser_headers = self._get_browser_headers(url=endpoint, referer=referer)

        # Merge with custom headers if provided (custom headers take precedence)
        if headers:
            browser_headers.update(headers)

        try:
            bt.logging.info(
                f"{request_id} | {miner_uid} | {endpoint} | Sending request"
            )

            response = await self.client.get(
                endpoint,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers=browser_headers
            )

            duration = time.perf_counter() - start

            # Check for bot detection indicators
            if response.status_code == 403:
                bt.logging.warning(
                    f"{request_id} | {miner_uid} | {endpoint} | "
                    f"403 Forbidden - Possible bot detection | {duration:.4f} seconds"
                )
            elif response.status_code == 429:
                bt.logging.warning(
                    f"{request_id} | {miner_uid} | {endpoint} | "
                    f"429 Too Many Requests - Rate limited | {duration:.4f} seconds"
                )
            else:
                bt.logging.info(
                    f"{request_id} | {miner_uid} | {endpoint} | "
                    f"Received response {response.status_code} | {duration:.4f} seconds"
                )

            return response

        except httpx.TimeoutException as e:
            duration = time.perf_counter() - start
            bt.logging.warning(
                f"{request_id} | {miner_uid} | {endpoint} | "
                f"Timeout after {duration:.4f} seconds: {e}"
            )
            return None

        except httpx.HTTPStatusError as e:
            duration = time.perf_counter() - start
            bt.logging.warning(
                f"{request_id} | {miner_uid} | {endpoint} | "
                f"HTTP error {e.response.status_code} | {duration:.4f} seconds: {e}"
            )
            return None

        except httpx.RequestError as e:
            duration = time.perf_counter() - start
            bt.logging.warning(
                f"{request_id} | {miner_uid} | {endpoint} | "
                f"Request error | {duration:.4f} seconds: {e}"
            )
            return None

        except Exception as e:
            duration = time.perf_counter() - start
            bt.logging.error(
                f"{request_id} | {miner_uid} | {endpoint} | "
                f"Unexpected error | {duration:.4f} seconds: {e}",
                exc_info=True
            )
            return None

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

    async def render_page(self, request_id: str, miner_uid: int, endpoint: str, headers: dict = None, referer: str = None):
        """
        Render a webpage with anti-bot detection measures.

        Args:
            request_id: Request identifier for logging
            miner_uid: Miner UID for logging
            endpoint: URL to fetch
            headers: Optional custom headers
            referer: Optional referer URL for the request

        Returns:
            httpx.Response if successful, None if failed
        """
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
                return await self.send_get_request(request_id, miner_uid, endpoint, headers, referer=referer)

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

snippet_fetcher = SnippetFetcher()

async def fetch_entire_page(
    request_id: str, miner_uid: int, url: str
) -> str | None:
    return await snippet_fetcher.fetch_entire_page(request_id, miner_uid, url)




