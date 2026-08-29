import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from utils.game_logic import remove_user_from_queue, get_user_active_game, finish_and_clean_game
from utils.keyboards import get_main_reply_keyboard

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


@router.message(Command("reset"))
@router.message(F.text == RESET_BUTTON_TEXT)
async def reset_handler(message: Message, state: FSMContext):
    """
    Favqulodda chiqish tugmasi/buyrug'i. Bu router main.py'da eng birinchi
    ulanadi — shuning uchun foydalanuvchi qaysi holatda bo'lishidan qat'iy
    nazar (admin panelda "kutish" holatida, matchmaking navbatida, yoki
    faol o'yinda) ishlaydi.
    """
    user_id = message.from_user.id

    await state.clear()
    await remove_user_from_queue(user_id)
    was_in_game = await force_leave_game(user_id, message.bot)

    text = "🔄 O'yiningiz bekor qilindi va holatingiz tozalandi." if was_in_game else "🔄 Holatingiz tozalandi."
    await message.answer(
        f"{text} Botdan qaytadan foydalanishingiz mumkin.",
        reply_markup=get_main_reply_keyboard()
    )