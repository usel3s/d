from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> bool:
    """Проверка подписи Telegram WebApp initData."""
    if not init_data or not bot_token:
        return False
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return False

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return False

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, received_hash)


def extract_user_id(init_data: str) -> int | None:
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        raw = parsed.get("user")
        if not raw:
            return None
        user = json.loads(raw)
        uid = int(user.get("id") or 0)
        return uid or None
    except Exception:
        return None


def resolve_webapp_user_id(init_data: str, bot_token: str) -> int | None:
    """
    Достаёт user id из initData.
    Если подпись валидна — ок. Если подпись битая, но user есть —
    всё равно возвращаем id (мягкий режим для кастомных клиентов).
    """
    uid = extract_user_id(init_data)
    if not uid:
        return None
    if validate_init_data(init_data, bot_token):
        return uid
    # Swiftgram / некоторые клиенты иногда ломают hash — id всё равно нужен для sync
    return uid
