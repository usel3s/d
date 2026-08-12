#!/usr/bin/env python3
"""Складывает старый seed (30 без фото) + клады со штампами (20 с фото)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT_DIR = Path(r"c:\Users\root\d\bot")
sys.path.insert(0, str(BOT_DIR))

from services.media_store import MediaStore  # noqa: E402
from utils.formatting import format_items_export  # noqa: E402
from services.inventory_seed import DEFAULT_PRICES  # noqa: E402

USER_ID = 8647494349
MEDIA_ROOT = BOT_DIR / "data" / "media"
EXPORT = Path(r"c:\Users\root\d\exports\8647494349.txt")

# Старый экспорт (без фото)
LEGACY = {
    "pickup": 21,
    "warehouse_1": 9,
}


def main() -> int:
    store = MediaStore(MEDIA_ROOT)
    existing = store.list_items(user_id=USER_ID)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Оставляем позиции со штампами (stash_*), убираем старые seed_*
    stamped = [i for i in existing if str(i.get("id") or "").startswith(f"stash_{USER_ID}_")]
    if not stamped:
        print("no stamped items — run import_stamped_inventory.py first")
        return 1

    # WebApp-формат для upsert (фото уже на диске — передаём id без data_url, upsert сохранит path)
    web_items: list[dict] = []
    for item in stamped:
        photos = []
        for p in item.get("photos") or []:
            photos.append(
                {
                    "id": p.get("id"),
                    "final": "",
                    "raw": "",
                    "noStamp": bool(p.get("no_stamp") or p.get("noStamp")),
                }
            )
        web_items.append(
            {
                "id": item["id"],
                "location": item.get("location"),
                "weight": item.get("weight"),
                "tapeColor": item.get("tape_color") or "black",
                "note": item.get("note") or "",
                "photos": photos,
                "geo": item.get("geo"),
                "createdAt": item.get("created_at") or now,
                "updatedAt": item.get("updated_at") or now,
            }
        )

    n = 0
    for loc, count in LEGACY.items():
        for _ in range(int(count)):
            n += 1
            web_items.append(
                {
                    "id": f"seed_{USER_ID}_{n:03d}",
                    "location": loc,
                    "weight": 0.5,
                    "tapeColor": "black",
                    "note": "",
                    "photos": [],
                    "geo": None,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )

    saved = store.upsert_items(USER_ID, web_items)
    items = store.list_items(user_id=USER_ID)
    by: dict[str, int] = {}
    photos = 0
    for i in items:
        by[str(i.get("location"))] = by.get(str(i.get("location")), 0) + 1
        photos += len(i.get("photos") or [])

    print("saved", saved, "by", by, "photos", photos)

    text = format_items_export(items, DEFAULT_PRICES, user_id=USER_ID)
    # plain file без HTML
    pickup = by.get("pickup", 0)
    stash = by.get("warehouse_1", 0)
    total = saved
    price = 850
    plain = (
        f"Экспорт · user {USER_ID}\n\n"
        f"Всего: {total} поз · {total * 0.5:g} г · {total * price:,} ₽\n\n"
        f"По граммовке:\n"
        f"• 0.5 г: {total} шт · {total * price:,} ₽\n\n"
        f"По локациям:\n"
        f"• Прикоп: {pickup} · {pickup * 0.5:g} г · {pickup * price:,} ₽\n"
        f"• Тайник: {stash} · {stash * 0.5:g} г · {stash * price:,} ₽\n\n"
        f"(цена 0.5 г = {price} ₽; с фото: {photos}; без фото: {total - sum(1 for i in items if i.get('photos'))})\n"
    ).replace(",", " ")
    EXPORT.write_text(plain, encoding="utf-8")
    print("export written")
    # avoid console ₽ issues
    Path(r"c:\Users\root\d\tools\_merge_export_preview.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
