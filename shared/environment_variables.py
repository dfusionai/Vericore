import os
from dotenv import load_dotenv

load_dotenv()

DASHBOARD_API_URL= os.environ.get("DASHBOARD_API_URL", "https://dashboard.vericore.dfusion.ai")

USE_AI_API = os.environ.get("USE_AI_API", "True")
AI_API_URL = os.environ.get("AI_API_URL", "https://dashboard.vericore.dfusion.ai")


USE_HTML_PARSER_API = os.environ.get("USE_HTML_PARSER_API", "False").lower() == 'true'
HTML_PARSER_API_URL = os.environ.get("HTML_PARSER_API_URL", "https://api.snippet-fetcher.vericore.dfusion.ai")
