from __future__ import annotations

from html import escape
from typing import Any


LOCATION_LABELS = {
    "warehouse_1": "Тайник",
    "warehouse_2": "Подьезд",
    "pickup": "Прикоп",
}


def location_label(location_id: str) -> str:
    return LOCATION_LABELS.get(location_id, location_id)


def format_grams(value: float | int) -> str:
    number = float(value)
    text = str(int(number)) if number.is_integer() else str(number)
    return f"{text} г"


def format_money(value: float | int) -> str:
    return f"{int(round(float(value))):,} ₽".replace(",", " ")


def summarize_sync(payload: dict[str, Any]) -> str:
    stats = payload.get("stats") or {}
    items = payload.get("items") or []
    total_weight = stats.get("totalWeight", 0)
    total_revenue = stats.get("totalRevenue", 0)
    total_count = stats.get("totalCount", len(items))

    lines = [
        f"Позиций: <b>{escape(str(total_count))}</b>",
        f"Общий вес: <b>{escape(format_grams(total_weight))}</b>",
        f"Прогноз выручки: <b>{escape(format_money(total_revenue))}</b>",
    ]

    by_loc = stats.get("byLoc") or {}
    if by_loc:
        lines.append("")
        lines.append("По локациям:")
        for loc_id, label in LOCATION_LABELS.items():
            chunk = by_loc.get(loc_id) or {}
            weight = chunk.get("weight", 0)
            revenue = chunk.get("revenue", 0)
            lines.append(
                f"• {escape(label)} — {escape(format_grams(weight))}, "
                f"{escape(format_money(revenue))}"
            )

    return "\n".join(lines)
