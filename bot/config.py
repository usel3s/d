from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_BOT_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BOT_DIR.parent

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


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    webapp_url: str
    admin_ids: frozenset[int]
    database_path: str
    host: str
    port: int
    local_dev: bool
    local_dev_user: int


def load_settings() -> Settings:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. "
            "Add it in Bothost panel → Environment variables (do not commit .env)."
        )

    # Bothost injects PORT (cannabis: process.env.PORT || PANEL_PORT)
    port = int((os.getenv("PORT") or os.getenv("PANEL_PORT") or "3000").strip())
    host = (os.getenv("HOST") or "0.0.0.0").strip()

    webapp_url = (
        os.getenv("WEBAPP_URL")
        or os.getenv("BASE_URL")
        or os.getenv("PANEL_PUBLIC_URL")
        or ""
    ).strip().rstrip("/")
    if not webapp_url:
        # last resort — bot still runs, WebApp button needs a real HTTPS URL in panel
        webapp_url = f"http://127.0.0.1:{port}"

    db_path = (os.getenv("DATABASE_PATH") or "data/logistics.db").strip()
    db_file = Path(db_path)
    if not db_file.is_absolute():
        db_file = (_BOT_DIR / db_path).resolve()

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    local_dev = (os.getenv("LOCAL_DEV") or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        local_dev_user = int((os.getenv("LOCAL_DEV_USER") or "0").strip() or 0)
    except ValueError:
        local_dev_user = 0
    if local_dev and not local_dev_user and admin_ids:
        local_dev_user = sorted(admin_ids)[0]

    return Settings(
        bot_token=token,
        webapp_url=webapp_url,
        admin_ids=admin_ids,
        database_path=str(db_file),
        host=host,
        port=port,
        local_dev=local_dev,
        local_dev_user=local_dev_user,
    )
