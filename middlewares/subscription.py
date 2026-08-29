import logging
from typing import Callable, Dict, Any, Awaitable, Union
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from config import ADMIN_ENTRY_COMMAND, OWNER_ENTRY_COMMAND
from database.requests import get_channels, is_admin

logger = logging.getLogger(__name__)

# Bular tekshiruvsiz har doim o'tadi
EXEMPT_COMMANDS = {"/start", "/reset", f"/{ADMIN_ENTRY_COMMAND}", f"/{OWNER_ENTRY_COMMAND}"}
EXEMPT_TEXTS = {"🔄 Qayta tiklash"}  # Favqulodda chiqish tugmasi — obuna tekshiruvidan ham ozod

EXEMPT_CALLBACK_PREFIXES = ("check_subscription", "cancel_search", "move_", "ready_")


class SubscriptionMiddleware(BaseMiddleware):
    """
    Har bir xabar/tugma bosishdan oldin foydalanuvchi majburiy kanallarga
    obuna bo'lganini tekshiradi. Adminlar bundan ozod.
    """

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user is None or user.is_bot:
            return await handler(event, data)

        if isinstance(event, Message) and event.text:
            if event.text in EXEMPT_TEXTS:
                return await handler(event, data)
            command = event.text.split()[0].split("@")[0]
            if command in EXEMPT_COMMANDS:
                return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data and event.data.startswith(EXEMPT_CALLBACK_PREFIXES):
            return await handler(event, data)

        if await is_admin(user.id):
            return await handler(event, data)

        channels = await get_channels()
        if not channels:
            return await handler(event, data)

        bot = data["bot"]
        not_subscribed = []

        for channel in channels:
            chat_ref = channel.channel_id or channel.username
            try:
                member = await bot.get_chat_member(chat_ref, user.id)
                if member.status in ("left", "kicked"):
                    not_subscribed.append(channel)
            except (TelegramBadRequest, TelegramForbiddenError):
                logger.warning(f"Kanal a'zoligini tekshirib bo'lmadi: {channel.username}")
                continue

        if not not_subscribed:
            return await handler(event, data)

        buttons = [[InlineKeyboardButton(text=f"📢 {c.title}", url=c.url)] for c in not_subscribed]
        buttons.append([InlineKeyboardButton(text="✅ Tekshirdim", callback_data="check_subscription")])
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        text = "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>"

        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup, parse_mode="HTML")
        else:
            try:
                await event.message.answer(text, reply_markup=markup, parse_mode="HTML")
            except TelegramBadRequest:
                pass
            await event.answer()

        return None