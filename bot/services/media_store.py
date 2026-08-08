from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any


_DATA_URL_RE = re.compile(r"^data:image/[^;]+;base64,(.+)$", re.I)


class MediaStore:
    """Хранит позиции и фото для админ-просмотра в Telegram."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.items_path = self.root / "catalog_items.json"
        self.photos_dir = self.root / "photos"
        self.photos_dir.mkdir(parents=True, exist_ok=True)

    def _load_items(self) -> list[dict[str, Any]]:
        if not self.items_path.exists():
            return []
        try:
            data = json.loads(self.items_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_items(self, items: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.items_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _decode_photo(self, data_url: str) -> bytes | None:
        if not data_url:
            return None
        match = _DATA_URL_RE.match(data_url.strip())
        if not match:
            return None
        try:
            return base64.b64decode(match.group(1))
        except Exception:
            return None

    def upsert_items(self, user_id: int, items: list[dict[str, Any]]) -> int:
        """Сохраняет/обновляет позиции пользователя. Фото — на диск."""
        existing = self._load_items()
        by_id = {str(i.get("id")): i for i in existing if i.get("id")}

        saved = 0
        for raw in items:
            item_id = str(raw.get("id") or "").strip()
            if not item_id:
                continue

            photos_meta: list[dict[str, str]] = []
            for idx, photo in enumerate(raw.get("photos") or []):
                if not isinstance(photo, dict):
                    continue
                photo_id = str(photo.get("id") or f"{item_id}_{idx}")
                data_url = photo.get("final") or photo.get("raw") or ""
                blob = self._decode_photo(data_url)
                if not blob:
                    # keep previous file path if photo already stored
                    prev = by_id.get(item_id) or {}
                    for p in prev.get("photos") or []:
                        if p.get("id") == photo_id and p.get("path"):
                            photos_meta.append(p)
                            break
                    continue

                rel = f"{user_id}/{item_id}/{photo_id}.jpg"
                path = self.photos_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
                photos_meta.append({"id": photo_id, "path": str(path)})

            record = {
                "id": item_id,
                "user_id": user_id,
                "location": raw.get("location"),
                "weight": raw.get("weight"),
                "tape_color": raw.get("tapeColor") or raw.get("tape_color"),
                "note": raw.get("note") or "",
                "geo": raw.get("geo") or {},
                "created_at": raw.get("createdAt") or raw.get("created_at"),
                "updated_at": raw.get("updatedAt") or raw.get("updated_at"),
                "photos": photos_meta,
            }
            by_id[item_id] = record
            saved += 1

        self._save_items(list(by_id.values()))
        return saved

    def list_items(self) -> list[dict[str, Any]]:
        items = self._load_items()
        items.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
        return items

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        for item in self._load_items():
            if str(item.get("id")) == str(item_id):
                return item
        return None

    def photo_paths(self, item: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []
        for photo in item.get("photos") or []:
            p = Path(photo.get("path") or "")
            if p.exists():
                paths.append(p)
        return paths
