import time
import asyncio
import httpx
import random
from bs4 import BeautifulSoup
from urllib.parse import urlparse

import bittensor as bt
import certifi

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    bt.logging.warning("Selenium not available - bot detection fallback disabled")

from shared.environment_variables import HTML_PARSER_API_URL, USE_HTML_PARSER_API

REQUEST_TIMEOUT_SECONDS = 60

# Rotating User-Agents to avoid detection (Strategy: Rotate HTTP Headers / User-Agent)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Accept-Language variations (Strategy: Rotate HTTP Headers)
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,fr;q=0.8",
]

class SnippetFetcher:

    def __init__(self):
        bt.logging.info("SnippetFetcher created")

        # Initialize a shared client with cookie support (Strategy: Use Cookies)
        # Cookies are persisted across requests to mimic real user sessions
        self.client = httpx.AsyncClient(
            verify=certifi.where(),
            follow_redirects=True,
            http2=True,
            cookies=httpx.Cookies(),  # Enable cookie jar for session persistence
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        # self.limiter = AsyncLimiter(max_rate=5, time_period=10.0)  # 10 seconds per 10 seconds
        self.limiter = asyncio.Semaphore(5) # Max 5 concurrent threads

        # Selenium driver pool for concurrent requests (Selenium WebDriver is NOT thread-safe)
        # Each driver can only handle one request at a time, so we need a pool
        self._selenium_driver_pool = asyncio.Queue(maxsize=5)  # Pool of up to 5 drivers
        self._selenium_driver_lock = asyncio.Lock()  # Lock for pool operations
        self._selenium_drivers_created = 0  # Track how many drivers we've created
        self._max_selenium_drivers = 5  # Maximum concurrent Selenium drivers

    def _get_browser_headers(self, url: str = None, referer: str = None) -> dict:
        """
        Generate realistic browser headers to avoid bot detection.
        Strategy: Rotate HTTP Headers / User-Agent

        Args:
            url: The target URL (for generating referer if needed)
            referer: Optional referer URL

        Returns:
            Dictionary of browser headers
        """
        # Randomize user agent (Strategy: Rotate HTTP Headers / User-Agent)
        user_agent = random.choice(USER_AGENTS)

        # Randomize Accept-Language (Strategy: Rotate HTTP Headers)
        accept_language = random.choice(ACCEPT_LANGUAGES)

        # Generate referer if not provided but URL is available
        # Use Google search as referer to make it look like user came from search
        # Strategy: Follow Natural Page Flow (coming from search is natural)
        if referer is None:
            if url:
                # Use Google search as referer to appear more natural
                referer = f"https://www.google.com/search?q={urlparse(url).netloc}"
            else:
                referer = "https://www.google.com/"

        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": accept_language,  # Randomized
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


    def _create_selenium_driver(self):
        """
        Create a new Selenium WebDriver with stealth options.
        Strategy: Use Tools / Plugins for "Stealth Mode"

        Returns:
            Selenium WebDriver instance or None if creation fails
        """
        if not SELENIUM_AVAILABLE:
            return None

        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # Run in background
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')  # Hide automation
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            # Randomize user agent
            user_agent = random.choice(USER_AGENTS)
            chrome_options.add_argument(f'user-agent={user_agent}')

            # Disable automation indicators (Strategy: Disable Automation Indicator Flags)
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            # Remove webdriver property (Strategy: Disable Automation Indicator Flags)
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                '''
            })

            bt.logging.info("Selenium WebDriver created for bot detection fallback")
            return driver
        except Exception as e:
            bt.logging.error(f"Failed to create Selenium WebDriver: {e}")
            return None

    async def _get_selenium_driver_from_pool(self):
        """
        Get a Selenium driver from the pool, creating a new one if needed.
        Thread-safe and handles concurrent requests.

        Returns:
            Selenium WebDriver instance or None
        """
        if not SELENIUM_AVAILABLE:
            return None

        async with self._selenium_driver_lock:
            # Try to get an existing driver from the pool
            try:
                driver = self._selenium_driver_pool.get_nowait()
                return driver
            except asyncio.QueueEmpty:
                # No driver available, create a new one if under limit
                if self._selenium_drivers_created < self._max_selenium_drivers:
                    driver = await asyncio.to_thread(self._create_selenium_driver)
                    if driver:
                        self._selenium_drivers_created += 1
                        return driver
                # Pool is full, wait for a driver to become available
                bt.logging.info("Selenium driver pool exhausted, waiting for available driver")
                return await self._selenium_driver_pool.get()

    async def _return_selenium_driver_to_pool(self, driver):
        """
        Return a Selenium driver to the pool for reuse.

        Args:
            driver: Selenium WebDriver instance to return
        """
        if driver is None:
            return

        try:
            # Clear cookies and cache for reuse
            driver.delete_all_cookies()
            await self._selenium_driver_pool.put(driver)
        except Exception as e:
            # If pool is full or error occurs, close the driver
            bt.logging.warning(f"Error returning driver to pool, closing driver: {e}")
            try:
                driver.quit()
                async with self._selenium_driver_lock:
                    self._selenium_drivers_created -= 1
            except:
                pass

    async def _fetch_with_selenium(self, request_id: str, miner_uid: int, url: str) -> httpx.Response:
        """
        Fetch page using Selenium WebDriver as fallback for bot detection.
        Strategy: Use Tools / Plugins for "Stealth Mode"
        Uses a driver pool for concurrent requests (thread-safe).

        Args:
            request_id: Request identifier for logging
            miner_uid: Miner UID for logging
            url: URL to fetch

        Returns:
            Mock httpx.Response-like object with .text and .status_code
        """
        if not SELENIUM_AVAILABLE:
            bt.logging.warning(f"{request_id} | {miner_uid} | {url} | Selenium not available for fallback")
            return None

        # Get a driver from the pool (waits if pool is exhausted)
        driver = await self._get_selenium_driver_from_pool()
        if driver is None:
            return None

        try:
            bt.logging.info(f"{request_id} | {miner_uid} | {url} | Using Selenium fallback for bot detection")

            # Run Selenium in thread since it's synchronous
            # Each driver handles one request at a time (thread-safe)
            def selenium_fetch():
                driver.get(url)
                # Wait for page to load (Strategy: Follow Natural Page Flow)
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                # Additional wait for JavaScript to execute (Cloudflare challenges)
                time.sleep(2)
                return driver.page_source

            html_content = await asyncio.to_thread(selenium_fetch)

            # Create a mock response object compatible with httpx.Response
            class MockResponse:
                def __init__(self, text, status_code=200):
                    self.text = text
                    self.status_code = status_code
                    self.headers = {}

            bt.logging.success(f"{request_id} | {miner_uid} | {url} | Selenium fallback successful")
            return MockResponse(html_content, 200)

        except Exception as e:
            bt.logging.error(f"{request_id} | {miner_uid} | {url} | Selenium fallback failed: {e}")
            # If driver is broken, don't return it to pool - close it
            try:
                driver.quit()
                async with self._selenium_driver_lock:
                    self._selenium_drivers_created -= 1
            except:
                pass
            return None
        finally:
            # Always return driver to pool for reuse (if still valid)
            await self._return_selenium_driver_to_pool(driver)

    # Implement async context manager methods
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        print("Snippet fetcher closing")
        await self.client.aclose()
        # Close all Selenium drivers in the pool
        while not self._selenium_driver_pool.empty():
            try:
                driver = await self._selenium_driver_pool.get()
                driver.quit()
            except Exception as e:
                bt.logging.warning(f"Error closing Selenium driver: {e}")
        self._selenium_drivers_created = 0

    async def send_get_request(
        self, request_id: str, miner_uid: int, endpoint: str, headers: dict = None, referer: str = None
    ):
        """
        Send GET request with anti-bot detection measures.
        Implements strategies: Rotate Headers, Use Cookies

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

        # Get realistic browser headers (Strategy: Rotate HTTP Headers / User-Agent)
        browser_headers = self._get_browser_headers(url=endpoint, referer=referer)

        # Merge with custom headers if provided (custom headers take precedence)
        if headers:
            browser_headers.update(headers)

        try:
            bt.logging.info(
                f"{request_id} | {miner_uid} | {endpoint} | Sending request"
            )

            # Strategy: Use Cookies - cookies are automatically managed by httpx.Cookies()
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
                # Mark response for Selenium fallback (will be handled outside semaphore)
                response._needs_selenium_fallback = True
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
        Semaphore limits HTTP requests only - Selenium has its own concurrency control (driver pool).

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

        if USE_HTML_PARSER_API:
            async with self.limiter:
                return await self.send_html_parser_api_request(request_id, miner_uid, endpoint, headers)
        else:
            # Semaphore limits HTTP requests (fast, ~milliseconds)
            # Selenium fallback happens outside semaphore since it has its own pool limit
            async with self.limiter:
                bt.logging.info(
                    f"{request_id} | {miner_uid} | {endpoint} | Snippet Fetcher: Rendering page - fetching snippet - passed semaphore"
                )
                response = await self.send_get_request(request_id, miner_uid, endpoint, headers, referer=referer)

            # Check if Selenium fallback is needed (outside semaphore context)
            # This allows other HTTP requests to proceed while Selenium runs
            if (response is not None and
                response.status_code == 403 and
                SELENIUM_AVAILABLE and
                hasattr(response, '_needs_selenium_fallback') and
                response._needs_selenium_fallback):

                bt.logging.info(
                    f"{request_id} | {miner_uid} | {endpoint} | "
                    f"Attempting Selenium fallback for 403 response (outside HTTP semaphore)"
                )
                selenium_response = await self._fetch_with_selenium(request_id, miner_uid, endpoint)
                if selenium_response and selenium_response.status_code == 200:
                    return selenium_response
                else:
                    bt.logging.warning(
                        f"{request_id} | {miner_uid} | {endpoint} | "
                        f"Selenium fallback failed, returning original 403 response"
                    )

            return response

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




