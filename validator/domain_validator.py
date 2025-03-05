import whois
import sys

from datetime import datetime

def domain_is_recently_registered(domain):
    domain_info = whois.whois(domain)
    creation_date = domain_info.creation_date

    print(f"domain_info: {domain_info}")

    # Check if creation_date is within the last X days (e.g., 30 days)
    if isinstance(creation_date, list):
        creation_date = creation_date[0]  # In case of multiple creation dates

    return (datetime.now() - creation_date).days <= 30  # Adjust the days threshold

# Used for testing purposes
if __name__ == "__main__":
    if len(sys.argv) < 2:
      print("Usage: python domain_validator.py '<domain_url>'")
      sys.exit(1)

    domain_url = sys.argv[1]

    isRecently = domain_is_recently_registered(domain_url)

    print("is_recently_registered", isRecently)
