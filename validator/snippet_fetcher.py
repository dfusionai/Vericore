# validator/snippet_fetcher.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager

import bittensor as bt

import logging

class SnippetFetcher:
    driver: WebDriver

    def __init__(self):
      bt.logging.info("SnippetFetcher.__init__")
      self.chrome_options = Options()
      self.chrome_options.add_argument("--no-proxy-server")
      self.chrome_options.add_argument("--headless")
      self.chrome_options.add_argument("--disable-cache")
      self.service = Service(ChromeDriverManager().install())
      # #todo - ask patrick whether timeout can be shorter that 2 minutes ( if the page doesn't exist - it shouldn't take more than 30 second? )
      self.driver = webdriver.Chrome(service=self.service, options=self.chrome_options)

    def __del__(self):
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
      # finally:
         # self.driver.quit()
