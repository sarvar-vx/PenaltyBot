from typing import Dict, Optional

# Faol takliflar: invite_id -> {inviter_id, inviter_name, inviter_chat_id,
#                                target_id, target_name, target_msg_id, timer_task}
PENDING_INVITES: Dict[str, dict] = {}


def create_invite(
    invite_id: str, inviter_id: int, inviter_name: str, inviter_chat_id: int,
    target_id: int, target_name: str, target_msg_id: int, timer_task
) -> None:
    PENDING_INVITES[invite_id] = {
        "inviter_id": inviter_id,
        "inviter_name": inviter_name,
        "inviter_chat_id": inviter_chat_id,
        "target_id": target_id,
        "target_name": target_name,
        "target_msg_id": target_msg_id,
        "timer_task": timer_task,
    }


def get_invite(invite_id: str) -> Optional[dict]:
    return PENDING_INVITES.get(invite_id)


def remove_invite(invite_id: str) -> None:
    PENDING_INVITES.pop(invite_id, None)


def is_user_busy(user_id: int) -> bool:
    """Foydalanuvchi allaqachon biror taklifda (yuborgan yoki qabul qiluvchi sifatida) bor-yo'qligini tekshiradi"""
    return any(
        invite["inviter_id"] == user_id or invite["target_id"] == user_id
        for invite in PENDING_INVITES.values()
    )