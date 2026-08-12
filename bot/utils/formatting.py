from __future__ import annotations

from html import escape
from typing import Any


LOCATION_LABELS = {
    "warehouse_1": "Тайник",
    "warehouse_2": "Подьезд",
    "pickup": "Прикоп",
}

TAPE_LABELS = {
    "red": "Красная",
    "blue": "Синяя",
    "yellow": "Жёлтая",
    "white": "Белая",
    "black": "Чёрная",
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


def format_items_export(
    items: list[dict[str, Any]],
    prices: dict[str, float] | None = None,
    *,
    user_id: int | None = None,
) -> str:
    """Сводка: кол-во и сумма по граммовке/локации, без фото."""
    price_map = prices or {"0.5": 850, "1": 1100, "2": 260, "3": 380, "4": 490, "5": 600}

    def _price(weight: Any) -> float:
        try:
            w = float(weight)
            key = str(int(w)) if w.is_integer() else str(w)
        except (TypeError, ValueError):
            return 0.0
        return float(price_map.get(key, 0) or 0)

    by_weight: dict[str, dict[str, float]] = {}
    by_loc: dict[str, dict[str, float]] = {}
    total_count = 0
    total_weight = 0.0
    total_revenue = 0.0

    for item in items:
        try:
            w = float(item.get("weight") or 0)
        except (TypeError, ValueError):
            w = 0.0
        price = _price(w)
        loc = str(item.get("location") or "")
        w_key = str(int(w)) if w.is_integer() else str(w)

        total_count += 1
        total_weight += w
        total_revenue += price

        bw = by_weight.setdefault(w_key, {"count": 0, "revenue": 0.0})
        bw["count"] += 1
        bw["revenue"] += price

        bl = by_loc.setdefault(loc, {"count": 0, "weight": 0.0, "revenue": 0.0})
        bl["count"] += 1
        bl["weight"] += w
        bl["revenue"] += price

    title = "Экспорт позиций"
    if user_id:
        title = f"Экспорт · user <code>{escape(str(user_id))}</code>"

    lines = [
        f"<b>{title}</b>",
        "",
        f"Всего: <b>{total_count}</b> поз · "
        f"<b>{escape(format_grams(total_weight))}</b> · "
        f"<b>{escape(format_money(total_revenue))}</b>",
    ]

    if by_weight:
        lines.append("")
        lines.append("По граммовке:")
        for w_key in sorted(by_weight.keys(), key=lambda x: float(x)):
            chunk = by_weight[w_key]
            lines.append(
                f"• {escape(format_grams(float(w_key)))}: "
                f"<b>{int(chunk['count'])}</b> шт · "
                f"<b>{escape(format_money(chunk['revenue']))}</b>"
            )

    if by_loc:
        lines.append("")
        lines.append("По локациям:")
        for loc_id, label in LOCATION_LABELS.items():
            chunk = by_loc.get(loc_id)
            if not chunk:
                continue
            lines.append(
                f"• {escape(label)}: <b>{int(chunk['count'])}</b> · "
                f"<b>{escape(format_grams(chunk['weight']))}</b> · "
                f"<b>{escape(format_money(chunk['revenue']))}</b>"
            )
        for loc_id, chunk in by_loc.items():
            if loc_id in LOCATION_LABELS:
                continue
            label = loc_id or "—"
            lines.append(
                f"• {escape(label)}: <b>{int(chunk['count'])}</b> · "
                f"<b>{escape(format_grams(chunk['weight']))}</b> · "
                f"<b>{escape(format_money(chunk['revenue']))}</b>"
            )

    return "\n".join(lines)


def format_manual_export(
    *,
    user_id: int,
    weight: float,
    count: int,
    by_location: dict[str, int],
    price_per_item: float = 850,
) -> str:
    """Текстовый экспорт по заданным цифрам (без фото)."""
    total_revenue = count * price_per_item
    total_weight = count * weight
    lines = [
        f"<b>Экспорт · user <code>{escape(str(user_id))}</code></b>",
        "",
        f"Всего: <b>{count}</b> поз · "
        f"<b>{escape(format_grams(total_weight))}</b> · "
        f"<b>{escape(format_money(total_revenue))}</b>",
        "",
        "По граммовке:",
        f"• {escape(format_grams(weight))}: <b>{count}</b> шт · "
        f"<b>{escape(format_money(total_revenue))}</b>",
        "",
        "По локациям:",
    ]
    for loc_id, label in LOCATION_LABELS.items():
        n = int(by_location.get(loc_id) or 0)
        if not n:
            continue
        lines.append(
            f"• {escape(label)}: <b>{n}</b> · "
            f"<b>{escape(format_grams(n * weight))}</b> · "
            f"<b>{escape(format_money(n * price_per_item))}</b>"
        )
    return "\n".join(lines)
