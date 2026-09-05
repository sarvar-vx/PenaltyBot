from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def _chunk_buttons(labels: list[str], per_row: int = 2) -> list[list[KeyboardButton]]:
    """Tugmalar ro'yxatini 'per_row' tadan qatorlarga bo'ladi, oxirgi qator to'liq bo'lmasa ham qoldiradi"""
    buttons = [KeyboardButton(text=label) for label in labels]
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    labels = ["🎮 O'yinni boshlash", "👥 Sherik bilan o'ynash", "🔄 Qayta tiklash"]
    return ReplyKeyboardMarkup(keyboard=_chunk_buttons(labels), resize_keyboard=True)