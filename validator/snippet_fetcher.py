import requests

from bs4 import BeautifulSoup


import bittensor as bt


class SnippetFetcher:

    def fetch_entire_page(self, url: str) -> str:
      """
      Pull the final rendered HTML (post-JS) using http request.
      Return it as a string.
      """
      headers = { "User-Agent": "Mozilla/5.0" }  # Mimic a real browser

      bt.logging.info(f"Fetching url: {url}")
      try:

          response = requests.get(url, headers=headers)

          bt.logging.info(f"Received response: {url}")

          if response.status_code == 200:
              soup = BeautifulSoup(response.text, "html.parser")

              bt.logging.info(f"Cleaning html")

              # Remove common ad elements
              for tag in soup.find_all(["script", "iframe", "ins", "aside", "noscript"]):
                  tag.decompose()  # Remove the tag from the DOM

              clean_html = str(soup)
              return clean_html
          else:
              bt.logging.error(f"Failed to fetch {url} - {response.status_code}: {response.text}")
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
