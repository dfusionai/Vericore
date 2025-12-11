import argparse
import json
import os
import time
import bittensor as bt
import uuid
import asyncio
from dataclasses import asdict

from shared.veridex_protocol import SourceEvidence
from validator.snippet_fetcher import SnippetFetcher

# Array of hard-coded test URLs for snippet fetching
TEST_URLS = [
    "https://nmaahc.si.edu/explore/stories/unforgettable-nat-king-cole-flip-wilson-american-television",
    "https://www.pbs.org/wnet/nature/blog/killer-whale-fact-sheet/",
    "https://hms.harvard.edu/news/screen-time-brain"
]

def get_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("--custom", default="my_custom_value", help="Custom value")
    parser.add_argument("--netuid", type=int, default=1, help="Chain subnet uid")
    bt.subtensor.add_args(parser)
    bt.logging.add_args(parser)
    bt.wallet.add_args(parser)
    bt.axon.add_args(parser)
    config = bt.config(parser)

    bt.logging.info(f"get_config: {config}")
    config.full_path = os.path.expanduser(
        "{}/{}/{}/netuid{}/validator".format(
            config.logging.logging_dir,
            config.wallet.name,
            config.wallet.hotkey_str,
            config.netuid,
        )
    )
    os.makedirs(config.full_path, exist_ok=True)
    return config

def setup_logging():
    config = get_config()
    bt.logging(config=config, logging_dir=config.full_path)
    bt.logging.info("Starting APIQueryHandler with config:")
    bt.logging.info(config)


# The main routine
async def main(url):
    miner_uid = 1
    start = time.perf_counter()
    try:
        snippet_fetcher = SnippetFetcher()
        page_text = await snippet_fetcher.fetch_entire_page("abc", 1, url)
        print(page_text)
        # Create tasks
    finally:
        duration = time.perf_counter() - start
        print(f"Time taken for {url}:  {duration:.4f} seconds")

async def main_all_urls():
    """Fetch all URLs in the TEST_URLS array"""
    miner_uid = 1
    snippet_fetcher = SnippetFetcher()

    try:
        for i, url in enumerate(TEST_URLS):
            print(f"\n{'='*80}")
            print(f"Fetching URL {i+1}/{len(TEST_URLS)}: {url}")
            print(f"{'='*80}\n")

            start = time.perf_counter()
            try:
                page_text = await snippet_fetcher.fetch_entire_page(f"test-{i}", miner_uid, url)
                duration = time.perf_counter() - start

                print(f"\n{'='*80}")
                print(f"Result for {url}:")
                print(f"Length: {len(page_text)} characters")
                print(f"Time taken: {duration:.4f} seconds")
                print(f"{'='*80}\n")
                print(page_text[:500] + "..." if len(page_text) > 500 else page_text)
                print("\n")
            except Exception as e:
                duration = time.perf_counter() - start
                print(f"Error fetching {url}: {e} (took {duration:.4f} seconds)")
    finally:
        await snippet_fetcher.client.aclose()

# Entry point
if __name__ == "__main__":
    # Initialize bittensor logging to see logs in console
    # Simple initialization - logs will go to console
    import tempfile
    logging_dir = tempfile.mkdtemp(prefix='vericore_test_')
    bt.logging(config=None, logging_dir=logging_dir)
    bt.logging.info("Test logging initialized")
    
    parser = argparse.ArgumentParser(description="Run Snippet Fetcher for url.")
    parser.add_argument(
        "--url",
        type=str,
        default=TEST_URLS[0],
        help="Page to fetch (default: first URL in TEST_URLS array)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch all URLs in TEST_URLS array"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all URLs in TEST_URLS array"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()
    
    # Set debug level if requested
    if args.debug:
        bt.logging.set_debug(True)
        bt.logging.info("Debug logging enabled")

    if args.list:
        print("Available test URLs:")
        for i, url in enumerate(TEST_URLS, 1):
            print(f"  {i}. {url}")
    elif args.all:
        asyncio.run(main_all_urls())
    else:
        asyncio.run(main(args.url))
