from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_BOT_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BOT_DIR.parent

# Bothost cwd = /app — подхватываем .env из корня и из bot/
load_dotenv(_ROOT_DIR / ".env")
load_dotenv(_BOT_DIR / ".env")
load_dotenv()


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return frozenset(ids)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    webapp_url: str
    admin_ids: frozenset[int]
    database_path: str
    host: str
    port: int
    use_webhook: bool
    webhook_path: str
    base_url: str


def load_settings() -> Settings:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    # Bothost / PaaS usually inject PORT
    port = int((os.getenv("PORT") or os.getenv("APP_PORT") or "8080").strip())
    host = (os.getenv("HOST") or "0.0.0.0").strip()

    base_url = (os.getenv("BASE_URL") or os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
    webapp_url = (os.getenv("WEBAPP_URL") or base_url or "").strip().rstrip("/")
    if not webapp_url:
        raise RuntimeError("WEBAPP_URL (or BASE_URL) is not set")

    # На Bothost HTTP (Uvicorn/app.py) и бот (bot/main.py) — разные процессы.
    # По умолчанию polling; webhook включайте явно USE_WEBHOOK=1 только если
    # webhook принимает тот же процесс, что и HTTP.
    use_webhook = _env_bool("USE_WEBHOOK", default=False)

    webhook_path = (os.getenv("WEBHOOK_PATH") or "/webhook").strip()
    if not webhook_path.startswith("/"):
        webhook_path = "/" + webhook_path

    db_path = (os.getenv("DATABASE_PATH") or "data/logistics.db").strip()
    db_file = Path(db_path)
    if not db_file.is_absolute():
        # relative paths resolve from bot/ so data/ always рядом с кодом бота
        candidate = (_BOT_DIR / db_path).resolve()
        if not candidate.parent.exists() and (_ROOT_DIR / db_path).parent.exists():
            candidate = (_ROOT_DIR / db_path).resolve()
        db_file = candidate

    return Settings(
        bot_token=token,
        webapp_url=webapp_url,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        database_path=str(db_file),
        host=host,
        port=port,
        use_webhook=use_webhook,
        webhook_path=webhook_path,
        base_url=base_url or webapp_url,
    )
