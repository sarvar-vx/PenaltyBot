import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from utils.game_logic import remove_user_from_queue, get_user_active_game, finish_and_clean_game
from utils.keyboards import get_main_reply_keyboard
from utils.friend_invite import PENDING_INVITES, remove_invite

router = Router()
logger = logging.getLogger(__name__)

RESET_BUTTON_TEXT = "🔄 Qayta tiklash"


async def force_leave_game(user_id: int, bot) -> bool:
    """
    Foydalanuvchining faol o'yinini majburiy tugatadi: raqibga xabar
    beriladi, o'yin xotiradan (ACTIVE_GAMES) o'chiriladi. Statistikaga
    yozilmaydi, chunki o'yin normal tarzda tugamagan.

    True qaytaradi, agar foydalanuvchi haqiqatan ham faol o'yinda bo'lsa.
    """
    game = get_user_active_game(user_id)
    if not game:
        return False

    opponent_id = game.p2_id if user_id == game.p1_id else game.p1_id

    try:
        await bot.send_message(
            opponent_id,
            "⚠️ Raqibingiz o'yindan chiqib ketdi. O'yin bekor qilindi.",
            reply_markup=get_main_reply_keyboard()
        )
    except TelegramAPIError:
        logger.exception(f"force_leave_game: raqibga xabar berib bo'lmadi [user_id={opponent_id}]")

    await finish_and_clean_game(game.game_id, save_to_db=False)
    return True


async def cleanup_pending_invites(user_id: int, bot) -> None:
    """
    Foydalanuvchi reset qilganda uning yuborgan yoki qabul qilishi kutilayotgan
    barcha takliflarini bekor qiladi, ikkinchi tomonga xabar beradi.
    """
    to_remove = [
        invite_id for invite_id, invite in PENDING_INVITES.items()
        if invite["inviter_id"] == user_id or invite["target_id"] == user_id
    ]

    for invite_id in to_remove:
        invite = PENDING_INVITES.get(invite_id)
        if not invite:
            continue

        if invite["timer_task"] and not invite["timer_task"].done():
            invite["timer_task"].cancel()

        other_id = invite["target_id"] if invite["inviter_id"] == user_id else invite["inviter_chat_id"]
        try:
            await bot.send_message(other_id, "⚠️ Taklif bekor qilindi.")
        except TelegramAPIError:
            pass

        remove_invite(invite_id)


@router.message(Command("reset"))
@router.message(F.text == RESET_BUTTON_TEXT)
async def reset_handler(message: Message, state: FSMContext):
    """
    Favqulodda chiqish tugmasi/buyrug'i. Bu router main.py'da eng birinchi
    ulanadi — shuning uchun foydalanuvchi qaysi holatda bo'lishidan qat'iy
    nazar (admin panelda "kutish" holatida, matchmaking navbatida, taklif
    kutayotganda, yoki faol o'yinda) ishlaydi.
    """
    user_id = message.from_user.id

    await state.clear()
    await remove_user_from_queue(user_id)
    await cleanup_pending_invites(user_id, message.bot)
    was_in_game = await force_leave_game(user_id, message.bot)

    text = "🔄 O'yiningiz bekor qilindi va holatingiz tozalandi." if was_in_game else "🔄 Holatingiz tozalandi."
    await message.answer(
        f"{text} Botdan qaytadan foydalanishingiz mumkin.",
        reply_markup=get_main_reply_keyboard()
    )