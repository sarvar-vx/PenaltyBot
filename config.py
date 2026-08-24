import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN .env faylida topilmadi!")

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 5432))


OWNER_ID = int(os.getenv("OWNER_ID", 0))
if not OWNER_ID:
    raise RuntimeError("OWNER_ID .env faylida topilmadi! Bu sizning shaxsiy Telegram ID'ingiz bo'lishi kerak.")

ADMIN_ENTRY_COMMAND = "alakazam"   # adminchalar uchun
OWNER_ENTRY_COMMAND = "laviosso"   # Faqat owner uchun

VIDEO_CHANNEL_ID = int(os.getenv("VIDEO_CHANNEL_ID", 0))
LOGS_CHANNEL_ID = int(os.getenv("LOGS_CHANNEL_ID", 0))
BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", 0))
