import os
from dotenv import load_dotenv

load_dotenv()

DEBUG_LOCAL = os.getenv("DEBUG_LOCAL", "False").lower() == "true"
