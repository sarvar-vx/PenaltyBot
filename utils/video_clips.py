"""
Penalty natija video kliplari — yopiq kanaldagi xabar ID'lari orqali.

9 ta kombinatsiya: hujumchi yo'nalishi (left/center/right) x
darvozabon yo'nalishi (left/center/right).

Har bir videoning message_id'sini topish uchun:
Kanaldagi videoga uzoq bosing (yoki o'ng tugma) -> "Copy Message Link" ->
havola oxiridagi raqam (masalan .../c/1234567890/57 dagi 57) — shu message_id.
"""

# Kalit format: "{hujumchi_yo'nalishi}_{darvozabon_yo'nalishi}"
VIDEO_MESSAGE_IDS = {
    "left_left": 2,
    "left_center": 5,
    "left_right": 8,
    "center_left": 3,
    "center_center": 6,
    "center_right": 9,
    "right_left": 4,
    "right_center": 7,
    "right_right": 10,
}


def get_result_message_id(kicker_direction: str, keeper_direction: str) -> int | None:
    """
    kicker_direction, keeper_direction: 'left' | 'center' | 'right' | 'timeout'

    Agar ikkalasi ham haqiqiy yo'nalish bo'lsa (timeout emas) — mos videoni qaytaradi.
    Aks holda (kimdir ulgurmagan bo'lsa) None qaytaradi, chunki bunday holat uchun
    video yo'q — faqat matn ko'rsatiladi.
    """
    valid = ("left", "center", "right")
    if kicker_direction not in valid or keeper_direction not in valid:
        return None

    key = f"{kicker_direction}_{keeper_direction}"
    return VIDEO_MESSAGE_IDS.get(key)
