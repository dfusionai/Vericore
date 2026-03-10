import os
from dotenv import load_dotenv

load_dotenv()

DASHBOARD_API_URL= os.environ.get("DASHBOARD_API_URL", "https://api.dashboard.vericore.dfusion.ai")

USE_AI_API = os.environ.get("USE_AI_API", "True").lower() == 'true'
AI_API_URL = os.environ.get("AI_API_URL", "https://api.dashboard.vericore.dfusion.ai")


USE_HTML_PARSER_API = os.environ.get("USE_HTML_PARSER_API", "False").lower() == 'true'
HTML_PARSER_API_URL = os.environ.get("HTML_PARSER_API_URL", "https://api.snippet-fetcher.vericore.dfusion.ai")

VERICORE_VALIDATOR_VERSION = os.environ.get("VERICORE_VALIDATOR_VERSION", "v0.0.43.4")

# JWT auth for proxy -> validator: defaults to keys/validator_jwt_public.pem.
# Override with VALIDATOR_JWT_PUBLIC_KEY_FILE (path) or VALIDATOR_JWT_PUBLIC_KEY (inline PEM).
_DEFAULT_JWT_PUBLIC_KEY_FILE = "keys/validator_jwt_public.pem"


def _load_jwt_public_key():
    inline = os.environ.get("VALIDATOR_JWT_PUBLIC_KEY")
    if inline:
        return inline
    key_file = os.environ.get("VALIDATOR_JWT_PUBLIC_KEY_FILE", _DEFAULT_JWT_PUBLIC_KEY_FILE)
    path = os.path.abspath(os.path.expanduser(key_file))
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


VALIDATOR_JWT_PUBLIC_KEY = _load_jwt_public_key()
VALIDATOR_JWT_ALGORITHM = os.environ.get("VALIDATOR_JWT_ALGORITHM", "RS512")

INITIAL_WEIGHT = 0.7

# Desearch (miner-side): API key for Desearch; set when using Desearch miner.
# Web search: GET https://api.desearch.ai/web?num=10&start=0&query=...
DESEARCH_API_KEY = os.environ.get("DESEARCH_API_KEY", "")
DESEARCH_BASE_URL = os.environ.get("DESEARCH_BASE_URL", "https://api.desearch.ai")

NEUTRAL_SCORE=10
IMMUNITY_PERIOD = 100 # Ensures new miners have a full day to prove themselves, even if other miners have been idle.
IMMUNITY_WEIGHT = 0.5
