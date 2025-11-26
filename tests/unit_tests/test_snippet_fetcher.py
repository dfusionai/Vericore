import unittest
import asyncio
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Mock bittensor before importing
# Allow real logging if RUN_NETWORK_TESTS is set to see actual errors
if os.environ.get('RUN_NETWORK_TESTS', '').lower() == 'true':
    # Use real bittensor logging for network tests to see actual errors
    import bittensor as bt
    bt.logging.set_trace()
else:
    # Mock bittensor for unit tests
    sys.modules['bittensor'] = MagicMock()
    bt_mock = MagicMock()
    bt_mock.logging = MagicMock()
    bt_mock.logging.info = MagicMock()
    bt_mock.logging.warning = MagicMock()
    bt_mock.logging.error = MagicMock()
    sys.modules['bittensor'] = bt_mock

# Mock shared modules
sys.modules['shared.environment_variables'] = MagicMock()
env_vars_mock = MagicMock()
env_vars_mock.HTML_PARSER_API_URL = "https://api.example.com"
env_vars_mock.USE_HTML_PARSER_API = False
sys.modules['shared.environment_variables'] = env_vars_mock

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from validator.snippet_fetcher import SnippetFetcher, fetch_entire_page

# Array of hard-coded test URLs for snippet fetching
TEST_URLS = [
    "https://nmaahc.si.edu/explore/stories/unforgettable-nat-king-cole-flip-wilson-american-television",
    "https://www.pbs.org/wnet/nature/blog/killer-whale-fact-sheet/",
    "https://medium.com/@arbormove/urbanization-and-real-estate-value-navigating-the-changing-landscape-with-arbor-move-28a177d66319",
    "https://www.catf.us/2025/02/introduction-next-clean-energy-frontier-superhot-rock-geothermal-pathways-commercial-liftoff/",
    "https://www.earthday.org/breaking-the-dam-how-the-supreme-court-eroded-50-years-of-clean-water-protection/",
]


class TestSnippetFetcher(unittest.TestCase):
    """Unit tests for SnippetFetcher class"""

    def setUp(self):
        """Set up test fixtures"""
        self.fetcher = SnippetFetcher()
        self.test_url = TEST_URLS[0]  # Default to first URL
        self.request_id = "test-req-123"
        self.miner_uid = 1

    def tearDown(self):
        """Clean up after tests"""
        # Close the client if it exists
        if hasattr(self, 'fetcher') and hasattr(self.fetcher, 'client'):
            try:
                asyncio.run(self.fetcher.client.aclose())
            except:
                pass

    def test_get_browser_headers(self):
        """Test that browser headers are generated correctly"""
        headers = self.fetcher._get_browser_headers(url=self.test_url)

        # Check that required headers are present
        self.assertIn("User-Agent", headers)
        self.assertIn("Accept", headers)
        self.assertIn("Accept-Language", headers)
        self.assertIn("Accept-Encoding", headers)
        self.assertIn("Sec-Fetch-Dest", headers)
        self.assertIn("Sec-Fetch-Mode", headers)

        # Check that User-Agent is from the list
        from validator.snippet_fetcher import USER_AGENTS
        self.assertIn(headers["User-Agent"], USER_AGENTS)

    def test_get_browser_headers_with_referer(self):
        """Test browser headers with custom referer"""
        referer = "https://example.com/page"
        headers = self.fetcher._get_browser_headers(url=self.test_url, referer=referer)

        self.assertEqual(headers["Referer"], referer)
        self.assertEqual(headers["Sec-Fetch-Site"], "cross-site")

    def test_get_browser_headers_without_referer(self):
        """Test browser headers without referer"""
        headers = self.fetcher._get_browser_headers(url=self.test_url)

        # Should generate referer from URL
        self.assertIn("Referer", headers)
        self.assertEqual(headers["Sec-Fetch-Site"], "cross-site")

    def test_clean_html_removes_scripts(self):
        """Test that clean_html removes script tags and other unwanted elements"""
        html_content = """
        <html>
            <head><title>Test</title></head>
            <body>
                <script>alert('test');</script>
                <p>This is visible text</p>
                <iframe src="test.html"></iframe>
                <aside>Sidebar content</aside>
                <noscript>No script content</noscript>
            </body>
        </html>
        """

        async def run_test():
            async with self.fetcher:
                result = await self.fetcher.clean_html(
                    self.request_id,
                    self.miner_uid,
                    self.test_url,
                    html_content
                )

                # Should contain visible text
                self.assertIn("This is visible text", result)

                # Should not contain script content
                self.assertNotIn("alert", result)
                self.assertNotIn("test.html", result)
                self.assertNotIn("Sidebar content", result)
                self.assertNotIn("No script content", result)

        asyncio.run(run_test())

    @unittest.skip("Requires network access - run manually with: python -m pytest tests/unit_tests/test_snippet_fetcher.py::TestSnippetFetcher::test_fetch_nmaahc_url -v")
    def test_fetch_nmaahc_url(self):
        """Test fetching the NMAAHC Nat King Cole article URL

        This test fetches the actual URL and validates the content.
        Run manually: python -m unittest tests.unit_tests.test_snippet_fetcher.TestSnippetFetcher.test_fetch_nmaahc_url
        """
        async def run_test():
            async with self.fetcher:
                result = await self.fetcher.fetch_entire_page(
                    self.request_id,
                    self.miner_uid,
                    TEST_URLS[0]
                )

                # Should return non-empty string
                self.assertIsNotNone(result)
                self.assertIsInstance(result, str)
                self.assertGreater(len(result), 0)

                # Should contain expected content from the article
                result_lower = result.lower()
                self.assertIn("nat king cole", result_lower)
                self.assertIn("flip wilson", result_lower)
                self.assertIn("television", result_lower)

                # Should contain key topics from the article
                self.assertTrue("variety" in result_lower or "variety show" in result_lower)
                self.assertIn("african american", result_lower)

        asyncio.run(run_test())

    @unittest.skip("Requires network access - run manually")
    def test_fetch_pbs_killer_whale_url(self):
        """Test fetching the PBS Killer Whale fact sheet URL"""
        async def run_test():
            async with self.fetcher:
                result = await self.fetcher.fetch_entire_page(
                    self.request_id,
                    self.miner_uid,
                    TEST_URLS[1]
                )

                # Should return non-empty string
                self.assertIsNotNone(result)
                self.assertIsInstance(result, str)
                self.assertGreater(len(result), 0)

                # Should contain expected content from the article
                result_lower = result.lower()
                self.assertIn("killer whale", result_lower)
                self.assertIn("orca", result_lower)
                self.assertIn("dolphin", result_lower)

                # Should contain key facts
                self.assertTrue("orca" in result_lower or "orcinus" in result_lower)
                self.assertIn("delphinidae", result_lower)

        asyncio.run(run_test())

    @unittest.skipUnless(
        os.environ.get('RUN_NETWORK_TESTS', '').lower() == 'true',
        "Requires network access - set RUN_NETWORK_TESTS=true to run"
    )
    def test_fetch_all_test_urls(self):
        """Test fetching all URLs in the TEST_URLS array"""
        async def run_test():
            async with self.fetcher:
                for i, url in enumerate(TEST_URLS):
                    with self.subTest(url=url):
                        # Get response directly to see status codes
                        response = await self.fetcher.render_page(
                            f"{self.request_id}-{i}",
                            self.miner_uid,
                            url
                        )

                        # Log response details for debugging
                        if response is None:
                            print(f"\n❌ {url}: No response (request failed)")
                        elif response.status_code != 200:
                            print(f"\n❌ {url}: HTTP {response.status_code}")
                            if hasattr(response, 'text') and response.text:
                                # Show first 200 chars of error response
                                error_preview = response.text[:200].replace('\n', ' ')
                                print(f"   Response preview: {error_preview}...")
                        else:
                            print(f"\n✅ {url}: HTTP {response.status_code} ({len(response.text)} bytes)")

                        result = await self.fetcher.fetch_entire_page(
                            f"{self.request_id}-{i}",
                            self.miner_uid,
                            url
                        )

                        # Should return non-empty string
                        self.assertIsNotNone(result, f"Failed to fetch {url}")
                        self.assertIsInstance(result, str)
                        self.assertGreater(len(result), 0, f"Empty result for {url}")
                        self.assertGreater(len(result), 100, f"Result too short for {url}")

        asyncio.run(run_test())

    @unittest.skip("Requires network access - run manually")
    def test_fetch_nmaahc_url_integration(self):
        """Integration test using the module-level fetch_entire_page function"""
        async def run_test():
            result = await fetch_entire_page(
                self.request_id,
                self.miner_uid,
                TEST_URLS[0]
            )

            # Should return non-empty string
            self.assertIsNotNone(result)
            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 0)

            # Verify content quality - should have substantial text
            self.assertGreater(len(result), 500)  # Article should have substantial content

        asyncio.run(run_test())

    @unittest.skip("Requires network access - run manually")
    def test_fetch_nmaahc_url_content_validation(self):
        """Test that fetched content contains expected article elements"""
        async def run_test():
            async with self.fetcher:
                result = await self.fetcher.fetch_entire_page(
                    self.request_id,
                    self.miner_uid,
                    TEST_URLS[0]
                )

                result_lower = result.lower()

                # Verify key historical facts are present
                expected_mentions = [
                    "1956",
                    "1970",
                    "nbc",
                    "emmy",
                    "geraldine",
                    "madison avenue"
                ]

                found_mentions = [mention for mention in expected_mentions if mention in result_lower]
                # Should find at least some of the expected mentions
                self.assertGreater(len(found_mentions), 0,
                                 f"Expected to find some of {expected_mentions}, but found: {found_mentions}")

        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()

