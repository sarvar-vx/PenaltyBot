import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List

from database.requests import update_game_stats

logger = logging.getLogger(__name__)

QUEUE_LOCK = asyncio.Lock()


@dataclass
class GameSession:
    game_id: str
    p1_id: int
    p2_id: int
    p1_name: str
    p2_name: str

    kicker_id: int
    keeper_id: int
    kicker_name: str
    keeper_name: str

    p1_score: List[str] = field(default_factory=list)
    p2_score: List[str] = field(default_factory=list)

    p1_ready: bool = False
    p2_ready: bool = False

    p1_msg_id: Optional[int] = None
    p2_msg_id: Optional[int] = None

    current_round: int = 1
    max_rounds: int = 10

    kicker_choice: Optional[str] = None
    keeper_choice: Optional[str] = None

    game_phase: str = "move"  # "move" - zarba bosqichi, "ready" - tayyorlik bosqichi

    is_processing: bool = False
    timer_task: Optional[asyncio.Task] = None

    @property
    def p1_goals(self) -> int:
        return self.p1_score.count("✅")

    @property
    def p2_goals(self) -> int:
        return self.p2_score.count("✅")


MATCHMAKING_QUEUE: List[dict] = []
ACTIVE_GAMES: Dict[str, GameSession] = {}


def is_user_in_game(user_id: int) -> bool:
    """Foydalanuvchi faol o'yinda bor yoki yo'qligini tekshirish"""
    return any(user_id in (game.p1_id, game.p2_id) for game in ACTIVE_GAMES.values())


def is_user_in_queue(user_id: int) -> bool:
    """Foydalanuvchi match-making navbatida borligini tekshirish"""
    return any(player["id"] == user_id for player in MATCHMAKING_QUEUE)


async def remove_user_from_queue(user_id: int) -> bool:
    """O'yinchi qidiruvni bekor qilsa, uni navbatdan xavfsiz o'chirish"""
    global MATCHMAKING_QUEUE
    async with QUEUE_LOCK:
        initial_len = len(MATCHMAKING_QUEUE)
        MATCHMAKING_QUEUE = [p for p in MATCHMAKING_QUEUE if p["id"] != user_id]
        return len(MATCHMAKING_QUEUE) < initial_len


def get_user_active_game(user_id: int) -> Optional[GameSession]:
    """Foydalanuvchining faol o'yin sessiyasini qaytarish"""
    for game in ACTIVE_GAMES.values():
        if user_id in (game.p1_id, game.p2_id):
            return game
    return None


async def finish_and_clean_game(
    game_id: str, save_to_db: bool = False, winner_id: Optional[int] = None,
    p1_name: str = "O'yinchi", p2_name: str = "O'yinchi"
) -> None:
    """
    O'yin tugagach timer'ni bekor qilish va xotiradan (ACTIVE_GAMES) to'liq o'chirish.

    winner_id: g'olib ID'si (statistikaga yozish uchun).
    p1_name, p2_name: agar foydalanuvchi 'users' jadvalida topilmasa, uni
    yaratishda ishlatiladigan ism (xavfsizlik uchun).
    """
    game = ACTIVE_GAMES.get(game_id)
    if game:
        if game.timer_task and not game.timer_task.done():
            game.timer_task.cancel()

        if save_to_db:
            try:
                await update_game_stats(
                    p1_id=game.p1_id,
                    p2_id=game.p2_id,
                    p1_goals=game.p1_goals,
                    p2_goals=game.p2_goals,
                    winner_id=winner_id,
                    p1_name=game.p1_name,
                    p2_name=game.p2_name
                )
            except Exception:
                logger.exception(f"Game stats save error [game_id={game_id}]")

        ACTIVE_GAMES.pop(game_id, None)
