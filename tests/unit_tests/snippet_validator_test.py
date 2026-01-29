import unittest
from validator.snippet_validator import SnippetValidator
from urllib.parse import urlparse
import tldextract
import ipaddress

class TestSnippetValidator(unittest.TestCase):
    def setUp(self):
        self.validator = SnippetValidator()

    def test_extract_domain(self):
        # Test regular domain names
        """
        Tests that the `_extract_domain` method correctly extracts domains from URLs.

        Test cases include:

        - Regular domain names
        - IP addresses
        - Different TLDs
        - Edge cases

        """
        self.assertEqual(
            self.validator._extract_domain("https://www.example.com/path"),
            "example.com"
        )
        self.assertEqual(
            self.validator._extract_domain("https://subdomain.example.co.uk/"),
            "example.co.uk"
        )

        # Test IP addresses (HTTPS required by validator)
        self.assertEqual(
            self.validator._extract_domain("https://192.168.1.1/path"),
            "192.168.1.1"
        )
        self.assertEqual(
            self.validator._extract_domain("https://[2001:db8::1]/path"),
            "2001:db8::1"
        )

        # Test different TLDs
        self.assertEqual(
            self.validator._extract_domain("https://example.org"),
            "example.org"
        )
        self.assertEqual(
            self.validator._extract_domain("https://example.co.jp"),
            "example.co.jp"
        )

        # Test edge cases
        self.assertEqual(
            self.validator._extract_domain("https://localhost"),
            "localhost"
        )
        self.assertEqual(
            self.validator._extract_domain("https://example"),
            "example"
        )

    def test_same_domain_responses(self):
        # Test URLs with multiple subdomains of advertisermetasupport.com
        """
        Tests that URLs with multiple subdomains of advertisermetasupport.com
        produce the same domain after extraction.

        Tests that URLs with different domains produce different domains after extraction.
        """
        test_urls = [
            "https://advertisermetasupport.com/posts/78228",
            "https://metacatalog.advertisermetasupport.com/posts/78229",
            "https://catalog.advertisermetasupport.com/posts/78230",
            "https://answer.advertisermetasupport.com/posts/78231",
            "https://knowledge.advertisermetasupport.com/posts/78232",
            "https://metawiki.advertisermetasupport.com/posts/78233",
            "https://metawikipedia.advertisermetasupport.com/posts/78234",
            "https://wiki.advertisermetasupport.com/posts/78235",
            "https://wikipedia.advertisermetasupport.com/posts/78236"
        ]

        # Extract domains from all URLs
        domains = [self.validator._extract_domain(url) for url in test_urls]

        # All domains should be "advertisermetasupport.com" after extraction
        expected_domain = "advertisermetasupport.com"
        for domain in domains:
            self.assertEqual(domain, expected_domain,
                           f"Domain {domain} does not match expected {expected_domain}")

        # Test with mixed domains (should fail)
        mixed_urls = [
            "https://advertisermetasupport.com/post1",
            "https://different-domain.com/post2",
        ]

        domains = [self.validator._extract_domain(url) for url in mixed_urls]

        # Verify domains are different
        self.assertNotEqual(domains[0], domains[1],
                          "Domains should be different in this test case")

if __name__ == '__main__':
    unittest.main()
