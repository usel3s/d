#!/usr/bin/env python3
"""Импорт пересланных альбомов Karma из AyuGram в склад админа 8647494349."""

from __future__ import annotations

import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"c:\Users\root\d")
BOT_DIR = ROOT / "bot"
sys.path.insert(0, str(BOT_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(BOT_DIR / ".env")

from config import load_settings  # noqa: E402
from services.media_store_factory import create_media_store  # noqa: E402

USER_ID = 8647494349
SRC = Path(r"C:\Users\root\Downloads\AyuGram Desktop")
OCR_CACHE = ROOT / "tools" / "_ayugram_ocr.json"
MAX_PHOTOS = 5

GPS_RE = re.compile(
    r"(5[6-7])[.,](\d{5,6})(?!\d)\s*[,;]\s*(4[0-1])[.,](\d{5,6})(?!\d)"
)
ACC_PLUS_RE = re.compile(r"±\s*(\d+[.,]\d+)\s*м")
ACC_PLAIN_RE = re.compile(r"(?<![0-9.,])(\d+[.,]\d+)\s*м")
NOTE_RE = re.compile(r"#note\s+(.+?)\s+#gps", re.I)
LOC_RE = re.compile(r"#locat[iI]on\s+([^\n#]+)", re.I)
ADDR_RE = re.compile(r"#addr\s+(.+?)\s*$", re.I | re.M)
_CYR_DIGITS = str.maketrans(
    {
        "\u041e": "0",
        "\u043e": "0",
        "\u0411": "6",
        "\u0417": "3",
        "\u0437": "3",
    }
)


def photo_num(path: Path) -> int:
    return int(path.stem.split("_")[1])


def gps_blob(text: str) -> str:
    match = re.search(r"#gps\s*(.+?)(?:#addr|$)", text, re.I | re.S)
    chunk = match.group(1) if match else text
    return chunk.translate(_CYR_DIGITS)


def parse_gps(text: str) -> tuple[float, float] | None:
    match = GPS_RE.search(gps_blob(text))
    if not match:
        match = GPS_RE.search(text.translate(_CYR_DIGITS))
    if not match:
        return None
    lat = float(match.group(1) + "." + match.group(2))
    lon = float(match.group(3) + "." + match.group(4))
    if not (55.0 <= lat <= 58.5 and 39.0 <= lon <= 42.5):
        return None
    return lat, lon


def parse_acc(text: str) -> float | None:
    blob = gps_blob(text)
    match = ACC_PLUS_RE.search(blob) or ACC_PLUS_RE.search(text)
    if not match:
        match = ACC_PLAIN_RE.search(blob)
    if not match:
        return None
    try:
        val = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    if not (0.3 <= val <= 50.0):
        return None
    return val


def parse_note(text: str) -> str:
    match = NOTE_RE.search(text)
    return re.sub(r"\s+", " ", (match.group(1) if match else "").strip())


def parse_location_label(text: str) -> str:
    match = LOC_RE.search(text)
    return re.sub(r"\s+", " ", (match.group(1) if match else "").strip())


def parse_addr(text: str) -> str:
    match = ADDR_RE.search(text)
    raw = re.sub(r"\s+", " ", (match.group(1) if match else "").strip())
    raw = re.sub(r"^ул\.\s*ица\s+", "ул. ", raw, flags=re.I)
    raw = re.sub(r"\s+улица$", "", raw, flags=re.I)
    return raw


def location_id(label: str, note: str) -> str:
    blob = f"{label} {note}".lower()
    if "тайник" in blob or "сигарет" in blob:
        return "warehouse_1"
    return "pickup"


def refresh_ocr_coords(cache: dict[str, dict]) -> dict[str, dict]:
    for rec in cache.values():
        text = str(rec.get("text") or "")
        gps = parse_gps(text)
        rec["lat"] = gps[0] if gps else None
        rec["lon"] = gps[1] if gps else None
        rec["acc"] = parse_acc(text)
        rec["note"] = parse_note(text)
        rec["loc"] = parse_location_label(text)
        rec["addr"] = parse_addr(text)
    return cache


def split_by_gps(files: list[Path], ocr: dict[str, dict]) -> list[list[Path]]:
    groups: list[list[Path]] = []
    current: list[Path] = []
    last: tuple[float, float] | None = None
    for path in files:
        rec = ocr.get(path.name) or {}
        gps = None
        if rec.get("lat") is not None and rec.get("lon") is not None:
            gps = (round(float(rec["lat"]), 6), round(float(rec["lon"]), 6))
        if gps is None:
            if current:
                current.append(path)
            else:
                current = [path]
            continue
        if last is None or gps == last or not current:
            current.append(path)
            last = gps
            continue
        groups.append(current)
        current = [path]
        last = gps
    if current:
        groups.append(current)
    return groups


def best_text(paths: list[Path], ocr: dict[str, dict]) -> str:
    texts = [(ocr.get(path.name) or {}).get("text") or "" for path in paths]
    scored = sorted(texts, key=lambda t: (("#note" in t) + ("#gps" in t) + ("#addr" in t), len(t)), reverse=True)
    return scored[0] if scored else ""


def group_gps(paths: list[Path], ocr: dict[str, dict]) -> tuple[float, float] | None:
    pts = []
    for path in paths:
        rec = ocr.get(path.name) or {}
        if rec.get("lat") is not None and rec.get("lon") is not None:
            pts.append((round(float(rec["lat"]), 6), round(float(rec["lon"]), 6)))
    if not pts:
        return None
    pts.sort()
    return pts[len(pts) // 2]


def group_acc(paths: list[Path], ocr: dict[str, dict]) -> float | None:
    vals = []
    for path in paths:
        rec = ocr.get(path.name) or {}
        if rec.get("acc") is not None:
            vals.append(float(rec["acc"]))
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2]


def to_data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    files = sorted(SRC.glob("photo_*.jpg"), key=photo_num)
    if not files:
        print("no photos in", SRC)
        return 1
    if not OCR_CACHE.exists():
        print("missing OCR cache", OCR_CACHE)
        return 1

    ocr = refresh_ocr_coords(json.loads(OCR_CACHE.read_text(encoding="utf-8")))
    OCR_CACHE.write_text(json.dumps(ocr, ensure_ascii=False, indent=2), encoding="utf-8")
    groups = split_by_gps(files, ocr)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    items: list[dict] = []
    for i, paths in enumerate(groups, start=1):
        text = best_text(paths, ocr)
        note = parse_note(text)
        loc_label = parse_location_label(text)
        addr = parse_addr(text)
        gps = group_gps(paths, ocr)
        acc = group_acc(paths, ocr)
        photos = []
        for idx, path in enumerate(paths[:MAX_PHOTOS], start=1):
            photos.append(
                {
                    "id": f"p{idx}",
                    "final": to_data_url(path),
                    "raw": "",
                    "strokes": [],
                    "stampBaked": True,
                }
            )
        geo = None
        if gps:
            geo = {
                "latitude": gps[0],
                "longitude": gps[1],
                "accuracy": acc,
                "address": addr,
            }
        loc = location_id(loc_label, note)
        item = {
            "id": f"karma_{USER_ID}_{i:02d}",
            "location": loc,
            "weight": 0.5,
            "tapeColor": "white",
            "note": note,
            "photos": photos,
            "geo": geo,
            "createdAt": now,
            "updatedAt": now,
        }
        items.append(item)
        gps_txt = f"{gps[0]:.6f},{gps[1]:.6f}" if gps else "NO_GPS"
        print(
            f"{i:02d} {loc:12} photos={len(photos)} {gps_txt} {addr} | {note}",
            flush=True,
        )

    settings = load_settings()
    store = create_media_store(settings)
    old_ids = [f"karma_{USER_ID}_{i:02d}" for i in range(1, 40)]
    removed = store.delete_item_ids(USER_ID, old_ids)
    saved = store.merge_items(USER_ID, items)
    total = len(store.list_items(user_id=USER_ID))
    print(f"removed_old={removed} merged={saved} total_for_user={total}")
    if hasattr(store, "close"):
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
