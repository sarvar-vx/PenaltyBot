import asyncio
import html
import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

from config import VIDEO_CHANNEL_ID
from utils.game_logic import ACTIVE_GAMES, GameSession, finish_and_clean_game
from utils.video_clips import get_result_message_id

router = Router()
logger = logging.getLogger(__name__)

TURN_TIMEOUT = 5      # Zarba/sakrash uchun vaqt (soniya)
READY_TIMEOUT = 20    # Keyingi raundga tayyorlik uchun vaqt (soniya)


def get_shot_keyboard(game_id: str, role: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Chap", callback_data=f"move_{game_id}_{role}_left"),
            InlineKeyboardButton(text="⬆️ Markaz", callback_data=f"move_{game_id}_{role}_center"),
            InlineKeyboardButton(text="➡️ O'ng", callback_data=f"move_{game_id}_{role}_right")
        ]
    ])


def get_ready_keyboard(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Keyingi raundga tayyorman", callback_data=f"ready_{game_id}")]
    ])


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎮 O'yinni boshlash")]], resize_keyboard=True)


def build_scoreboard(game: GameSession) -> str:
    total_shots_per_player = max(5, game.max_rounds // 2)

    p1_shots = " ".join(game.p1_score) + " " + " ".join(["⏳"] * max(0, total_shots_per_player - len(game.p1_score)))
    p2_shots = " ".join(game.p2_score) + " " + " ".join(["⏳"] * max(0, total_shots_per_player - len(game.p2_score)))

    p1_name = html.escape(game.p1_name)
    p2_name = html.escape(game.p2_name)

    return (
        f"📊 <b>HISOB TABLOSI:</b>\n"
        f"👤 <b>{p1_name}:</b> {p1_shots}\n"
        f"👤 <b>{p2_name}:</b> {p2_shots}"
    )


async def safe_edit_text(bot, chat_id: int, message_id: int, text: str, reply_markup=None):
    """Telegram API xatolarini xavfsiz ushlab qoluvchi yordamchi funksiya"""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.warning(f"Edit message error [Chat: {chat_id}]: {e}")
    except Exception:
        logger.exception(f"Kutilmagan xatolik [Chat: {chat_id}]")


async def send_result_media(bot, chat_id: int, source_message_id: int | None, caption: str):
    """
    Natijani video (yopiq kanaldan copy_message orqali) yoki oddiy matn
    sifatida yuboradi. source_message_id — kanaldagi video xabarining ID'si.
    """
    try:
        if source_message_id:
            await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=VIDEO_CHANNEL_ID,
                message_id=source_message_id,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(chat_id, caption, parse_mode="HTML")
    except TelegramAPIError:
        logger.exception(f"Result media send error [Chat: {chat_id}]")


async def start_turn_timer(game: GameSession, bot):
    """Joriy bosqich (zarba yoki tayyorlik) uchun vaqt nazorati"""
    phase = game.game_phase
    timeout = TURN_TIMEOUT if phase == "move" else READY_TIMEOUT

    try:
        await asyncio.sleep(timeout)

        if phase == "move":
            if not game.kicker_choice:
                game.kicker_choice = "timeout"
            if not game.keeper_choice:
                game.keeper_choice = "timeout"
            await process_round_result(game, bot)

        elif phase == "ready":
            await handle_ready_timeout(game, bot)

    except asyncio.CancelledError:
        pass


async def end_game(game: GameSession, bot, save_to_db: bool, winner_id: int = None):
    """O'yinni yakunlab, ikkala o'yinchiga bosh menyuni yuborish (natija allaqachon video/matn orqali yuborilgan)"""
    for chat_id in (game.p1_id, game.p2_id):
        try:
            await bot.send_message(
                chat_id,
                "Yangi o'yin boshlash uchun tugmani bosing:",
                reply_markup=get_main_reply_keyboard()
            )
        except TelegramAPIError:
            logger.exception(f"Send final msg error [game_id={game.game_id}, chat_id={chat_id}]")

    await finish_and_clean_game(game.game_id, save_to_db=save_to_db, winner_id=winner_id)


async def handle_ready_timeout(game: GameSession, bot):
    """Raqib(lar) 'tayyorman' tugmasini bosishga ulgurmasa chaqiriladi"""
    if game.is_processing:
        return
    if game.p1_ready and game.p2_ready:
        return

    game.is_processing = True
    try:
        scoreboard_txt = build_scoreboard(game)

        if game.p1_ready and not game.p2_ready:
            winner_id = game.p1_id
            result_text = (
                f"🏁 <b>O'YIN YAKUNLANDI!</b>\n\n⏱️ Raqib vaqtida javob bermadi.\n"
                f"🏆 <b>G'OLIB: {html.escape(game.p1_name)}!</b>\n\n{scoreboard_txt}"
            )
        elif game.p2_ready and not game.p1_ready:
            winner_id = game.p2_id
            result_text = (
                f"🏁 <b>O'YIN YAKUNLANDI!</b>\n\n⏱️ Raqib vaqtida javob bermadi.\n"
                f"🏆 <b>G'OLIB: {html.escape(game.p2_name)}!</b>\n\n{scoreboard_txt}"
            )
        else:
            winner_id = None
            result_text = (
                f"🏁 <b>O'YIN BEKOR QILINDI!</b>\n\n⏱️ Ikkala o'yinchi ham vaqtida javob bermadi.\n\n{scoreboard_txt}"
            )

        for chat_id in (game.p1_id, game.p2_id):
            await send_result_media(bot, chat_id, None, result_text)

        save = game.p1_ready or game.p2_ready
        await end_game(game, bot, save_to_db=save, winner_id=winner_id)
    finally:
        game.is_processing = False


@router.callback_query(F.data.startswith("ready_"))
async def handle_ready(call: CallbackQuery):
    game_id = call.data.split("_")[1]
    game = ACTIVE_GAMES.get(game_id)
    if not game:
        await call.answer("O'yin allaqachon yakunlangan!", show_alert=True)
        return

    user_id = call.from_user.id

    if user_id == game.p1_id:
        game.p1_ready = True
    elif user_id == game.p2_id:
        game.p2_ready = True

    await call.answer("Tayyorgarlik qabul qilindi! Raqib kutilmoqda...")

    if game.p1_ready and game.p2_ready and not game.is_processing:
        game.is_processing = True
        game.p1_ready, game.p2_ready = False, False
        game.kicker_choice, game.keeper_choice = None, None
        game.game_phase = "move"

        p1_role = "kicker" if game.p1_id == game.kicker_id else "keeper"
        p2_role = "kicker" if game.p2_id == game.kicker_id else "keeper"

        await safe_edit_text(
            call.bot, game.p1_id, game.p1_msg_id,
            text=f"🔄 <b>{game.current_round}-Raund!</b>\nSiz: <b>{'🎯 Hujumchisiz' if p1_role == 'kicker' else '🧤 Darvozabonsiz'}</b>\n⏱️ <b>5 soniya!</b>",
            reply_markup=get_shot_keyboard(game.game_id, p1_role)
        )
        await safe_edit_text(
            call.bot, game.p2_id, game.p2_msg_id,
            text=f"🔄 <b>{game.current_round}-Raund!</b>\nSiz: <b>{'🎯 Hujumchisiz' if p2_role == 'kicker' else '🧤 Darvozabonsiz'}</b>\n⏱️ <b>5 soniya!</b>",
            reply_markup=get_shot_keyboard(game.game_id, p2_role)
        )

        game.is_processing = False

        if game.timer_task and not game.timer_task.done():
            game.timer_task.cancel()
        game.timer_task = asyncio.create_task(start_turn_timer(game, call.bot))


@router.callback_query(F.data.startswith("move_"))
async def handle_move(call: CallbackQuery):
    _, game_id, role, direction = call.data.split("_")
    game = ACTIVE_GAMES.get(game_id)
    if not game:
        await call.answer("O'yin topilmadi yoki yakunlangan!", show_alert=True)
        return

    user_id = call.from_user.id

    if role == "kicker" and user_id == game.kicker_id and not game.kicker_choice:
        game.kicker_choice = direction
        await call.answer("Zarba berildi! ⚽️")
    elif role == "keeper" and user_id == game.keeper_id and not game.keeper_choice:
        game.keeper_choice = direction
        await call.answer("Sakrash belgilandi! 🧤")
    else:
        await call.answer("Tanlov allaqachon qabul qilingan!", show_alert=True)
        return

    if game.kicker_choice and game.keeper_choice:
        if game.timer_task and not game.timer_task.done():
            game.timer_task.cancel()
        await process_round_result(game, call.bot)


async def process_round_result(game: GameSession, bot):
    if game.is_processing:
        return
    game.is_processing = True

    try:
        k_choice, g_choice = game.kicker_choice, game.keeper_choice

        is_goal = (k_choice != "timeout") and (k_choice != g_choice)
        icon = "✅" if is_goal else "❌"

        if game.kicker_id == game.p1_id:
            game.p1_score.append(icon)
        else:
            game.p2_score.append(icon)

        kicker_name = html.escape(game.kicker_name)
        keeper_name = html.escape(game.keeper_name)

        if k_choice == "timeout" and g_choice == "timeout":
            res_txt = "⏱️ <b>Ikkala o'yinchi ham ulgurmadi!</b>"
        elif k_choice == "timeout":
            res_txt = f"⏱️ <b>{kicker_name} zarba berishga ulgurmadi!</b>"
        elif is_goal:
            res_txt = f"⚽️ <b>GOOOOL!</b> ({kicker_name})"
        else:
            res_txt = f"🧤 <b>SEYVV!</b> ({keeper_name} to'pni qaytardi)"

        scoreboard_txt = build_scoreboard(game)

        p1_goals = game.p1_score.count("✅")
        p2_goals = game.p2_score.count("✅")
        p1_shots_taken = len(game.p1_score)
        p2_shots_taken = len(game.p2_score)

        game_over = False
        winner_txt = ""
        winner_id = None

        if game.current_round <= 10:
            p1_shots_left = 5 - p1_shots_taken
            p2_shots_left = 5 - p2_shots_taken

            if p1_goals > p2_goals + p2_shots_left:
                game_over = True
                winner_id = game.p1_id
                winner_txt = f"\n🏆 <b>G'OLIB: {html.escape(game.p1_name)}!</b>"
            elif p2_goals > p1_goals + p1_shots_left:
                game_over = True
                winner_id = game.p2_id
                winner_txt = f"\n🏆 <b>G'OLIB: {html.escape(game.p2_name)}!</b>"
        else:
            if p1_shots_taken == p2_shots_taken:
                if p1_goals > p2_goals:
                    game_over = True
                    winner_id = game.p1_id
                    winner_txt = f"\n🏆 <b>G'OLIB: {html.escape(game.p1_name)}! (Sudden Death)</b>"
                elif p2_goals > p1_goals:
                    game_over = True
                    winner_id = game.p2_id
                    winner_txt = f"\n🏆 <b>G'OLIB: {html.escape(game.p2_name)}! (Sudden Death)</b>"

        if game_over:
            caption = f"🏁 <b>O'YIN YAKUNLANDI!</b>{winner_txt}\n\n{res_txt}\n\n{scoreboard_txt}"
        else:
            caption = f"{res_txt}\n\n{scoreboard_txt}"

        source_msg_id = get_result_message_id(k_choice, g_choice)
        for chat_id in (game.p1_id, game.p2_id):
            await send_result_media(bot, chat_id, source_msg_id, caption)

        if not game_over:
            game.current_round += 1

            if game.current_round > game.max_rounds:
                game.max_rounds += 2

            game.kicker_id, game.keeper_id = game.keeper_id, game.kicker_id
            game.kicker_name, game.keeper_name = game.keeper_name, game.kicker_name
            game.game_phase = "ready"

            sudden_death_info = "\n🔥 <b>SUDDEN DEATH! (Birinchi xatogacha)</b>" if game.current_round > 10 else ""
            ready_text = f"{sudden_death_info}\n\nKeyingi raund uchun tugmani bosing 👇"

            for attr_chat, attr_msg in (("p1_id", "p1_msg_id"), ("p2_id", "p2_msg_id")):
                chat_id = getattr(game, attr_chat)
                try:
                    msg = await bot.send_message(
                        chat_id, ready_text, reply_markup=get_ready_keyboard(game.game_id)
                    )
                    setattr(game, attr_msg, msg.message_id)
                except TelegramAPIError:
                    logger.exception(f"Ready prompt send error [game_id={game.game_id}, chat_id={chat_id}]")

            game.is_processing = False

            if game.timer_task and not game.timer_task.done():
                game.timer_task.cancel()
            game.timer_task = asyncio.create_task(start_turn_timer(game, bot))
        else:
            await end_game(game, bot, save_to_db=True, winner_id=winner_id)

    except Exception:
        logger.exception(f"Process round result error [game_id={game.game_id}]")
        game.is_processing = False