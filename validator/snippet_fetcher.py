# validator/snippet_fetcher.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.options import PageLoadStrategy
from webdriver_manager.chrome import ChromeDriverManager

import bittensor as bt

import logging
import atexit

class SnippetFetcher:
    driver: WebDriver

    def __init__(self):
        bt.logging.info("SnippetFetcher.__init__")
        self.chrome_options = Options()
        self.chrome_options.page_load_strategy = 'eager'
        self.chrome_options.add_argument("--no-proxy-server")
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--disable-cache")
        self.service = Service(ChromeDriverManager().install())

        self.driver = webdriver.Chrome(service=self.service, options=self.chrome_options)

        # Set timeout to 30 seconds. If can't load page within 30 seconds, ignore snippets
        self.driver.set_page_load_timeout(30)
        self.driver.set_script_timeout(30)
        self.driver.implicitly_wait(30)

        # Ensure driver quits when the program exits
        atexit.register(self.cleanup)

    def cleanup(self):
        """ Properly quit the driver """
        if hasattr(self, 'driver') and self.driver:
            logging.info("Closing WebDriver")
            self.driver.quit()

    def fetch_entire_page(self, url: str) -> str:
        """
        Pull the final rendered HTML (post-JS) using headless Chrome.
        Return it as a string.
        """
        # self.driver = webdriver.Chrome(service=self.service, options=self.chrome_options)
        try:
            bt.logging.info(f"Fetching url: {url}")
            self.driver.get(url)
            page_source = self.driver.page_source
            return page_source
        except Exception as e:
            bt.logging.error(f"Failed to fetch {url} - {e}")
            return ""
