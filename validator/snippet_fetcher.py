# validator/snippet_fetcher.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager
from lxml import html
import logging

class SnippetFetcher:
    driver: WebDriver

    def __init__(self):
      chrome_options = Options()
      chrome_options.add_argument("--headless")
      service = Service(ChromeDriverManager().install())
      self.driver = webdriver.Chrome(service=service, options=chrome_options)

    def __del__(self):
      self.driver.quit()

    def fetch_entire_page(self, url: str) -> str:
      """
      Pull the final rendered HTML (post-JS) using headless Chrome.
      Return it as a string.
      """
      try:
          self.driver.get(url)
          page_source = self.driver.page_source
          return page_source
      except Exception as e:
          logging.error(f"Failed to fetch {url} - {e}")
          return ""


