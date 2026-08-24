"""
Barcha loglarni Telegram kanaliga real vaqtda (guruhlab) yuboradigan handler.

Nega guruhlab (batch) yuboriladi: agar har bir log qatori alohida xabar
sifatida yuborilsa, faol o'yin paytida soniyasiga bir nechta xabar ketishi
mumkin — bu Telegram flood-limitiga tez uchraydi. Shuning uchun loglar
xotirada to'planib, har 4 soniyada bittalab xabar sifatida yuboriladi.
"""
import asyncio
import html
import logging
from collections import deque

from aiogram import Bot

TELEGRAM_MSG_LIMIT = 3500  # Telegram 4096 belgigacha ruxsat beradi, biroz zaxira qoldiramiz
FLUSH_INTERVAL = 4.0       # Necha soniyada bir marta yuborish


class TelegramLogHandler(logging.Handler):
    """Log yozuvlarini xotirada to'playdi, o'zi hech qanday tarmoq so'rovi qilmaydi."""

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self._buffer: deque[str] = deque()

    def emit(self, record: logging.LogRecord):
        try:
            self._buffer.append(self.format(record))
        except Exception:
            pass  # Handler o'zi hech qachon botni yiqitmasligi kerak

    def pop_all(self) -> list[str]:
        messages = list(self._buffer)
        self._buffer.clear()
        return messages


def _chunk_text(text: str, limit: int) -> list[str]:
    """Uzun matnni Telegram limitiga sig'adigan bo'laklarga bo'ladi"""
    return [text[i:i + limit] for i in range(0, len(text), limit)]


async def telegram_log_sender(bot: Bot, channel_id: int, handler: TelegramLogHandler):
    """
    Fonda ishlaydigan cheksiz sikl: har FLUSH_INTERVAL soniyada to'plangan
    loglarni bitta (yoki bir nechta, agar juda uzun bo'lsa) xabar sifatida yuboradi.
    """
    while True:
        await asyncio.sleep(FLUSH_INTERVAL)
        messages = handler.pop_all()
        if not messages:
            continue

        full_text = "\n".join(messages)
        for chunk in _chunk_text(full_text, TELEGRAM_MSG_LIMIT):
            try:
                await bot.send_message(
                    channel_id,
                    f"<pre>{html.escape(chunk)}</pre>",
                    parse_mode="HTML"
                )
            except Exception as e:
                # Muhim: bu yerda logger.error() ishlatmaymiz — aks holda
                # xato logi yana shu handler orqali qayta yuborilishga
                # urinib, cheksiz halqaga aylanishi mumkin.
                print(f"[TelegramLogHandler] Kanalga yuborib bo'lmadi: {e}")
            await asyncio.sleep(1.2)  # Flood-limitdan qochish uchun bo'laklar orasida kutish