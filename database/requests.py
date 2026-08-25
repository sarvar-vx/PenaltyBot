import logging

from sqlalchemy import select, delete, or_, func, case
from sqlalchemy.exc import IntegrityError

from database.engine import async_session
from database.models import User, GameStat, Channel, Admin

logger = logging.getLogger(__name__)


# ==================== FOYDALANUVCHILAR ====================

async def register_user(user_id: int, full_name: str, username: str = None):
    """Foydalanuvchini ro'yxatdan o'tkazadi yoki ma'lumotlarini yangilaydi (Upsert)"""
    async with async_session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            user.full_name = full_name
            user.username = username
        else:
            user = User(user_id=user_id, full_name=full_name, username=username)
            session.add(user)

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                existing.full_name = full_name
                existing.username = username
                await session.commit()


# ==================== O'YIN STATISTIKASI ====================

async def update_game_stats(
    p1_id: int, p2_id: int, p1_goals: int, p2_goals: int, winner_id: int,
    p1_name: str = "O'yinchi", p2_name: str = "O'yinchi"
):
    """
    O'yin natijasini bazaga saqlaydi va users jadvalidagi wins/losses/total_games
    ustunlarini yangilaydi.

    Xavfsizlik: agar biror sababdan foydalanuvchi 'users' jadvalida topilmasa,
    FOREIGN KEY xatosiga yo'l qo'ymaslik uchun uni shu yerning o'zida
    avtomatik yaratib qo'yamiz.
    """
    async with async_session() as session:
        stmt = select(User).where(User.user_id.in_([p1_id, p2_id]))
        result = await session.execute(stmt)
        users = {u.user_id: u for u in result.scalars().all()}

        for uid, name in ((p1_id, p1_name), (p2_id, p2_name)):
            if uid not in users:
                logger.warning(f"update_game_stats: user {uid} 'users' jadvalida yo'q edi, avtomatik yaratildi")
                new_user = User(user_id=uid, full_name=name)
                session.add(new_user)
                users[uid] = new_user

        game_record = GameStat(
            p1_id=p1_id, p2_id=p2_id,
            p1_goals=p1_goals, p2_goals=p2_goals,
            winner_id=winner_id
        )
        session.add(game_record)

        for uid in (p1_id, p2_id):
            user = users[uid]
            user.total_games += 1
            if winner_id == uid:
                user.wins += 1
            else:
                user.losses += 1

        await session.commit()


async def get_user_stats(user_id: int) -> dict:
    """Foydalanuvchining o'yinlar soni, g'alaba va mag'lubiyatlarini hisoblaydi"""
    async with async_session() as session:
        stmt = select(
            func.count(GameStat.id).label("total"),
            func.coalesce(func.sum(case((GameStat.winner_id == user_id, 1), else_=0)), 0).label("wins"),
            func.coalesce(func.sum(case(
                ((GameStat.winner_id != user_id) & ((GameStat.p1_id == user_id) | (GameStat.p2_id == user_id)), 1),
                else_=0
            )), 0).label("losses")
        ).where(
            or_(GameStat.p1_id == user_id, GameStat.p2_id == user_id)
        )
        result = await session.execute(stmt)
        row = result.one()
        return {
            "total": row.total or 0,
            "wins": row.wins,
            "losses": row.losses
        }


# ==================== MAJBURIY KANALLAR ====================

async def get_channels():
    """Barcha majburiy kanallar ro'yxatini qaytaradi"""
    async with async_session() as session:
        stmt = select(Channel)
        result = await session.execute(stmt)
        return result.scalars().all()


async def add_channel(username: str, title: str, url: str, channel_id: int = None):
    """Yangi majburiy kanal qo'shadi"""
    if not username.startswith("@"):
        username = f"@{username}"

    async with async_session() as session:
        channel = Channel(username=username, title=title, url=url, channel_id=channel_id)
        session.add(channel)
        await session.commit()


async def remove_channel_by_id(channel_pk: int) -> bool:
    """Kanalni bazadagi (primary key) ID bo'yicha o'chiradi — admin panel shuni ishlatadi"""
    async with async_session() as session:
        stmt = delete(Channel).where(Channel.id == channel_pk)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0


# ==================== ADMINLAR ====================

async def get_admin(user_id: int) -> Admin | None:
    async with async_session() as session:
        stmt = select(Admin).where(Admin.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def is_admin(user_id: int) -> bool:
    return await get_admin(user_id) is not None


async def is_owner(user_id: int) -> bool:
    admin = await get_admin(user_id)
    return admin is not None and admin.role == "owner"


async def ensure_owner_exists(owner_id: int):
    """
    Bot ishga tushganda .env dagi OWNER_ID doim 'owner' huquqiga ega bo'lishini
    ta'minlaydi. Agar u bazada bo'lmasa — qo'shiladi, boshqa rolda bo'lsa — owner'ga o'zgartiriladi.
    """
    async with async_session() as session:
        stmt = select(Admin).where(Admin.user_id == owner_id)
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()

        if admin:
            if admin.role != "owner":
                admin.role = "owner"
                await session.commit()
        else:
            session.add(Admin(user_id=owner_id, role="owner"))
            await session.commit()


async def add_admin(user_id: int, full_name: str = None, role: str = "moderator") -> bool:
    """Yangi admin qo'shadi. Agar allaqachon mavjud bo'lsa False qaytaradi."""
    async with async_session() as session:
        stmt = select(Admin).where(Admin.user_id == user_id)
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            return False

        session.add(Admin(user_id=user_id, full_name=full_name, role=role))
        await session.commit()
        return True


async def remove_admin(user_id: int) -> bool:
    """Adminni o'chiradi (owner ekanligini tekshirish chaqiruvchi tomonda amalga oshiriladi)"""
    async with async_session() as session:
        stmt = delete(Admin).where(Admin.user_id == user_id)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0


async def get_all_admins() -> list:
    async with async_session() as session:
        stmt = select(Admin)
        result = await session.execute(stmt)
        return result.scalars().all()


# ==================== STATISTIKA (ADMIN PANEL) ====================

async def get_bot_stats() -> dict:
    """Umumiy bot statistikasi: foydalanuvchilar, o'yinlar, kanallar soni"""
    async with async_session() as session:
        users_count = await session.scalar(select(func.count(User.user_id)))
        games_count = await session.scalar(select(func.count(GameStat.id)))
        channels_count = await session.scalar(select(func.count(Channel.id)))
        return {
            "users_count": users_count or 0,
            "games_count": games_count or 0,
            "channels_count": channels_count or 0,
        }


async def get_all_user_ids() -> list:
    """Broadcast (xabar yuborish) uchun barcha foydalanuvchi ID'larini qaytaradi"""
    async with async_session() as session:
        stmt = select(User.user_id)
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]
