#!/usr/bin/env python3
"""Демо-позиции с GPS для локального теста карты."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BOT_DIR = Path(r"c:\Users\root\d\bot")
sys.path.insert(0, str(BOT_DIR))

from services.media_store import MediaStore  # noqa: E402

USER_ID = 8647494349
MEDIA = BOT_DIR / "data" / "media"


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    demos = [
        {
            "id": "demo_1",
            "location": "warehouse_1",
            "note": "под камнем",
            "lat": 57.00663,
            "lon": 40.94384,
            "addr": "улица Ясной Поляны, 8",
        },
        {
            "id": "demo_2",
            "location": "pickup",
            "note": "1–2 см",
            "lat": 57.00347,
            "lon": 40.94359,
            "addr": "Гаражная улица, 13",
        },
        {
            "id": "demo_3",
            "location": "warehouse_1",
            "note": "под колесом",
            "lat": 57.00670,
            "lon": 40.94390,
            "addr": "улица Ясной Поляны, 10",
        },
        {
            "id": "demo_4",
            "location": "pickup",
            "note": "у забора",
            "lat": 56.99288,
            "lon": 40.96451,
            "addr": "Футбольная улица, 37",
        },
    ]
    items = []
    for d in demos:
        items.append(
            {
                "id": d["id"],
                "location": d["location"],
                "weight": 0.5,
                "tapeColor": "black",
                "note": d["note"],
                "photos": [],
                "geo": {
                    "latitude": d["lat"],
                    "longitude": d["lon"],
                    "accuracy": 8,
                    "address": d["addr"],
                },
                "createdAt": now,
                "updatedAt": now,
            }
        )
    store = MediaStore(MEDIA)
    n = store.upsert_items(USER_ID, items)
    print("demo items", n, "for", USER_ID)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
