import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, OWNER_ID, LOGS_CHANNEL_ID, BACKUP_CHANNEL_ID
from database.engine import init_db, close_db
from database.requests import ensure_owner_exists
from handlers import reset, admin, friend, start, game
from middlewares.registration import UserRegistrationMiddleware
from middlewares.subscription import SubscriptionMiddleware
from utils.telegram_logger import TelegramLogHandler, telegram_log_sender
from utils.backup import backup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    registration_mw = UserRegistrationMiddleware()
    dp.message.middleware(registration_mw)
    dp.callback_query.middleware(registration_mw)

    subscription_mw = SubscriptionMiddleware()
    dp.message.middleware(subscription_mw)
    dp.callback_query.middleware(subscription_mw)

    # Reset router ENG BIRINCHI — har qanday FSM holatidan qat'iy nazar ishlashi kerak
    dp.include_router(reset.router)
    dp.include_router(admin.router)
    dp.include_router(friend.router)
    dp.include_router(start.router)
    dp.include_router(game.router)

    logger.info("📦 Ma'lumotlar bazasi tekshirilmoqda va sozlanmoqda...")
    try:
        await init_db()
        await ensure_owner_exists(OWNER_ID)
    except Exception:
        logger.exception("Bazaga ulanishda xatolik yuz berdi, bot to'xtatilmoqda.")
        return

    log_sender_task = None
    if LOGS_CHANNEL_ID:
        tg_handler = TelegramLogHandler()
        tg_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
        logging.getLogger().addHandler(tg_handler)
        log_sender_task = asyncio.create_task(telegram_log_sender(bot, LOGS_CHANNEL_ID, tg_handler))
        logger.info("📡 Loglar Telegram kanaliga yuborilmoqda.")
    else:
        logger.warning("LOGS_CHANNEL_ID sozlanmagan — loglar faqat konsolga chiqadi.")

    backup_task = None
    if BACKUP_CHANNEL_ID:
        backup_task = asyncio.create_task(backup_scheduler(bot))
        logger.info("🗄 Kunlik avtomatik backup faollashtirildi.")
    else:
        logger.warning("BACKUP_CHANNEL_ID sozlanmagan — avtomatik backup o'chirilgan.")

    logger.info("🚀 Bot muvaffaqiyatli ishga tushdi! Telegram'da /start bosing.")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        logger.info("🔄 Resurslar va bot sessiyasi yopilmoqda...")

        for task in (log_sender_task, backup_task):
            if task:
                task.cancel()

        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot faoliyati to'xtatildi.")