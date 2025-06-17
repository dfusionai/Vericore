import os
from dotenv import load_dotenv

load_dotenv()

DASHBOARD_API_URL= os.environ.get("DASHBOARD_API_URL", "https://dashboard.vericore.dfusion.ai")

AI_API_URL = os.environ.get("AI_API_URL", "https://dashboard.vericore.dfusion.ai")
