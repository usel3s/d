from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class UserRow:
    user_id: int
    username: str | None
    full_name: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class SyncRow:
    id: int
    user_id: int
    payload_json: str
    items_count: int
    total_weight: float
    total_revenue: float
    created_at: str


def sync_stats(payload: dict[str, Any]) -> tuple[int, float, float]:
    stats = payload.get("stats") or {}
    items = payload.get("items") or []
    count = int(stats.get("totalCount") or len(items) or 0)
    weight = float(stats.get("totalWeight") or 0)
    revenue = float(stats.get("totalRevenue") or 0)
    return count, weight, revenue
