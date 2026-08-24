import asyncio
import logging
from utils.backup import send_backup

from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import ADMIN_ENTRY_COMMAND, OWNER_ENTRY_COMMAND
from database.requests import (
    get_admin, is_owner, add_admin, remove_admin, get_all_admins,
    get_channels, add_channel, remove_channel_by_id, get_bot_stats, get_all_user_ids
)
from handlers.start import get_main_reply_keyboard

router = Router()
logger = logging.getLogger(__name__)


class AdminPanel(StatesGroup):
    menu = State()
    waiting_channel_username = State()
    waiting_broadcast_message = State()
    waiting_new_admin_id = State()


# ==================== KLAVIATURALAR ====================

def _chunk_buttons(labels: list[str], per_row: int = 2) -> list[list[KeyboardButton]]:
    """Tugmalar ro'yxatini 'per_row' tadan qatorlarga bo'ladi, oxirgi qator to'liq bo'lmasa ham qoldiradi"""
    buttons = [KeyboardButton(text=label) for label in labels]
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def get_moderator_menu() -> ReplyKeyboardMarkup:
    labels = ["📊 Statistika", "📺 Kanallar", "📢 Xabar yuborish", "🚪 Chiqish"]
    return ReplyKeyboardMarkup(keyboard=_chunk_buttons(labels), resize_keyboard=True)


def get_owner_menu() -> ReplyKeyboardMarkup:
    labels = ["📊 Statistika", "📺 Kanallar", "📢 Xabar yuborish", "👑 Adminlar", "🚪 Chiqish"]
    return ReplyKeyboardMarkup(keyboard=_chunk_buttons(labels), resize_keyboard=True)


def menu_for_role(role: str) -> ReplyKeyboardMarkup:
    return get_owner_menu() if role == "owner" else get_moderator_menu()


def get_cancel_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_cancel")]
    ])


# ==================== KIRISH ====================

@router.message(Command(ADMIN_ENTRY_COMMAND))
async def moderator_entry(message: Message, state: FSMContext):
    admin = await get_admin(message.from_user.id)
    if not admin:
        return  # Oddiy foydalanuvchi uchun bu buyruq "ko'rinmas" — hech narsa aytmaymiz

    await state.set_state(AdminPanel.menu)
    await state.update_data(role=admin.role)

    await message.answer(
        f"👋 Xush kelibsiz, <b>{admin.role.upper()}</b> panelga!",
        reply_markup=menu_for_role(admin.role),
        parse_mode="HTML"
    )


@router.message(Command(OWNER_ENTRY_COMMAND))
async def owner_entry(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return  # Sirni oshkor qilmaslik uchun hech qanday javob yo'q

    await state.set_state(AdminPanel.menu)
    await state.update_data(role="owner")

    await message.answer(
        "👑 <b>Owner panelga xush kelibsiz!</b>",
        reply_markup=get_owner_menu(),
        parse_mode="HTML"
    )


@router.message(StateFilter(AdminPanel), F.text == "🚪 Chiqish")
async def exit_admin_panel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Admin panelidan chiqdingiz.", reply_markup=get_main_reply_keyboard())


@router.callback_query(F.data == "admin_cancel")
async def admin_cancel(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminPanel.menu)
    data = await state.get_data()
    role = data.get("role", "moderator")

    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass

    await call.message.answer("Bekor qilindi.", reply_markup=menu_for_role(role))
    await call.answer()


# ==================== BACKUP ====================

@router.message(Command("backup"))
async def manual_backup(message: Message, bot: Bot):
    if not await is_owner(message.from_user.id):
        return

    await message.answer("⏳ Backup tayyorlanmoqda...")
    await send_backup(bot)
    await message.answer("✅ Backup jarayoni yakunlandi (kanalga qarang).")


# ==================== STATISTIKA ====================

@router.message(StateFilter(AdminPanel.menu), F.text == "📊 Statistika")
async def show_stats(message: Message):
    stats = await get_bot_stats()
    await message.answer(
        f"📊 <b>Bot statistikasi:</b>\n\n"
        f"👤 Foydalanuvchilar: <b>{stats['users_count']}</b>\n"
        f"⚽️ O'ynalgan o'yinlar: <b>{stats['games_count']}</b>\n"
        f"📺 Majburiy kanallar: <b>{stats['channels_count']}</b>",
        parse_mode="HTML"
    )


# ==================== KANALLAR ====================

def build_channels_view(channels) -> tuple[str, InlineKeyboardMarkup]:
    buttons = [
        [InlineKeyboardButton(text=f"❌ {c.title}", callback_data=f"admin_del_channel_{c.id}")]
        for c in channels
    ]
    buttons.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="admin_add_channel")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = "📺 <b>Majburiy obuna kanallari:</b>\n\nO'chirish uchun kanalga bosing." if channels \
        else "📺 Hozircha majburiy kanal qo'shilmagan."

    return text, markup


@router.message(StateFilter(AdminPanel.menu), F.text == "📺 Kanallar")
async def show_channels(message: Message):
    channels = await get_channels()
    text, markup = build_channels_view(channels)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(StateFilter(AdminPanel.menu), F.data == "admin_add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminPanel.waiting_channel_username)
    await call.message.answer(
        "📺 Kanalning username'ini yuboring (masalan: <code>@mychannel</code>).\n\n"
        "⚠️ Botni o'sha kanalga <b>admin</b> qilib qo'shganingizga ishonch hosil qiling, "
        "aks holda obunani tekshira olmaydi.",
        reply_markup=get_cancel_inline(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(StateFilter(AdminPanel.waiting_channel_username))
async def add_channel_finish(message: Message, state: FSMContext, bot: Bot):
    username = message.text.strip()
    if not username.startswith("@"):
        username = f"@{username}"

    try:
        chat = await bot.get_chat(username)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        await message.answer(
            f"❌ Kanalni topib bo'lmadi yoki bot u yerda admin emas.\n\nQaytadan urinib ko'ring:",
            reply_markup=get_cancel_inline()
        )
        return

    url = f"https://t.me/{username.lstrip('@')}"
    await add_channel(username=username, title=chat.title, url=url, channel_id=chat.id)

    await state.set_state(AdminPanel.menu)
    data = await state.get_data()
    role = data.get("role", "moderator")

    await message.answer(
        f"✅ Kanal qo'shildi: <b>{chat.title}</b>",
        reply_markup=menu_for_role(role),
        parse_mode="HTML"
    )


@router.callback_query(StateFilter(AdminPanel.menu), F.data.startswith("admin_del_channel_"))
async def delete_channel_handler(call: CallbackQuery):
    channel_pk = int(call.data.split("_")[-1])
    removed = await remove_channel_by_id(channel_pk)

    await call.answer("✅ Kanal o'chirildi" if removed else "❌ Kanal topilmadi", show_alert=not removed)

    channels = await get_channels()
    text, markup = build_channels_view(channels)
    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest:
        pass


# ==================== XABAR YUBORISH (BROADCAST) ====================

@router.message(StateFilter(AdminPanel.menu), F.text == "📢 Xabar yuborish")
async def broadcast_start(message: Message, state: FSMContext):
    await state.set_state(AdminPanel.waiting_broadcast_message)
    await message.answer(
        "📢 Yubormoqchi bo'lgan xabaringizni shu yerga tashlang (matn, rasm, video — farqi yo'q). "
        "U aynan shu holicha barcha foydalanuvchilarga ko'chirib yuboriladi:",
        reply_markup=get_cancel_inline()
    )


@router.message(StateFilter(AdminPanel.waiting_broadcast_message))
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    user_ids = await get_all_user_ids()

    await message.answer(f"⏳ Yuborilmoqda... ({len(user_ids)} foydalanuvchiga)")

    success, failed = 0, 0
    for uid in user_ids:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success += 1
        except (TelegramBadRequest, TelegramForbiddenError):
            failed += 1
        except Exception:
            logger.exception(f"Broadcast xatosi [user_id={uid}]")
            failed += 1

        await asyncio.sleep(0.05)  # Telegram flood limitidan qochish uchun

    await state.set_state(AdminPanel.menu)
    data = await state.get_data()
    role = data.get("role", "moderator")

    await message.answer(
        f"✅ Xabar yuborildi!\n\n✔️ Muvaffaqiyatli: {success}\n❌ Yuborilmadi: {failed}",
        reply_markup=menu_for_role(role)
    )


# ==================== ADMINLAR (FAQAT OWNER) ====================

@router.message(StateFilter(AdminPanel.menu), F.text == "👑 Adminlar")
async def show_admins(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("role") != "owner":
        return  # Moderator bu tugmani ko'rmaydi ham, lekin himoya sifatida qoldiramiz

    admins = await get_all_admins()
    lines = [f"• <code>{a.user_id}</code> — {a.role}" for a in admins]
    text = "👑 <b>Adminlar ro'yxati:</b>\n\n" + "\n".join(lines)

    buttons = [[InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="admin_add_admin")]]
    for a in admins:
        if a.role != "owner":  # Owner'ni shu paneldan o'chirib bo'lmaydi
            buttons.append([InlineKeyboardButton(
                text=f"➖ {a.user_id} ni o'chirish", callback_data=f"admin_del_admin_{a.user_id}"
            )])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(StateFilter(AdminPanel.menu), F.data == "admin_add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("role") != "owner":
        await call.answer("Sizda bu huquq yo'q!", show_alert=True)
        return

    await state.set_state(AdminPanel.waiting_new_admin_id)
    await call.message.answer(
        "➕ Yangi moderatorning Telegram ID raqamini yuboring:\n"
        "(ID'ni bilish uchun foydalanuvchi @userinfobot ga /start bosishi mumkin)",
        reply_markup=get_cancel_inline()
    )
    await call.answer()


@router.message(StateFilter(AdminPanel.waiting_new_admin_id))
async def add_admin_finish(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ Faqat raqam yuboring. Qaytadan urinib ko'ring:", reply_markup=get_cancel_inline())
        return

    new_admin_id = int(message.text.strip())
    added = await add_admin(user_id=new_admin_id, role="moderator")

    await state.set_state(AdminPanel.menu)

    if added:
        await message.answer(
            f"✅ <code>{new_admin_id}</code> moderator qilib qo'shildi.\n\n"
            f"Endi u <code>/{ADMIN_ENTRY_COMMAND}</code> buyrug'i orqali panelga kira oladi.",
            reply_markup=get_owner_menu(), parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ Bu foydalanuvchi allaqachon admin.", reply_markup=get_owner_menu())


@router.callback_query(StateFilter(AdminPanel.menu), F.data.startswith("admin_del_admin_"))
async def delete_admin_handler(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("role") != "owner":
        await call.answer("Sizda bu huquq yo'q!", show_alert=True)
        return

    target_id = int(call.data.split("_")[-1])
    removed = await remove_admin(target_id)

    await call.answer("✅ Admin o'chirildi" if removed else "❌ Topilmadi", show_alert=not removed)

    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass