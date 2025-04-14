import datetime

import requests

from bs4 import BeautifulSoup


import bittensor as bt

from shared.http_helper import send_get_request


class SnippetFetcher:

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
            response = await send_get_request(url, headers=headers) #requests.get(url, headers=headers)
          finally:
              bt.logging.info(f"Received response: {url} : {response.status} : {(datetime.datetime.now() - start_time).total_seconds()} seconds" )

          if response.status_code == 200:
              bt.logging.info(f"Passing to Beautiful soup for cleaning: {url}")

              soup = BeautifulSoup(response.text, "html.parser")

              bt.logging.info(f"Cleaning html")

              # Remove common ad elements
              for tag in soup.find_all(["script", "iframe", "ins", "aside", "noscript"]):
                  tag.decompose()  # Remove the tag from the DOM

              clean_html = str(soup)
              return clean_html
          else:
              bt.logging.error(f"Failed to fetch {url} - {response.status_code}")
              return ""
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
