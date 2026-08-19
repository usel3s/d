from __future__ import annotations

import base64
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

logger = logging.getLogger(__name__)

_DATA_URL_RE = re.compile(r"^data:image/[^;]+;base64,(.+)$", re.I)
_OWNER_FROM_ID_RE = re.compile(r"^(?:stash|seed)_(\d+)_")
_ITEMS = "logistics_items"
_PHOTOS = "logistics_photos"


class MongoMediaStore:
    """Склад в MongoDB: мета позиций + бинарники фото (переживает redeploy)."""

    def __init__(self, uri: str, db_name: str) -> None:
        if not uri.strip():
            raise ValueError("MongoDB URI is empty")
        self._client = MongoClient(
            uri,
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=8000,
            socketTimeoutMS=20000,
            maxPoolSize=20,
        )
        self._db: Database = self._client[db_name]
        self._items: Collection = self._db[_ITEMS]
        self._photos: Collection = self._db[_PHOTOS]
        self._lock = threading.RLock()
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self._items.create_index([("id", ASCENDING)], unique=True)
        self._items.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
        self._photos.create_index(
            [("user_id", ASCENDING), ("item_id", ASCENDING), ("photo_id", ASCENDING)],
            unique=True,
        )

    def close(self) -> None:
        self._client.close()

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

    @staticmethod
    def _decode_photo(data_url: str) -> bytes | None:
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
    def _now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def _item_query(self, user_id: int | None = None) -> dict[str, Any]:
        if user_id is None:
            return {}
        return {"user_id": self._uid(user_id)}

    def _normalize_item(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        item = dict(doc)
        item.pop("_id", None)
        photos = item.get("photos") or []
        item["photos"] = [
            {
                "id": str(p.get("id") or ""),
                **({"no_stamp": True} if p.get("no_stamp") or p.get("noStamp") else {}),
            }
            for p in photos
            if isinstance(p, dict) and p.get("id")
        ]
        return item

    def _load_user_items(self, user_id: int) -> list[dict[str, Any]]:
        uid = self._uid(user_id)
        cursor = self._items.find({"user_id": uid}).sort(
            "updated_at", DESCENDING
        )
        return [i for i in (self._normalize_item(d) for d in cursor) if i]

    def _get_item_doc(
        self, item_id: str, user_id: int | None = None
    ) -> dict[str, Any] | None:
        query: dict[str, Any] = {"id": str(item_id)}
        if user_id is not None:
            query["user_id"] = self._uid(user_id)
        return self._normalize_item(self._items.find_one(query))

    def _save_photo_blob(
        self,
        uid: int,
        item_id: str,
        photo_id: str,
        blob: bytes,
        *,
        no_stamp: bool = False,
    ) -> dict[str, Any]:
        self._photos.update_one(
            {
                "user_id": uid,
                "item_id": item_id,
                "photo_id": photo_id,
            },
            {
                "$set": {
                    "data": blob,
                    "no_stamp": bool(no_stamp),
                    "updated_at": self._now_iso(),
                },
                "$setOnInsert": {
                    "user_id": uid,
                    "item_id": item_id,
                    "photo_id": photo_id,
                },
            },
            upsert=True,
        )
        meta: dict[str, Any] = {"id": photo_id}
        if no_stamp:
            meta["no_stamp"] = True
        return meta

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
            no_stamp = bool(photo.get("noStamp") or photo.get("no_stamp"))
            data_url = photo.get("final") or photo.get("raw") or ""
            blob = self._decode_photo(data_url)
            if blob:
                photos_meta.append(
                    self._save_photo_blob(
                        uid, item_id, photo_id, blob, no_stamp=no_stamp
                    )
                )
                continue

            kept = prev_photos.get(photo_id)
            if kept:
                if no_stamp:
                    kept["no_stamp"] = True
                else:
                    kept.pop("no_stamp", None)
                photos_meta.append(kept)

        if prev_photos:
            for pid, kept in prev_photos.items():
                if pid in seen_ids:
                    continue
                photos_meta.append(kept)

        if not photos_meta and prev_photos:
            photos_meta = list(prev_photos.values())

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
            "created_at": raw.get("createdAt")
            or raw.get("created_at")
            or (prev or {}).get("created_at")
            or self._now_iso(),
            "updated_at": raw.get("updatedAt") or raw.get("updated_at") or self._now_iso(),
            "photos": photos_meta,
            "hidden": bool(raw["hidden"])
            if "hidden" in raw
            else bool((prev or {}).get("hidden")),
        }

    def _remove_item_photos(self, uid: int, item_id: str) -> None:
        self._photos.delete_many({"user_id": uid, "item_id": str(item_id)})

    def _upsert_record(self, rec: dict[str, Any]) -> None:
        payload = dict(rec)
        item_id = payload.pop("id")
        self._items.update_one(
            {"id": item_id},
            {"$set": payload, "$setOnInsert": {"id": item_id}},
            upsert=True,
        )

    def upsert_items(self, user_id: int, items: list[dict[str, Any]]) -> int:
        with self._lock:
            uid = self._uid(user_id)
            prev_by_id = {i["id"]: i for i in self._load_user_items(uid) if i.get("id")}
            incoming_ids: set[str] = set()
            count = 0
            for raw in items:
                item_id = str(raw.get("id") or "").strip()
                if not item_id:
                    continue
                rec = self._record_from_raw(uid, raw, prev_by_id.get(item_id))
                if not rec:
                    continue
                incoming_ids.add(rec["id"])
                self._upsert_record(rec)
                count += 1

            for old_id, old in prev_by_id.items():
                if old_id not in incoming_ids:
                    if old.get("hidden"):
                        continue
                    self._remove_item_photos(uid, old_id)
                    self._items.delete_one({"id": old_id, "user_id": uid})
            return count

    def merge_items(self, user_id: int, items: list[dict[str, Any]]) -> int:
        with self._lock:
            uid = self._uid(user_id)
            prev_by_id = {i["id"]: i for i in self._load_user_items(uid) if i.get("id")}
            updated = 0
            for raw in items:
                item_id = str(raw.get("id") or "").strip()
                if not item_id:
                    continue
                rec = self._record_from_raw(uid, raw, prev_by_id.get(item_id))
                if not rec:
                    continue
                self._upsert_record(rec)
                updated += 1
            return updated

    def delete_item_ids(self, user_id: int, item_ids: list[str]) -> int:
        with self._lock:
            uid = self._uid(user_id)
            drop = {str(x).strip() for x in item_ids if str(x).strip()}
            if not drop:
                return 0
            removed = 0
            for item_id in drop:
                res = self._items.delete_one({"id": item_id, "user_id": uid})
                if res.deleted_count:
                    self._remove_item_photos(uid, item_id)
                    removed += 1
            return removed

    def hide_all_items(self, user_id: int) -> int:
        with self._lock:
            uid = self._uid(user_id)
            if not uid:
                return 0
            res = self._items.update_many(
                {"user_id": uid, "hidden": {"$ne": True}},
                {"$set": {"hidden": True, "updated_at": self._now_iso()}},
            )
            return int(res.modified_count)

    def restore_hidden_items(self, user_id: int) -> int:
        with self._lock:
            uid = self._uid(user_id)
            if not uid:
                return 0
            res = self._items.update_many(
                {"user_id": uid, "hidden": True},
                {"$set": {"hidden": False, "updated_at": self._now_iso()}},
            )
            return int(res.modified_count)

    def hidden_item_ids(self, user_id: int) -> list[str]:
        with self._lock:
            uid = self._uid(user_id)
            if not uid:
                return []
            cursor = self._items.find({"user_id": uid, "hidden": True}, {"id": 1})
            return [str(doc["id"]) for doc in cursor if doc.get("id")]

    def ensure_seed(self, user_id: int) -> int:
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
        item_id = str(item.get("id") or "")
        photos = []
        for p in item.get("photos") or []:
            if not isinstance(p, dict):
                continue
            photo_id = str(p.get("id") or "")
            if not photo_id:
                continue
            photos.append(
                {
                    "id": photo_id,
                    "url": MongoMediaStore.photo_url(item_id, photo_id),
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

    def resolve_photo_bytes(
        self, user_id: int, item_id: str, photo_id: str
    ) -> bytes | None:
        with self._lock:
            item = self.get_item(item_id, user_id=user_id)
            if not item:
                return None
            allowed = {str(p.get("id") or "") for p in item.get("photos") or []}
            if str(photo_id) not in allowed:
                return None
            doc = self._photos.find_one(
                {
                    "user_id": self._uid(user_id),
                    "item_id": str(item_id),
                    "photo_id": str(photo_id),
                },
                {"data": 1},
            )
            if not doc:
                return None
            data = doc.get("data")
            return bytes(data) if data is not None else None

    def photo_bytes(self, item: dict[str, Any]) -> list[tuple[str, bytes]]:
        uid = self._owner_uid(item)
        item_id = str(item.get("id") or "")
        out: list[tuple[str, bytes]] = []
        for photo in item.get("photos") or []:
            photo_id = str(photo.get("id") or "")
            if not photo_id:
                continue
            blob = self.resolve_photo_bytes(uid, item_id, photo_id)
            if blob:
                out.append((f"{photo_id}.jpg", blob))
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
            query = self._item_query(user_id)
            if not include_hidden:
                query = dict(query)
                query["hidden"] = {"$ne": True}
            cursor = self._items.find(query).sort("updated_at", DESCENDING)
            return [i for i in (self._normalize_item(d) for d in cursor) if i]

    def get_item(self, item_id: str, user_id: int | None = None) -> dict[str, Any] | None:
        with self._lock:
            return self._get_item_doc(item_id, user_id=user_id)

    def ping(self) -> bool:
        try:
            self._client.admin.command("ping")
            return True
        except Exception as exc:
            logger.warning("MongoDB ping failed: %s", exc)
            return False
