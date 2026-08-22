"""
Configuration module loading environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# load .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
CHECK_INTERVAL: int = int(os.getenv("CHECK_INTERVAL", "120"))
DB_PATH: str = os.getenv("DB_PATH", "bot_data.db")

