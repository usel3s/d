#!/usr/bin/env python3
"""Залить локальный catalog_items.json + photos в MongoDB."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "bot"
sys.path.insert(0, str(BOT_DIR))
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(BOT_DIR / ".env")

from config import load_settings  # noqa: E402
from services.media_store import MediaStore  # noqa: E402
from services.mongo_media_store import MongoMediaStore  # noqa: E402
from services.media_store_factory import _db_name_from_uri


def main() -> int:
    settings = load_settings()
    uri = (settings.mongodb_uri or "").strip()
    if not uri:
        print("MONGODB_URI не задан в .env / Bothost variables")
        return 1

    media_root = Path(settings.database_path).resolve().parent / "media"
    catalog = media_root / "catalog_items.json"
    if not catalog.is_file():
        print(f"Нет локального каталога: {catalog}")
        return 1

    raw = json.loads(catalog.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        print("catalog_items.json пуст")
        return 1

    db_name = (settings.mongodb_db or "").strip() or _db_name_from_uri(uri)
    mongo = MongoMediaStore(uri, db_name)
    if not mongo.ping():
        print("MongoDB недоступен")
        return 1

    local = MediaStore(media_root)
    by_user: dict[int, list[dict]] = {}
    for item in raw:
        uid = int(item.get("user_id") or 0)
        if not uid:
            continue
        web = local.to_webapp_item(item)
        photos = []
        for p in item.get("photos") or []:
            pid = str(p.get("id") or "")
            path = Path(p.get("path") or "")
            if not pid or not path.is_file():
                continue
            import base64

            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            photos.append(
                {
                    "id": pid,
                    "final": f"data:image/jpeg;base64,{b64}",
                    "noStamp": bool(p.get("no_stamp") or p.get("noStamp")),
                }
            )
        web["photos"] = photos
        by_user.setdefault(uid, []).append(web)

    total_items = 0
    total_photos = 0
    for uid, items in by_user.items():
        saved = mongo.merge_items(uid, items)
        total_items += saved
        for it in items:
            total_photos += len(it.get("photos") or [])
        print(f"user {uid}: merged {saved} items")

    listed = mongo.list_items()
    print(
        f"done · uploaded {total_items} items ({total_photos} photo payloads) · "
        f"mongo total={len(listed)}"
    )
    mongo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
