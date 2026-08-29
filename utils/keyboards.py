from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 O'yinni boshlash")],
            [KeyboardButton(text="🔄 Qayta tiklash")],
        ],
        resize_keyboard=True
    )