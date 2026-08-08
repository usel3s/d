from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from database.models import SyncRow, UserRow, sync_stats


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._create_tables()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def _create_tables(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sync_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                items_count INTEGER NOT NULL DEFAULT 0,
                total_weight REAL NOT NULL DEFAULT 0,
                total_revenue REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_sync_user ON sync_events(user_id);
            CREATE INDEX IF NOT EXISTS idx_sync_created ON sync_events(created_at);
            """
        )
        await self.conn.commit()

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                updated_at = datetime('now')
            """,
            (user_id, username, full_name),
        )
        await self.conn.commit()

    async def save_sync(self, user_id: int, payload: dict[str, Any]) -> int:
        count, weight, revenue = sync_stats(payload)
        cursor = await self.conn.execute(
            """
            INSERT INTO sync_events (
                user_id, payload_json, items_count, total_weight, total_revenue
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, json.dumps(payload, ensure_ascii=False), count, weight, revenue),
        )
        await self.conn.commit()
        return int(cursor.lastrowid)

    async def get_user(self, user_id: int) -> UserRow | None:
        cursor = await self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return UserRow(
            user_id=row["user_id"],
            username=row["username"],
            full_name=row["full_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def latest_sync(self, user_id: int) -> SyncRow | None:
        cursor = await self.conn.execute(
            """
            SELECT * FROM sync_events
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return SyncRow(
            id=row["id"],
            user_id=row["user_id"],
            payload_json=row["payload_json"],
            items_count=row["items_count"],
            total_weight=row["total_weight"],
            total_revenue=row["total_revenue"],
            created_at=row["created_at"],
        )

    async def count_users(self) -> int:
        cursor = await self.conn.execute("SELECT COUNT(*) AS c FROM users")
        row = await cursor.fetchone()
        return int(row["c"] if row else 0)

    async def count_syncs(self) -> int:
        cursor = await self.conn.execute("SELECT COUNT(*) AS c FROM sync_events")
        row = await cursor.fetchone()
        return int(row["c"] if row else 0)
