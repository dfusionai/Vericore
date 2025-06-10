import os
from dotenv import load_dotenv

load_dotenv()

DASHBOARD_API_URL= os.environ.get("DASHBOARD_API_URL", "https://dashboard.vericore.dfusion.ai")

VLLM_API_URL = os.environ.get("VLLM_API_URL", "http://34.204.222.98:9000")
