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

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Snippet Fetcher for url.")
    parser.add_argument("--url", type=str, default="https://studyfinds.org/content-overload-streaming", help="Page to fetch")
    args = parser.parse_args()

    asyncio.run(main(args.url))
