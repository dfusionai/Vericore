import whois
import bittensor as bt
import sys
import asyncio
from datetime import datetime

async def domain_is_recently_registered(domain) -> bool:
    try:
        domain_info =  await asyncio.to_thread(whois.whois, domain)

        # Give benefit of doubt if error happened: return False
        if domain_info is None:
            return False

        creation_date = domain_info.creation_date

        # Check if creation_date is within the last X days (e.g., 30 days)
        if isinstance(creation_date, list):
            creation_date = creation_date[0]  # In case of multiple creation dates

        return (datetime.now() - creation_date).days <= 30  # Adjust the days threshold
    except Exception as e:
        # Give benefit of doubt if error happened: return False
        bt.logging.error(f"Error validating domain: {e}")
        return False

# Used for testing purposes
if __name__ == "__main__":
    if len(sys.argv) < 2:
      print("Usage: python domain_validator.py '<domain_url>'")
      sys.exit(1)

    domain_url = sys.argv[1]

    isRecently = asyncio.run(domain_is_recently_registered(domain_url))

    print("is_recently_registered", isRecently)
