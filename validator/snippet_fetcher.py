# validator/snippet_fetcher.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from lxml import html
import logging

class SnippetFetcher:
    def __init__(self):
        pass

    def fetch_entire_page(self, url: str) -> str:
        """
        Pull the final rendered HTML (post-JS) using headless Chrome.
        Return it as a string.
        """
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(url)
            page_source = driver.page_source
            driver.quit()
            return page_source
        except Exception as e:
            logging.error(f"Failed to fetch {url} - {e}")
            return ""