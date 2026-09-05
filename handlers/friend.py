import asyncio
import html
import logging
import uuid

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError, TelegramForbiddenError

from database.requests import get_user_by_identifier
from utils.game_logic import ACTIVE_GAMES, GameSession, is_user_in_game, is_user_in_queue
from utils.friend_invite import create_invite, get_invite, remove_invite, is_user_busy
from utils.keyboards import get_main_reply_keyboard
from handlers.game import get_shot_keyboard, start_turn_timer

router = Router()
logger = logging.getLogger(__name__)

INVITE_TIMEOUT = 60


class FriendInvite(StatesGroup):
    waiting_identifier = State()


def get_cancel_invite_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="friend_cancel_invite")]
    ])


def get_invite_response_keyboard(invite_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"friend_accept_{invite_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"friend_decline_{invite_id}"),
        ]
    ])


@router.message(F.text == "👥 Sherik bilan o'ynash")
async def friend_invite_start(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if is_user_in_game(user_id):
        await message.answer("⚠️ Siz allaqachon davom etayotgan o'yindasiz!")
        return
    if is_user_in_queue(user_id):
        await message.answer("⚠️ Siz hozir random raqib qidiryapsiz. Avval uni bekor qiling.")
        return
    if is_user_busy(user_id):
        await message.answer("⚠️ Sizda allaqachon faol taklif bor.")
        return

    await state.set_state(FriendInvite.waiting_identifier)
    await message.answer(
        "👥 Sherikning username'ini (masalan <code>@ali_valiyev</code>) yoki Telegram ID raqamini yuboring.\n\n"
        "⚠️ Sherik botga kamida bir marta <code>/start</code> bosgan bo'lishi kerak.",
        reply_markup=get_cancel_invite_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "friend_cancel_invite")
async def cancel_invite_input(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    await call.message.answer("❌ Bekor qilindi.", reply_markup=get_main_reply_keyboard())
    await call.answer()


@router.message(FriendInvite.waiting_identifier)
async def friend_invite_lookup(message: Message, state: FSMContext, bot):
    inviter_id = message.from_user.id
    inviter_name = html.escape(message.from_user.full_name or "O'yinchi")
    identifier = message.text.strip().lstrip("@")

    target = await get_user_by_identifier(identifier)

    if not target:
        await message.answer(
            "❌ Bunday foydalanuvchi topilmadi. U botga <code>/start</code> bosganiga ishonch hosil qiling.\n\n"
            "Qaytadan urinib ko'ring yoki bekor qiling:",
            reply_markup=get_cancel_invite_keyboard(),
            parse_mode="HTML"
        )
        return

    target_id = target.user_id

    if target_id == inviter_id:
        await message.answer(
            "❌ O'zingizni taklif qila olmaysiz. Boshqa foydalanuvchi kiriting:",
            reply_markup=get_cancel_invite_keyboard()
        )
        return

    if is_user_in_game(target_id) or is_user_in_queue(target_id) or is_user_busy(target_id):
        await message.answer(
            "❌ Bu foydalanuvchi hozir band (o'yinda, navbatda yoki boshqa taklifda). Keyinroq urinib ko'ring.",
            reply_markup=get_cancel_invite_keyboard()
        )
        return

    await state.clear()

    invite_id = str(uuid.uuid4())[:8]

    try:
        sent = await bot.send_message(
            target_id,
            f"⚔️ <b>{inviter_name}</b> sizni penalty o'yiniga taklif qilmoqda!\n\n"
            f"⏱️ {INVITE_TIMEOUT} soniya ichida javob bering:",
            reply_markup=get_invite_response_keyboard(invite_id),
            parse_mode="HTML"
        )
    except (TelegramForbiddenError, TelegramAPIError):
        await message.answer(
            "❌ Sherikka xabar yuborib bo'lmadi (u botni bloklagan bo'lishi mumkin).",
            reply_markup=get_main_reply_keyboard()
        )
        return

    timer_task = asyncio.create_task(invite_timeout_watcher(invite_id, bot))

    create_invite(
        invite_id=invite_id,
        inviter_id=inviter_id, inviter_name=inviter_name, inviter_chat_id=message.chat.id,
        target_id=target_id, target_name=html.escape(target.full_name or "O'yinchi"),
        target_msg_id=sent.message_id,
        timer_task=timer_task,
    )

    await message.answer(
        "✅ Taklif yuborildi! Javobni kutamiz...",
        reply_markup=get_main_reply_keyboard()
    )


async def invite_timeout_watcher(invite_id: str, bot):
    try:
        await asyncio.sleep(INVITE_TIMEOUT)
        invite = get_invite(invite_id)
        if not invite:
            return

        remove_invite(invite_id)

        try:
            await bot.edit_message_reply_markup(
                chat_id=invite["target_id"], message_id=invite["target_msg_id"], reply_markup=None
            )
        except TelegramBadRequest:
            pass

        try:
            await bot.send_message(invite["target_id"], "⏱️ Taklif muddati tugadi.")
        except TelegramAPIError:
            pass
        try:
            await bot.send_message(invite["inviter_chat_id"], "⏱️ Sherikingiz javob bermadi, taklif bekor qilindi.")
        except TelegramAPIError:
            pass
    except asyncio.CancelledError:
        pass


@router.callback_query(F.data.startswith("friend_accept_"))
async def friend_accept(call: CallbackQuery):
    invite_id = call.data.split("_", 2)[2]
    invite = get_invite(invite_id)

    if not invite or call.from_user.id != invite["target_id"]:
        await call.answer("Bu taklif allaqachon eskirgan.", show_alert=True)
        return

    if invite["timer_task"] and not invite["timer_task"].done():
        invite["timer_task"].cancel()
    remove_invite(invite_id)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    inviter_id = invite["inviter_id"]
    inviter_chat_id = invite["inviter_chat_id"]
    inviter_name = invite["inviter_name"]
    target_id = invite["target_id"]
    target_name = invite["target_name"]

    if is_user_in_game(inviter_id):
        await call.answer("Taklif qilgan odam allaqachon boshqa o'yinda!", show_alert=True)
        return

    game_id = str(uuid.uuid4())[:8]
    game = GameSession(
        game_id=game_id,
        p1_id=inviter_id, p2_id=target_id,
        p1_name=inviter_name, p2_name=target_name,
        kicker_id=inviter_id, keeper_id=target_id,
        kicker_name=inviter_name, keeper_name=target_name,
    )
    ACTIVE_GAMES[game_id] = game

    try:
        m1 = await call.bot.send_message(
            inviter_chat_id,
            f"⚔️ <b>MATCH BOSHLANDI!</b>\n\n🔥 <b>{inviter_name}</b> vs <b>{target_name}</b>\n\n🎯 <b>Siz Hujumchisiz!</b> (5 soniya)",
            reply_markup=get_shot_keyboard(game_id, "kicker"),
            parse_mode="HTML"
        )
        m2 = await call.message.answer(
            f"⚔️ <b>MATCH BOSHLANDI!</b>\n\n🔥 <b>{inviter_name}</b> vs <b>{target_name}</b>\n\n🧤 <b>Siz Darvozabonsiz!</b> (5 soniya)",
            reply_markup=get_shot_keyboard(game_id, "keeper"),
            parse_mode="HTML"
        )
        game.p1_msg_id, game.p2_msg_id = m1.message_id, m2.message_id
        game.timer_task = asyncio.create_task(start_turn_timer(game, call.bot))
    except TelegramAPIError:
        logger.exception(f"Friend match start error [game_id={game_id}]")
        ACTIVE_GAMES.pop(game_id, None)
        await call.answer("Match boshlashda xatolik yuz berdi.", show_alert=True)
        return

    await call.answer("Taklif qabul qilindi!")


@router.callback_query(F.data.startswith("friend_decline_"))
async def friend_decline(call: CallbackQuery):
    invite_id = call.data.split("_", 2)[2]
    invite = get_invite(invite_id)

    if not invite or call.from_user.id != invite["target_id"]:
        await call.answer("Bu taklif allaqachon eskirgan.", show_alert=True)
        return

    if invite["timer_task"] and not invite["timer_task"].done():
        invite["timer_task"].cancel()
    remove_invite(invite_id)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    await call.answer("Taklif rad etildi.")

    try:
        await call.bot.send_message(invite["inviter_chat_id"], f"❌ {invite['target_name']} taklifni rad etdi.")
    except TelegramAPIError:
        pass