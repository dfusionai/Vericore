from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from lxml import html
import logging

class SnippetFetcher:
    def __init__(self):
        # Potentially reuse the driver or create a new one each time 
        # (depending on concurrency model).
        # Below is a minimal approach: create a new driver for each fetch.
        pass

    def fetch_snippet_text(self, url: str, xpath: str, start_char: int, end_char: int) -> str:
        """
        Pull the HTML from `url` with headless Chrome, use xpath to find the 
        relevant element, then slice from start_char to end_char.
        Return the text snippet or empty if any error occurs.
        """
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(url)
            page_source = driver.page_source
            driver.quit()
        except Exception as e:
            logging.error(f"Failed to fetch {url} - {e}")
            return ""

        try:
            tree = html.fromstring(page_source)
            element = tree.xpath(xpath)
            if not element:
                return ""
            # If element is a list of matched nodes, just take first
            text_full = element[0].text_content()
            # Bound the offsets
            start_char = max(0, min(start_char, len(text_full)))
            end_char = max(0, min(end_char, len(text_full)))
            snippet = text_full[start_char:end_char]
            return snippet
        except Exception as e:
            logging.error(f"Failed to parse snippet with xpath={xpath} - {e}")
            return ""
