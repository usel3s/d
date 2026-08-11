#!/usr/bin/env python3
"""Импорт кладов из «Готово штампы» в MediaStore для admin 8647494349."""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT_DIR = Path(r"c:\Users\root\d\bot")
sys.path.insert(0, str(BOT_DIR))

from services.media_store import MediaStore  # noqa: E402

USER_ID = 8647494349
SRC = Path(r"C:\Users\root\Desktop\Готово штампы")
ANSWERS = Path(r"c:\Users\root\d\tools\location_answers.json")
CLUSTERS = Path(r"c:\Users\root\d\tools\gps_clusters.json")
EXPORT = Path(r"c:\Users\root\d\exports\8647494349.txt")
MEDIA_ROOT = BOT_DIR / "data" / "media"

TYPE_MAP = {
    "Тайник": "warehouse_1",
    "Прикоп": "pickup",
    "Подьезд": "warehouse_2",
    "warehouse_1": "warehouse_1",
    "pickup": "pickup",
    "warehouse_2": "warehouse_2",
}


def street_only(addr: str) -> str:
    text = (addr or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    keep = []
    for p in parts:
        low = p.lower()
        if low in {"ru", "россия", "иваново", "ivanovo"}:
            break
        keep.append(p)
    return ", ".join(keep) if keep else (parts[0] if parts else "")


def to_data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def collect_photos(folder: Path) -> list[tuple[Path, bool]]:
    """(path, no_stamp). Основные jpg + skip-папка."""
    out: list[tuple[Path, bool]] = []
    for p in sorted(folder.glob("*.jpg"), key=lambda x: x.name):
        out.append((p, False))
    skip = folder / "_skip_blue_bottle"
    if skip.is_dir():
        for p in sorted(skip.glob("*.jpg"), key=lambda x: x.name):
            out.append((p, True))
    return out[:5]  # лимит WebApp


def main() -> int:
    answers = {
        int(x["id"]): x
        for x in json.loads(ANSWERS.read_text(encoding="utf-8"))["locations"]
    }
    clusters = {
        int(c["id"]): c for c in json.loads(CLUSTERS.read_text(encoding="utf-8"))
    }
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    items: list[dict] = []
    by_loc: dict[str, int] = {}
    photo_total = 0

    for loc_id in range(1, 21):
        folder = SRC / str(loc_id)
        info_path = folder / "info.json"
        if not info_path.exists():
            print(f"skip {loc_id}: no info.json")
            continue

        info = json.loads(info_path.read_text(encoding="utf-8"))
        ans = answers.get(loc_id) or {}
        cluster = clusters.get(loc_id) or {}

        loc_key = TYPE_MAP.get(str(info.get("type") or ans.get("type") or ""), "")
        if not loc_key:
            loc_key = str(ans.get("type") or "warehouse_1")

        note = str(info.get("note") or ans.get("note") or "").strip()
        lat = info.get("lat", cluster.get("lat"))
        lon = info.get("lon", cluster.get("lon"))
        acc = cluster.get("acc")
        addr = street_only(str(info.get("addr") or cluster.get("addr") or ""))

        photos_raw = collect_photos(folder)
        if not photos_raw:
            print(f"warn {loc_id}: no photos")
            continue

        item_id = f"stash_{USER_ID}_{loc_id:02d}"
        photos = []
        for idx, (path, no_stamp) in enumerate(photos_raw, start=1):
            photo = {
                "id": f"p{idx}",
                "final": to_data_url(path),
                "raw": "",
                "strokes": [],
            }
            if no_stamp:
                photo["noStamp"] = True
            photos.append(photo)

        geo = None
        if lat is not None and lon is not None:
            geo = {
                "latitude": float(lat),
                "longitude": float(lon),
                "accuracy": float(acc) if acc is not None else None,
                "address": addr,
            }

        items.append(
            {
                "id": item_id,
                "location": loc_key,
                "weight": 0.5,
                "tapeColor": "black",
                "note": note,
                "photos": photos,
                "geo": geo,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        by_loc[loc_key] = by_loc.get(loc_key, 0) + 1
        photo_total += len(photos)
        print(f"ok {loc_id}: {loc_key} photos={len(photos)} note={note[:40]}")

    store = MediaStore(MEDIA_ROOT)
    saved = store.upsert_items(USER_ID, items)
    print(f"saved={saved} photos={photo_total} media={MEDIA_ROOT}")
    print("by_loc", by_loc)

    # экспорт-сводка
    EXPORT.parent.mkdir(parents=True, exist_ok=True)
    plain = (
        f"Экспорт · user {USER_ID}\n\n"
        f"Всего: {saved} поз · {saved * 0.5:g} г · {saved * 850:,} ₽\n\n"
        f"По граммовке:\n"
        f"• 0.5 г: {saved} шт · {saved * 850:,} ₽\n\n"
        f"По локациям:\n"
        f"• Прикоп: {by_loc.get('pickup', 0)} · {by_loc.get('pickup', 0) * 0.5:g} г · {by_loc.get('pickup', 0) * 850:,} ₽\n"
        f"• Тайник: {by_loc.get('warehouse_1', 0)} · {by_loc.get('warehouse_1', 0) * 0.5:g} г · {by_loc.get('warehouse_1', 0) * 850:,} ₽\n\n"
        f"(цена 0.5 г = 850 ₽; с фото: {photo_total})\n"
    ).replace(",", " ")
    EXPORT.write_text(plain, encoding="utf-8")
    print("export", EXPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
