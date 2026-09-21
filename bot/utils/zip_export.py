from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from utils.formatting import format_grams, location_label, tape_label

MSK = timezone(timedelta(hours=3))
TELEGRAM_DOC_LIMIT = 18 * 1024 * 1024
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def parse_item_dt(item: dict[str, Any]) -> datetime | None:
    raw = (
        item.get("created_at")
        or item.get("createdAt")
        or item.get("updated_at")
        or item.get("updatedAt")
    )
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def period_cutoff(period: str, now: datetime | None = None) -> tuple[datetime, str]:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if period == "day":
        local = now_utc.astimezone(MSK)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(timezone.utc), "день"
    return now_utc - timedelta(hours=12), "12 часов"


def filter_recent_items(
    items: list[dict[str, Any]],
    period: str,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], datetime, str]:
    cutoff, label = period_cutoff(period, now)
    recent: list[dict[str, Any]] = []
    for item in items:
        dt = parse_item_dt(item)
        if dt is not None and dt >= cutoff:
            recent.append(item)
    recent.sort(key=lambda it: parse_item_dt(it) or datetime.min.replace(tzinfo=timezone.utc))
    return recent, cutoff, label


def safe_part(text: str, max_len: int = 48) -> str:
    cleaned = _UNSAFE_NAME.sub(" ", str(text or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned[:max_len] or "item"


def folder_name(item: dict[str, Any], index: int) -> str:
    loc = location_label(str(item.get("location") or ""))
    weight = format_grams(item.get("weight") or 0)
    note = " ".join(str(item.get("note") or "").split())
    parts = [f"{index:02d}", loc, weight]
    if note:
        parts.append(note)
    return safe_part("_".join(parts), 80)


def _fmt_geo(geo: dict[str, Any] | None) -> str:
    if not isinstance(geo, dict):
        return "—"
    try:
        lat = float(geo.get("latitude"))
        lon = float(geo.get("longitude"))
    except (TypeError, ValueError):
        return "—"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return "—"
    line = f"{lat:.6f}, {lon:.6f}"
    address = str(geo.get("address") or "").strip()
    if address:
        line += f"\nАдрес: {address}"
    return line


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(MSK).strftime("%Y-%m-%d %H:%M")


def item_info_text(item: dict[str, Any], index: int, photo_count: int) -> str:
    loc = location_label(str(item.get("location") or ""))
    tape = tape_label(str(item.get("tape_color") or item.get("tapeColor") or ""))
    note = (item.get("note") or "").strip() or "—"
    created = parse_item_dt(item)
    lines = [
        f"{index}. {loc}",
        f"Граммовка: {format_grams(item.get('weight') or 0)}",
        f"Изолента: {tape}",
        f"Описание: {note}",
        f"Фото: {photo_count}",
        f"Создано: {_fmt_dt(created)} (МСК)",
        f"GPS: {_fmt_geo(item.get('geo') or {})}",
        f"ID: {item.get('id') or '—'}",
    ]
    return "\n".join(lines) + "\n"


def summary_text(
    items: list[dict[str, Any]],
    *,
    period_label: str,
    cutoff: datetime,
    photo_counts: list[int],
) -> str:
    lines = [
        f"Склад · {period_label}",
        f"С {_fmt_dt(cutoff)} (МСК)",
        f"Позиций: {len(items)}",
        f"Фото: {sum(photo_counts)}",
        "",
    ]
    for idx, item in enumerate(items, start=1):
        loc = location_label(str(item.get("location") or ""))
        weight = format_grams(item.get("weight") or 0)
        tape = tape_label(str(item.get("tape_color") or item.get("tapeColor") or ""))
        n_photos = photo_counts[idx - 1] if idx - 1 < len(photo_counts) else 0
        note = (item.get("note") or "").strip()
        lines.append(f"{idx}. {loc} · {weight} · {tape} · фото {n_photos}")
        if note:
            lines.append(f"   {note}")
    return "\n".join(lines) + "\n"


def _zip_write(zf: zipfile.ZipFile, name: str, data: bytes | str) -> None:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    info = zipfile.ZipInfo(filename=name.replace("\\", "/"))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.date_time = datetime.now().timetuple()[:6]
    info.flag_bits |= 0x800
    zf.writestr(info, payload)


class _ZipParts:
    def __init__(self, stem: str) -> None:
        self.stem = stem
        self.parts: list[bytes] = []
        self._buf = io.BytesIO()
        self._zf = zipfile.ZipFile(self._buf, "w", compression=zipfile.ZIP_DEFLATED)
        self._raw_added = 0

    def add(self, name: str, data: bytes | str) -> None:
        payload = data.encode("utf-8") if isinstance(data, str) else data
        if self._raw_added and self._raw_added + len(payload) > TELEGRAM_DOC_LIMIT:
            self._flush()
        _zip_write(self._zf, name, payload)
        self._raw_added += len(payload)

    def _flush(self) -> None:
        self._zf.close()
        blob = self._buf.getvalue()
        if blob:
            self.parts.append(blob)
        self._buf = io.BytesIO()
        self._zf = zipfile.ZipFile(self._buf, "w", compression=zipfile.ZIP_DEFLATED)
        self._raw_added = 0

    def finish(self) -> list[tuple[str, bytes]]:
        self._zf.close()
        blob = self._buf.getvalue()
        if blob:
            self.parts.append(blob)
        if not self.parts:
            empty = io.BytesIO()
            with zipfile.ZipFile(empty, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                _zip_write(zf, "пусто.txt", "Нет файлов\n")
            self.parts.append(empty.getvalue())
        out: list[tuple[str, bytes]] = []
        total = len(self.parts)
        for i, data in enumerate(self.parts, start=1):
            if total == 1:
                name = f"{self.stem}.zip"
            else:
                name = f"{self.stem}_{i}.zip"
            out.append((name, data))
        return out


def build_position_archives(
    items: list[dict[str, Any]],
    *,
    photo_loader: Callable[[dict[str, Any]], list[tuple[str, bytes]]],
    period_label: str,
    cutoff: datetime,
    zip_stem: str = "sklad",
) -> list[tuple[str, bytes]]:
    photo_counts = [len(item.get("photos") or []) for item in items]
    parts = _ZipParts(zip_stem)
    parts.add(
        "позиции.txt",
        summary_text(
            items,
            period_label=period_label,
            cutoff=cutoff,
            photo_counts=photo_counts,
        ),
    )
    used_folders: set[str] = set()
    for idx, item in enumerate(items, start=1):
        blobs = photo_loader(item) or []
        folder = folder_name(item, idx)
        base = folder
        n = 2
        while folder.lower() in used_folders:
            folder = f"{base}_{n}"
            n += 1
        used_folders.add(folder.lower())
        parts.add(f"{folder}/info.txt", item_info_text(item, idx, len(blobs)))
        for photo_idx, (_name, data) in enumerate(blobs, start=1):
            parts.add(f"{folder}/{photo_idx:02d}.jpg", data)
    return parts.finish()
