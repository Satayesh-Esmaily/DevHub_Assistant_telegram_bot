import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not all([BOT_TOKEN, GITHUB_CLIENT_ID, ENCRYPTION_KEY]):
    raise RuntimeError("Missing environment variables. Check your .env file.")