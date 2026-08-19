from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any


_DATA_URL_RE = re.compile(r"^data:image/[^;]+;base64,(.+)$", re.I)
_OWNER_FROM_ID_RE = re.compile(r"^(?:stash|seed)_(\d+)_")


class MediaStore:
    """Хранит позиции и фото по каждому admin user_id отдельно."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.items_path = self.root / "catalog_items.json"
        self.photos_dir = self.root / "photos"
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

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
        fd, tmp_name = tempfile.mkstemp(
            prefix=".catalog_items.",
            suffix=".tmp",
            dir=str(self.root),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(items, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.items_path)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

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

    def _owner_uid(self, item: dict[str, Any]) -> int:
        uid = self._uid(item.get("user_id"))
        if uid:
            return uid
        match = _OWNER_FROM_ID_RE.match(str(item.get("id") or ""))
        return self._uid(match.group(1)) if match else 0

    def _photos_from_raw(
        self,
        uid: int,
        item_id: str,
        raw: dict[str, Any],
        prev: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        photos_meta: list[dict[str, Any]] = []
        incoming = raw.get("photos") or []
        prev_photos = {
            str(p.get("id")): dict(p)
            for p in (prev or {}).get("photos") or []
            if isinstance(p, dict) and p.get("id")
        }
        seen_ids: set[str] = set()

        for idx, photo in enumerate(incoming):
            if not isinstance(photo, dict):
                continue
            photo_id = str(photo.get("id") or f"{item_id}_{idx}")
            seen_ids.add(photo_id)
            data_url = photo.get("final") or photo.get("raw") or ""
            blob = self._decode_photo(data_url)
            if not blob:
                kept = prev_photos.get(photo_id)
                if kept and kept.get("path"):
                    if "noStamp" in photo or "no_stamp" in photo:
                        if photo.get("noStamp") or photo.get("no_stamp"):
                            kept["no_stamp"] = True
                        else:
                            kept.pop("no_stamp", None)
                    photos_meta.append(kept)
                continue

            rel = f"{uid}/{item_id}/{photo_id}.jpg"
            path = self.photos_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            meta: dict[str, Any] = {"id": photo_id, "path": str(path)}
            if photo.get("noStamp") or photo.get("no_stamp"):
                meta["no_stamp"] = True
            photos_meta.append(meta)

        # Если клиент прислал неполный список фото без блобов — сохраняем остальные файлы
        if prev_photos:
            for pid, kept in prev_photos.items():
                if pid in seen_ids or not kept.get("path"):
                    continue
                photos_meta.append(kept)

        # Если клиент прислал позицию без фото-блобов — не теряем уже лежащие файлы
        if not photos_meta and prev_photos:
            photos_meta = [prev_photos[k] for k in prev_photos if prev_photos[k].get("path")]

        return photos_meta

    def _record_from_raw(
        self,
        uid: int,
        raw: dict[str, Any],
        prev: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            return None
        photos_meta = self._photos_from_raw(uid, item_id, raw, prev)
        return {
            "id": item_id,
            "user_id": uid,
            "location": raw.get("location"),
            "weight": raw.get("weight"),
            "tape_color": raw.get("tapeColor") or raw.get("tape_color"),
            "note": raw.get("note") or "",
            "geo": raw.get("geo") or {},
            "created_at": raw.get("createdAt") or raw.get("created_at") or (prev or {}).get("created_at"),
            "updated_at": raw.get("updatedAt") or raw.get("updated_at"),
            "photos": photos_meta,
            "hidden": bool(raw["hidden"])
            if "hidden" in raw
            else bool((prev or {}).get("hidden")),
        }

    def _split_user_items(
        self, user_id: int
    ) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
        uid = self._uid(user_id)
        existing = self._load_items()
        others = [i for i in existing if self._owner_uid(i) != uid]
        mine = [i for i in existing if self._owner_uid(i) == uid]
        prev_by_id = {str(i.get("id")): i for i in mine if i.get("id")}
        return uid, others, mine, prev_by_id

    def _remove_item_photos(self, uid: int, item_id: str) -> None:
        folder = self.photos_dir / str(uid) / str(item_id)
        if not folder.is_dir():
            return
        try:
            import shutil

            shutil.rmtree(folder, ignore_errors=True)
        except Exception:
            pass

    def upsert_items(self, user_id: int, items: list[dict[str, Any]]) -> int:
        """Полная замена позиций пользователя (чужие админы не затрагиваются)."""
        with self._lock:
            uid, others, mine, prev_by_id = self._split_user_items(user_id)
            incoming_ids: set[str] = set()
            new_records: list[dict[str, Any]] = []
            for raw in items:
                rec = self._record_from_raw(uid, raw, prev_by_id.get(str(raw.get("id") or "")))
                if not rec:
                    continue
                incoming_ids.add(rec["id"])
                new_records.append(rec)

            kept_hidden: list[dict[str, Any]] = []
            for old in mine:
                oid = str(old.get("id") or "")
                if oid and oid not in incoming_ids:
                    if old.get("hidden"):
                        kept_hidden.append(old)
                        continue
                    self._remove_item_photos(uid, oid)

            self._save_items(others + new_records + kept_hidden)
            return len(new_records)

    def merge_items(self, user_id: int, items: list[dict[str, Any]]) -> int:
        """Добавить/обновить позиции по id, остальные клады пользователя не трогать."""
        with self._lock:
            uid, others, mine, prev_by_id = self._split_user_items(user_id)
            merged = dict(prev_by_id)
            updated = 0
            for raw in items:
                rec = self._record_from_raw(uid, raw, prev_by_id.get(str(raw.get("id") or "")))
                if not rec:
                    continue
                merged[rec["id"]] = rec
                updated += 1
            self._save_items(others + list(merged.values()))
            return updated

    def delete_item_ids(self, user_id: int, item_ids: list[str]) -> int:
        with self._lock:
            uid, others, mine, _prev = self._split_user_items(user_id)
            drop = {str(x).strip() for x in item_ids if str(x).strip()}
            if not drop:
                return 0
            kept: list[dict[str, Any]] = []
            removed = 0
            for item in mine:
                oid = str(item.get("id") or "")
                if oid in drop:
                    self._remove_item_photos(uid, oid)
                    removed += 1
                    continue
                kept.append(item)
            self._save_items(others + kept)
            return removed

    def hide_all_items(self, user_id: int) -> int:
        with self._lock:
            uid, others, mine, _prev = self._split_user_items(user_id)
            hidden = 0
            next_mine: list[dict[str, Any]] = []
            for item in mine:
                rec = dict(item)
                if not rec.get("hidden"):
                    rec["hidden"] = True
                    hidden += 1
                next_mine.append(rec)
            self._save_items(others + next_mine)
            return hidden

    def restore_hidden_items(self, user_id: int) -> int:
        with self._lock:
            uid, others, mine, _prev = self._split_user_items(user_id)
            restored = 0
            next_mine: list[dict[str, Any]] = []
            for item in mine:
                rec = dict(item)
                if rec.get("hidden"):
                    rec["hidden"] = False
                    restored += 1
                next_mine.append(rec)
            self._save_items(others + next_mine)
            return restored

    def hidden_item_ids(self, user_id: int) -> list[str]:
        with self._lock:
            _uid, _others, mine, _prev = self._split_user_items(user_id)
            return [
                str(item["id"])
                for item in mine
                if item.get("hidden") and item.get("id")
            ]

    def ensure_seed(self, user_id: int) -> int:
        """Если у админа пусто — засеять известную сводку (без фото)."""
        with self._lock:
            from services.inventory_seed import build_seed_webapp_items

            uid = self._uid(user_id)
            if not uid:
                return 0
            if self.list_items(user_id=uid, include_hidden=True):
                return 0
            seed = build_seed_webapp_items(uid)
            if not seed:
                return 0
            return self.upsert_items(uid, seed)

    @staticmethod
    def photo_url(item_id: str, photo_id: str) -> str:
        return f"/api/photo/{item_id}/{photo_id}"

    @staticmethod
    def to_webapp_item(item: dict[str, Any]) -> dict[str, Any]:
        """Мета позиции для WebApp (без бинарников фото)."""
        item_id = str(item.get("id") or "")
        photos_meta = item.get("photos") or []
        photos = []
        for p in photos_meta:
            if not isinstance(p, dict):
                continue
            photo_id = str(p.get("id") or "")
            if not photo_id:
                continue
            photos.append(
                {
                    "id": photo_id,
                    "url": MediaStore.photo_url(item_id, photo_id),
                    "raw": "",
                    "final": "",
                    "strokes": [],
                    "noStamp": bool(p.get("no_stamp") or p.get("noStamp")),
                }
            )
        return {
            "id": item_id,
            "location": item.get("location"),
            "weight": item.get("weight"),
            "tapeColor": item.get("tape_color") or item.get("tapeColor") or "yellow",
            "note": item.get("note") or "",
            "photos": photos,
            "geo": item.get("geo") or None,
            "createdAt": item.get("created_at") or item.get("createdAt"),
            "updatedAt": item.get("updated_at") or item.get("updatedAt"),
        }

    def resolve_photo_file(
        self, user_id: int, item_id: str, photo_id: str
    ) -> Path | None:
        with self._lock:
            item = self.get_item(item_id, user_id=user_id)
            if not item:
                return None
            for photo in item.get("photos") or []:
                if str(photo.get("id") or "") != str(photo_id):
                    continue
                path = Path(photo.get("path") or "")
                if path.is_file():
                    return path
                return None
            return None

    def resolve_photo_bytes(
        self, user_id: int, item_id: str, photo_id: str
    ) -> bytes | None:
        with self._lock:
            item = self.get_item(item_id, user_id=user_id)
            if not item:
                return None
            for photo in item.get("photos") or []:
                if str(photo.get("id") or "") != str(photo_id):
                    continue
                path = Path(photo.get("path") or "")
                if path.is_file():
                    return path.read_bytes()
                return None
            return None

    def photo_bytes(self, item: dict[str, Any]) -> list[tuple[str, bytes]]:
        out: list[tuple[str, bytes]] = []
        for path in self.photo_paths(item):
            try:
                out.append((path.name, path.read_bytes()))
            except OSError:
                continue
        return out

    def list_webapp_items(self, user_id: int) -> list[dict[str, Any]]:
        with self._lock:
            self.ensure_seed(user_id)
            return [self.to_webapp_item(i) for i in self.list_items(user_id=user_id)]

    def list_items(
        self,
        user_id: int | None = None,
        *,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = self._load_items()
            if user_id is not None:
                uid = self._uid(user_id)
                items = [i for i in items if self._owner_uid(i) == uid]
            if not include_hidden:
                items = [i for i in items if not i.get("hidden")]
            items.sort(
                key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
                reverse=True,
            )
            return items

    def get_item(self, item_id: str, user_id: int | None = None) -> dict[str, Any] | None:
        with self._lock:
            for item in self._load_items():
                if str(item.get("id")) != str(item_id):
                    continue
                if user_id is not None and self._owner_uid(item) != self._uid(user_id):
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
