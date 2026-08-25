import logging
from typing import Callable, Dict, Any, Awaitable, Union

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from database.requests import register_user

logger = logging.getLogger(__name__)


class UserRegistrationMiddleware(BaseMiddleware):
    """
    Botga har qanday xabar yoki tugma bosish orqali murojaat qilgan har bir
    foydalanuvchini avtomatik ravishda 'users' jadvaliga yozib qo'yadi.

    Bu — faqat /start orqali ro'yxatdan o'tkazishga tayanishning oldini oladi:
    masalan bot qayta ishga tushganda, foydalanuvchida eski reply keyboard
    qolib ketishi va u /start bosmasdan to'g'ridan-to'g'ri boshqa tugmani
    bosishi mumkin.
    """

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user and not user.is_bot:
            try:
                await register_user(
                    user_id=user.id,
                    full_name=user.full_name,
                    username=user.username
                )
            except Exception:
                logger.exception(f"UserRegistrationMiddleware: foydalanuvchini saqlab bo'lmadi [user_id={user.id}]")

        return await handler(event, data)
