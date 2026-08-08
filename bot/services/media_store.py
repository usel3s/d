from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any


_DATA_URL_RE = re.compile(r"^data:image/[^;]+;base64,(.+)$", re.I)


class MediaStore:
    """Хранит позиции и фото по каждому admin user_id отдельно."""

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

    @staticmethod
    def _uid(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def upsert_items(self, user_id: int, items: list[dict[str, Any]]) -> int:
        """Полная замена позиций пользователя (чужие админы не затрагиваются)."""
        uid = self._uid(user_id)
        existing = self._load_items()
        others = [i for i in existing if self._uid(i.get("user_id")) != uid]
        prev_by_id = {
            str(i.get("id")): i
            for i in existing
            if self._uid(i.get("user_id")) == uid and i.get("id")
        }

        new_records: list[dict[str, Any]] = []
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
                    prev = prev_by_id.get(item_id) or {}
                    for p in prev.get("photos") or []:
                        if p.get("id") == photo_id and p.get("path"):
                            photos_meta.append(p)
                            break
                    continue

                rel = f"{uid}/{item_id}/{photo_id}.jpg"
                path = self.photos_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
                photos_meta.append({"id": photo_id, "path": str(path)})

            new_records.append(
                {
                    "id": item_id,
                    "user_id": uid,
                    "location": raw.get("location"),
                    "weight": raw.get("weight"),
                    "tape_color": raw.get("tapeColor") or raw.get("tape_color"),
                    "note": raw.get("note") or "",
                    "geo": raw.get("geo") or {},
                    "created_at": raw.get("createdAt") or raw.get("created_at"),
                    "updated_at": raw.get("updatedAt") or raw.get("updated_at"),
                    "photos": photos_meta,
                }
            )

        self._save_items(others + new_records)
        return len(new_records)

    def ensure_seed(self, user_id: int) -> int:
        """Если у админа пусто — засеять известную сводку (без фото)."""
        from services.inventory_seed import build_seed_webapp_items

        uid = self._uid(user_id)
        if not uid:
            return 0
        if self.list_items(user_id=uid):
            return 0
        seed = build_seed_webapp_items(uid)
        if not seed:
            return 0
        return self.upsert_items(uid, seed)

    @staticmethod
    def to_webapp_item(item: dict[str, Any]) -> dict[str, Any]:
        """Мета позиции для WebApp (без бинарников фото)."""
        photos_meta = item.get("photos") or []
        return {
            "id": str(item.get("id") or ""),
            "location": item.get("location"),
            "weight": item.get("weight"),
            "tapeColor": item.get("tape_color") or item.get("tapeColor") or "yellow",
            "note": item.get("note") or "",
            "photos": [
                {"id": str(p.get("id") or ""), "raw": "", "final": "", "strokes": []}
                for p in photos_meta
                if isinstance(p, dict)
            ],
            "geo": item.get("geo") or None,
            "createdAt": item.get("created_at") or item.get("createdAt"),
            "updatedAt": item.get("updated_at") or item.get("updatedAt"),
        }

    def list_webapp_items(self, user_id: int) -> list[dict[str, Any]]:
        self.ensure_seed(user_id)
        return [self.to_webapp_item(i) for i in self.list_items(user_id=user_id)]

    def list_items(self, user_id: int | None = None) -> list[dict[str, Any]]:
        items = self._load_items()
        if user_id is not None:
            uid = self._uid(user_id)
            items = [i for i in items if self._uid(i.get("user_id")) == uid]
        items.sort(
            key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
            reverse=True,
        )
        return items

    def get_item(self, item_id: str, user_id: int | None = None) -> dict[str, Any] | None:
        for item in self._load_items():
            if str(item.get("id")) != str(item_id):
                continue
            if user_id is not None and self._uid(item.get("user_id")) != self._uid(user_id):
                return None
            return item
        return None

    def photo_paths(self, item: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []
        for photo in item.get("photos") or []:
            p = Path(photo.get("path") or "")
            if p.exists():
                paths.append(p)
        return paths
