"""Bazaning kunlik avtomatik backup'ini Telegram kanaliga yuborish"""
import asyncio
import datetime
import logging
import os

from aiogram import Bot
from aiogram.types import FSInputFile

from config import DB_USER, DB_PASSWORD, DB_NAME, DB_HOST, DB_PORT, BACKUP_CHANNEL_ID

logger = logging.getLogger(__name__)

BACKUP_HOUR = 3  # Backup qaysi soatda olinadi (server vaqti bo'yicha, 24-soatlik format)
BACKUP_DIR = "/tmp"


async def create_backup_file() -> str:
    """pg_dump orqali bazaning to'liq nusxasini .sql faylga yozadi va fayl yo'lini qaytaradi"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = os.path.join(BACKUP_DIR, f"penaltybot_backup_{timestamp}.sql")

    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD

    process = await asyncio.create_subprocess_exec(
        "pg_dump",
        "-h", DB_HOST,
        "-p", str(DB_PORT),
        "-U", DB_USER,
        "-d", DB_NAME,
        "-f", filepath,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"pg_dump xatosi: {stderr.decode().strip()}")

    return filepath


async def send_backup(bot: Bot):
    """Backup faylini yaratib kanalga yuboradi, so'ng vaqtinchalik faylni o'chiradi"""
    if not BACKUP_CHANNEL_ID:
        return

    filepath = None
    try:
        filepath = await create_backup_file()
        size_mb = os.path.getsize(filepath) / (1024 * 1024)

        await bot.send_document(
            BACKUP_CHANNEL_ID,
            document=FSInputFile(filepath),
            caption=(
                f"🗄 <b>Baza backup'i</b>\n"
                f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"📦 {size_mb:.2f} MB"
            ),
            parse_mode="HTML"
        )
        logger.info(f"Backup muvaffaqiyatli yuborildi ({size_mb:.2f} MB)")

    except Exception:
        logger.exception("Backup yaratish/yuborishda xatolik")
    finally:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)


async def backup_scheduler(bot: Bot):
    """Har kuni BACKUP_HOUR'da avtomatik backup oladigan cheksiz fon vazifasi"""
    while True:
        now = datetime.datetime.now()
        next_run = now.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += datetime.timedelta(days=1)

        wait_seconds = (next_run - now).total_seconds()
        logger.info(f"Keyingi avtomatik backup: {next_run.strftime('%Y-%m-%d %H:%M')}")
        await asyncio.sleep(wait_seconds)

        await send_backup(bot)
