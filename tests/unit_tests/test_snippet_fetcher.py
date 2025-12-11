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
# 3 samples from each domain extracted from presentational_df_copy.csv
TEST_URLS = [
    "https://www.animalsaroundtheglobe.com/15-wild-predators-that-can-smell-you-before-they-see-you-4-318172/",
    "https://www.animalsaroundtheglobe.com/15-wild-species-making-a-comeback-2-327631/",
    "https://www.animalsaroundtheglobe.com/experts-say-the-gulf-stream-may-collapse-sooner-than-expected-1-311626/",
    "https://biologyinsights.com/what-lives-in-deserts-plant-and-animal-adaptations/",
    "https://biologyinsights.com/adaptations-and-interactions-of-desert-life-forms/",
    "https://biologyinsights.com/is-an-octopus-an-alien-the-scientific-answer/",
    "https://www.businessinsider.com/paris-summer-olympics-2024",
    "https://www.businessinsider.com/silicon-valley-vcs-are-funding-more-startups-outside-the-bay-area-2021-2",
    "https://www.businessinsider.com/new-york-yankees-world-series-wins-2024-10",
    "https://www.cnn.com/travel/article/forrest-fenn-treasure-found-identity-revealed-trnd/index.html",
    "https://www.cnn.com/2023/03/22/world/ramadan-astronauts-space-station-scn/index.html",
    "https://www.cnn.com/travel/diwali-festival-of-lights-explained-cec/index.html",
    "https://www.encyclopedia.com/philosophy-and-religion/other-religious-beliefs-and-general-terms/religion-general/afterlife",
    "https://www.encyclopedia.com/environment/energy-government-and-defense-magazines/glacial-retreat",
    "https://www.encyclopedia.com/philosophy-and-religion/ancient-religions/ancient-religion/odin",
    "https://facts.net/history/historical-events/39-facts-about-magna-carta-signed/",
    "https://facts.net/history/culture/34-facts-about-victorian-dress/",
    "https://facts.net/culture-and-the-arts/performing-arts/26-facts-about-didgeridoo/",
    "https://brief-history-of-the-world.fandom.com/wiki/French_Revolution",
    "https://mythus.fandom.com/wiki/Odin",
    "https://poker.fandom.com/wiki/The_History_of_Poker",
    "https://www.fastercapital.com/content/Ethical-Egoism--Ethical-Egoism--Balancing-Self-Interest-with-Utilitarian-Ideals.html",
    "https://fastercapital.com/content/Medical-Caveats--Understanding-the-Limitations-of-New-Treatments.html",
    "https://fastercapital.com/topics/history-of-coffee-trading.html",
    "https://fiveable.me/key-terms/ap-gov/treaty-of-versailles",
    "https://library.fiveable.me/key-terms/ap-gov/magna-carta",
    "https://library.fiveable.me/key-terms/world-geography/desert-climate",
    "https://timesofindia.indiatimes.com/life-style/food-news/14-everyday-herbs-and-spices-that-may-help-prevent-cancer-diabetes-and-heart-disease/articleshow/122898702.cms",
    "https://timesofindia.indiatimes.com/life-style/travel/great-migration-in-serengeti-best-time-for-safari-and-costs/articleshow/123924227.cms",
    "https://economictimes.indiatimes.com/news/bitcoin",
    "https://www.livescience.com/most-famous-bigfoot-sightings",
    "https://www.livescience.com/61946-ball-lightning-quantum-particle.html",
    "https://www.livescience.com/23310-serengeti.html",
    "https://medium.com/coinmonks/decentralized-nft-marketplace-a-comprehensive-guide-to-building-and-leveraging-business-growth-a4b810772138",
    "https://medium.com/@nawazasma3032/how-chocolate-conquered-the-world-from-aztec-elitism-to-global-treat-c87933d80882",
    "https://medium.com/@alexglushenkov/back-to-the-future-humanitys-quest-to-master-time-travel-6af0f111ecb1",
    "https://science.nasa.gov/climate-change/extreme-weather/",
    "https://science.nasa.gov/solar-system/meteors-meteorites/perseids/",
    "https://exoplanets.nasa.gov/news/1767/discovery-alert-with-six-new-worlds-5500-discovery-milestone-passed/",
    "https://www.space.com/33786-lunar-eclipse-guide.html",
    "https://www.space.com/23686-international-space-station-15-facts.html",
    "https://www.space.com/v2-rocket",
    "https://www.studysmarter.co.uk/explanations/history/us-history/european-colonization/",
    "https://www.studysmarter.co.uk/explanations/religious-studies/belief-systems/afterlife-beliefs/",
    "https://www.studysmarter.co.uk/explanations/religious-studies/philosophy-and-ethics/ethical-egoism/",
    "https://testbook.com/ias-preparation/treaty-of-versailles-1919",
    "https://testbook.com/question-answer/the-first-railway-in-the-world-was-opened-in-1825--64a6c6549cd2458c4fcc58b4",
    "https://testbook.com/question-answer/each-orbit-of-international-space-station-iss-ta--642ef2fcfad238ab274417a8",
    "https://www.thecollector.com/10-facts-about-michelangelo-david-sculpture/",
    "https://www.thecollector.com/odin-all-father-norse-god-facts/",
    "https://www.thecollector.com/what-is-paradox-time-travel/",
    "https://www.usatoday.com/story/sports/mlb/2024/10/24/world-series-2024-new-york-yankees-dodgers-history/75811349007/",
    "https://www.usatoday.com/story/sports/olympics/2024/08/01/usain-bolt-how-many-olympic-medals/74423856007/",
    "https://www.usatoday.com/story/news/nation/2025/08/10/perseid-meteor-shower-2025/85577274007/",
    "https://www.vaia.com/en-us/explanations/math/statistics/bayesian-statistics/",
    "https://www.vaia.com/en-us/explanations/english-literature/american-literature/moby-dick/",
    "https://www.vaia.com/en-us/textbooks/biology/biology-life-on-earth-with-physiology-11-edition/chapter-30/problem-5-list-some-adaptations-of-desert-cactus-plants-and-/",
    "https://vocal.media/earth/the-mariana-trench-the-deepest-depths",
    "https://vocal.media/art/michelangelo-s-david-a-colossal-masterpiece-of-renaissance-art",
    "https://vocal.media/education/top-10-food-preservation-methods-past-and-present",
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
    success = False
    snippet_fetcher = None
    try:
        snippet_fetcher = SnippetFetcher()
        page_text = await snippet_fetcher.fetch_entire_page("abc", 1, url)
        if page_text and len(page_text) > 0:
            success = True
        print(page_text)
        # Create tasks
    except Exception as e:
        print(f"Error: {e}")
    finally:
        duration = time.perf_counter() - start
        print(f"Time taken for {url}:  {duration:.4f} seconds")
        if snippet_fetcher:
            await snippet_fetcher.client.aclose()
    return success

async def main_all_urls():
    """Fetch all URLs in the TEST_URLS array"""
    miner_uid = 1
    snippet_fetcher = SnippetFetcher()
    
    # Track results
    successes = []
    errors = []
    total_start = time.perf_counter()

    try:
        for i, url in enumerate(TEST_URLS):
            print(f"\n{'='*80}")
            print(f"Fetching URL {i+1}/{len(TEST_URLS)}: {url}")
            print(f"{'='*80}\n")

            start = time.perf_counter()
            try:
                page_text = await snippet_fetcher.fetch_entire_page(f"test-{i}", miner_uid, url)
                duration = time.perf_counter() - start

                # Check if successful (has content)
                if page_text and len(page_text) > 0:
                    successes.append({
                        'url': url,
                        'length': len(page_text),
                        'duration': duration
                    })
                    print(f"\n{'='*80}")
                    print(f"✓ SUCCESS - {url}:")
                    print(f"Length: {len(page_text)} characters")
                    print(f"Time taken: {duration:.4f} seconds")
                    print(f"{'='*80}\n")
                    print(page_text[:500] + "..." if len(page_text) > 500 else page_text)
                    print("\n")
                else:
                    errors.append({
                        'url': url,
                        'error': 'Empty response',
                        'duration': duration
                    })
                    print(f"\n{'='*80}")
                    print(f"✗ ERROR - {url}:")
                    print(f"Empty response (no content)")
                    print(f"Time taken: {duration:.4f} seconds")
                    print(f"{'='*80}\n")
            except Exception as e:
                duration = time.perf_counter() - start
                errors.append({
                    'url': url,
                    'error': str(e),
                    'duration': duration
                })
                print(f"\n{'='*80}")
                print(f"✗ ERROR - {url}:")
                print(f"Exception: {e}")
                print(f"Time taken: {duration:.4f} seconds")
                print(f"{'='*80}\n")
    finally:
        await snippet_fetcher.client.aclose()
        
        # Print summary
        total_duration = time.perf_counter() - total_start
        print(f"\n{'='*80}")
        print(f"TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total URLs tested: {len(TEST_URLS)}")
        print(f"✓ Successes: {len(successes)}")
        print(f"✗ Errors: {len(errors)}")
        print(f"Total time: {total_duration:.4f} seconds")
        print(f"Success rate: {(len(successes) / len(TEST_URLS) * 100):.1f}%")
        print(f"{'='*80}\n")
        
        if errors:
            print(f"\nERROR DETAILS ({len(errors)} errors):")
            print(f"{'='*80}")
            for error in errors:
                print(f"  ✗ {error['url']}")
                print(f"    Error: {error['error']}")
                print(f"    Duration: {error['duration']:.4f} seconds")
                print()
        
        if successes:
            avg_duration = sum(s['duration'] for s in successes) / len(successes) if successes else 0
            avg_length = sum(s['length'] for s in successes) / len(successes) if successes else 0
            print(f"\nSUCCESS STATISTICS:")
            print(f"{'='*80}")
            print(f"  Average response length: {avg_length:.0f} characters")
            print(f"  Average fetch time: {avg_duration:.4f} seconds")
            print(f"{'='*80}\n")

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
        result = asyncio.run(main(args.url))
        print(f"\n{'='*80}")
        if result:
            print("✓ SUCCESS - URL fetched successfully")
        else:
            print("✗ ERROR - Failed to fetch URL or empty response")
        print(f"{'='*80}\n")
