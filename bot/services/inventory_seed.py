from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# Сводки по админам (кол-во / локации), пока нет живого синка с фото.
SEED_INVENTORIES: dict[int, dict[str, Any]] = {
    8647494349: {
        "weight": 0.5,
        "price_per_item": 850,
        "tape_color": "yellow",
        "by_location": {
            "pickup": 21,
            "warehouse_1": 9,
        },
    },
}

DEFAULT_PRICES: dict[str, float] = {
    "0.5": 850,
    "1": 1100,
    "2": 260,
    "3": 380,
    "4": 490,
    "5": 600,
}


def seed_spec(user_id: int) -> dict[str, Any] | None:
    return SEED_INVENTORIES.get(int(user_id))


def build_seed_webapp_items(user_id: int) -> list[dict[str, Any]]:
    """Позиции в формате WebApp (без фото)."""
    spec = seed_spec(user_id)
    if not spec:
        return []

    weight = float(spec["weight"])
    tape = str(spec.get("tape_color") or "yellow")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    items: list[dict[str, Any]] = []
    n = 0
    for loc_id, count in (spec.get("by_location") or {}).items():
        for _ in range(int(count or 0)):
            n += 1
            items.append(
                {
                    "id": f"seed_{user_id}_{n:03d}",
                    "location": str(loc_id),
                    "weight": weight,
                    "tapeColor": tape,
                    "note": "",
                    "photos": [],
                    "geo": None,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
    return items


def manual_export_kwargs(user_id: int) -> dict[str, Any] | None:
    spec = seed_spec(user_id)
    if not spec:
        return None
    by_loc = spec.get("by_location") or {}
    return {
        "weight": float(spec["weight"]),
        "count": int(sum(int(v or 0) for v in by_loc.values())),
        "by_location": {str(k): int(v or 0) for k, v in by_loc.items()},
        "price_per_item": float(spec.get("price_per_item") or 0),
    }
