import uuid
import asyncio
import html
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError, TelegramForbiddenError

from database.requests import get_channels
from utils.game_logic import (
    MATCHMAKING_QUEUE, ACTIVE_GAMES, GameSession, QUEUE_LOCK,
    is_user_in_game, is_user_in_queue, remove_user_from_queue
)
from utils.keyboards import get_main_reply_keyboard
from handlers.game import get_shot_keyboard, start_turn_timer

router = Router()
logger = logging.getLogger(__name__)


def get_cancel_queue_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Qidiruvni bekor qilish", callback_data="cancel_search")]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "⚽️ <b>eFootballLIVE Penaltilar Seriyasi</b>\n\nO'yinni boshlash uchun pastdagi tugmani bosing 👇",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "check_subscription")
async def check_subscription_handler(call: CallbackQuery):
    """Foydalanuvchi 'Tekshirdim' tugmasini bosganda majburiy obunani qayta tekshiradi"""
    channels = await get_channels()
    not_subscribed = []

    for channel in channels:
        chat_ref = channel.channel_id or channel.username
        try:
            member = await call.bot.get_chat_member(chat_ref, call.from_user.id)
            if member.status in ("left", "kicked"):
                not_subscribed.append(channel)
        except (TelegramBadRequest, TelegramForbiddenError):
            continue

    if not_subscribed:
        await call.answer("❌ Siz hali barcha kanallarga obuna bo'lmagansiz!", show_alert=True)
        return

    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass

    await call.message.answer(
        "✅ Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin.",
        reply_markup=get_main_reply_keyboard()
    )


@router.message(F.text == "🎮 O'yinni boshlash")
async def start_matchmaking(message: Message):
    user_id = message.from_user.id
    user_name = html.escape(message.from_user.full_name or "O'yinchi")

    if is_user_in_game(user_id):
        await message.answer("⚠️ Siz allaqachon davom etayotgan o'yindasiz!")
        return

    matched_pair = None
    async with QUEUE_LOCK:
        if is_user_in_queue(user_id):
            await message.answer("⏳ Siz allaqachon navbatdasiz! Yuqoridagi xabardagi tugmadan bekor qilishingiz mumkin.")
            return

        MATCHMAKING_QUEUE.append({"id": user_id, "name": user_name, "chat_id": message.chat.id})

        if len(MATCHMAKING_QUEUE) >= 2:
            p1 = MATCHMAKING_QUEUE.pop(0)
            p2 = MATCHMAKING_QUEUE.pop(0)

            if p1["id"] == p2["id"]:
                logger.warning(f"Self-match urinishi bloklandi: user_id={p1['id']}")
                MATCHMAKING_QUEUE.append(p1)
                return  # Xabar yubormaymiz — foydalanuvchida allaqachon "qidirilmoqda" xabari va tugmasi bor

            game_id = str(uuid.uuid4())[:8]
            game = GameSession(
                game_id=game_id,
                p1_id=p1["id"], p2_id=p2["id"],
                p1_name=p1["name"], p2_name=p2["name"],
                kicker_id=p1["id"], keeper_id=p2["id"],
                kicker_name=p1["name"], keeper_name=p2["name"]
            )
            ACTIVE_GAMES[game_id] = game
            matched_pair = (p1, p2, game)

    if matched_pair is None:
        await message.answer(
            "🔍 <b>Raqib qidirilmoqda...</b>",
            reply_markup=get_cancel_queue_keyboard(),
            parse_mode="HTML"
        )
        return

    p1, p2, game = matched_pair
    try:
        await message.bot.send_message(p1["chat_id"], "🎮 Match topildi! O'yin yuklanmoqda...", reply_markup=ReplyKeyboardRemove())
        await message.bot.send_message(p2["chat_id"], "🎮 Match topildi! O'yin yuklanmoqda...", reply_markup=ReplyKeyboardRemove())

        m1 = await message.bot.send_message(
            chat_id=p1["chat_id"],
            text=f"⚔️ <b>MATCH BOSHLANDI!</b>\n\n🔥 <b>{p1['name']}</b> vs <b>{p2['name']}</b>\n\n🎯 <b>Siz Hujumchisiz!</b> (5 soniya)",
            reply_markup=get_shot_keyboard(game.game_id, "kicker"),
            parse_mode="HTML"
        )
        m2 = await message.bot.send_message(
            chat_id=p2["chat_id"],
            text=f"⚔️ <b>MATCH BOSHLANDI!</b>\n\n🔥 <b>{p1['name']}</b> vs <b>{p2['name']}</b>\n\n🧤 <b>Siz Darvozabonsiz!</b> (5 soniya)",
            reply_markup=get_shot_keyboard(game.game_id, "keeper"),
            parse_mode="HTML"
        )

        game.p1_msg_id, game.p2_msg_id = m1.message_id, m2.message_id
        game.timer_task = asyncio.create_task(start_turn_timer(game, message.bot))

    except TelegramAPIError:
        logger.exception(f"Match start error [game_id={game.game_id}]")
        ACTIVE_GAMES.pop(game.game_id, None)

        for chat_id in (p1["chat_id"], p2["chat_id"]):
            try:
                await message.bot.send_message(
                    chat_id,
                    "⚠️ Match boshlashda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
                    reply_markup=get_main_reply_keyboard()
                )
            except TelegramAPIError:
                pass


@router.callback_query(F.data == "cancel_search")
async def cancel_search_handler(call: CallbackQuery):
    user_id = call.from_user.id
    removed = await remove_user_from_queue(user_id)

    if removed:
        try:
            await call.message.delete()
        except TelegramBadRequest:
            pass

        await call.message.answer(
            "❌ Qidiruv bekor qilindi.",
            reply_markup=get_main_reply_keyboard()
        )
    else:
        # Bu holat endi kamroq uchraydi, lekin baribir xavfsizlik uchun
        # qoldiramiz: agar match allaqachon topilgan bo'lsa, foydalanuvchi
        # shuni bilishi kerak.
        await call.answer("Siz allaqachon navbatda emassiz yoki match boshlanib bo'lgan!", show_alert=True)
        try:
            await call.message.delete()
        except TelegramBadRequest:
            pass