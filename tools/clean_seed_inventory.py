#!/usr/bin/env python3
"""Убрать seed_* без фото, оставить только stash_* с фото."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BOT_DIR = Path(r"c:\Users\root\d\bot")
sys.path.insert(0, str(BOT_DIR))

from services.media_store import MediaStore  # noqa: E402

USER_ID = 8647494349
MEDIA_ROOT = BOT_DIR / "data" / "media"
EXPORT = Path(r"c:\Users\root\d\exports\8647494349.txt")


def main() -> int:
    store = MediaStore(MEDIA_ROOT)
    existing = store.list_items(user_id=USER_ID)
    stamped = [
        i
        for i in existing
        if str(i.get("id") or "").startswith(f"stash_{USER_ID}_")
        and (i.get("photos") or [])
    ]
    if not stamped:
        print("no stamped items with photos")
        return 1

    web_items = []
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
                "createdAt": item.get("created_at"),
                "updatedAt": item.get("updated_at"),
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

    pickup = by.get("pickup", 0)
    stash = by.get("warehouse_1", 0)
    price = 850
    plain = (
        f"Экспорт · user {USER_ID}\n\n"
        f"Всего: {saved} поз · {saved * 0.5:g} г · {saved * price:,} ₽\n\n"
        f"По граммовке:\n"
        f"• 0.5 г: {saved} шт · {saved * price:,} ₽\n\n"
        f"По локациям:\n"
        f"• Прикоп: {pickup} · {pickup * 0.5:g} г · {pickup * price:,} ₽\n"
        f"• Тайник: {stash} · {stash * 0.5:g} г · {stash * price:,} ₽\n\n"
        f"(цена 0.5 г = {price} ₽; только с фото: {photos})\n"
    ).replace(",", " ")
    EXPORT.write_text(plain, encoding="utf-8")
    print("cleaned seed items; export updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
