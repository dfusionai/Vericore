import unittest

from validator.snippet_fetcher import SnippetFetcher

class TestSnippetFetcher(unittest.TestCase):
    def setUp(self):
        self.snippet_fetcher = SnippetFetcher()

    async def test_ssl(self):
        await self.snippet_fetcher.fetch_entire_page('1',1, 'https://www.google.com')

        await self.snippet_fetcher.fetch_entire_page('1', 1, 'http://advertisermetasupport.com/posts/272115')


if __name__ == '__main__':
    unittest.main()
