import datetime
import asyncio
# import requests
import httpx
from bs4 import BeautifulSoup


import bittensor as bt

from shared.http_helper import send_get_request

REQUEST_TIMEOUT_SECONDS = 60

class SnippetFetcher:


    def __int__(self):
        # Initialize a shared client once
        self.client = httpx.AsyncClient(
            http2=True,
            headers={ "User-Agent": "Mozilla/5.0" },
            timeout=60.0  # Adjust as needed
        )

    async def send_get_request(self, endpoint: str):
            return await self.client.get(endpoint, timeout=REQUEST_TIMEOUT_SECONDS)

    async def clean_html(self, url: str, html :str) -> str:
        bt.logging.info(f"{ url } | Cleaning html")
        soup = BeautifulSoup(html, "lxml")  # 5-10x faster than html.parser

        bt.logging.info(f"{url} | Decomposing  html")

        # Single-pass removal using CSS selectors
        for tag in soup.select("script, iframe, ins, aside, noscript"):
            tag.decompose()

        return str(soup)

    async def fetch_entire_page(self, url: str) -> str:
      """
      Pull the final rendered HTML (post-JS) using http request.
      Return it as a string.
      """
      headers = { "User-Agent": "Mozilla/5.0" }  # Mimic a real browser

      bt.logging.info(f"Fetching url: {url}")
      try:

          start_time = datetime.datetime.now()
          try:
            response = await self.send_get_request(url) #requests.get(url, headers=headers)
          finally:
              bt.logging.info(f"Received response: {url} : {response.status} : {(datetime.datetime.now() - start_time).total_seconds()} seconds" )

          if response.status_code != 200:
              bt.logging.error(f"Failed to fetch {url} - {response.status_code}")
              return ""

          response = await asyncio.to_thread(self.clean_html, response.text)

          bt.logging.info(f"{url} | Fetched html | {(datetime.datetime.now() - start_time).total_seconds()} seconds")

          return response

      except Exception as e:
          bt.logging.error(f"Failed to fetch {url} - {e}")
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
