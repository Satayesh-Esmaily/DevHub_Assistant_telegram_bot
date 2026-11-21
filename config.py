import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
ADMIN_ID = os.getenv("ADMIN_ID", "")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", "8080"))
DIGEST_HOUR_UTC = int(os.getenv("DIGEST_HOUR_UTC", "6"))

if not all([BOT_TOKEN, GITHUB_CLIENT_ID, ENCRYPTION_KEY, PUBLIC_URL, WEBHOOK_SECRET]):
    raise RuntimeError("Missing environment variables. Check your .env file.")
