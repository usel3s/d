from __future__ import annotations

import json
from typing import Any

from database import Database
from database.models import SyncRow


class LogisticsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def register_user(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
    ) -> None:
        await self.db.upsert_user(user_id, username, full_name)

    async def latest_sync(self, user_id: int) -> SyncRow | None:
        return await self.db.latest_sync(user_id)

    async def ingest_webapp_payload(
        self,
        user_id: int,
        raw_data: str,
    ) -> dict[str, Any]:
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ValueError("Некорректный JSON из WebApp") from exc

        if not isinstance(payload, dict):
            raise ValueError("Ожидался объект JSON")

        payload_type = payload.get("type")
        if payload_type not in {"logistics_sync", None}:
            raise ValueError(f"Неизвестный тип данных: {payload_type}")

        sync_id = await self.db.save_sync(user_id, payload)
        payload["_sync_id"] = sync_id
        return payload
