from __future__ import annotations

from html import escape
from typing import Any

from services.inventory_seed import DEFAULT_PRICES
from utils.emoji import pe
from utils.formatting import (
    TAPE_LABELS,
    format_grams,
    format_money,
    location_label,
)


def warehouse_stats(user_id: int, media_store: Any) -> dict[str, float | int]:
    items = media_store.list_items(user_id=user_id)
    weight = 0.0
    revenue = 0.0
    photos = 0
    for item in items:
        try:
            w = float(item.get("weight") or 0)
        except (TypeError, ValueError):
            w = 0.0
        weight += w
        key = str(int(w)) if w.is_integer() else str(w)
        revenue += float(DEFAULT_PRICES.get(key, 0) or 0)
        photos += len(item.get("photos") or [])
    return {
        "count": len(items),
        "weight": weight,
        "revenue": revenue,
        "photos": photos,
    }


def home_text(is_admin: bool, stats: dict[str, float | int] | None = None) -> str:
    if not is_admin:
        return (
            f"{pe('lock')} <b>Нет доступа</b>\n\n"
            "Этот бот только для администраторов.\n"
            "Если вам нужен доступ — напишите владельцу."
        )
    lines = [
        f"{pe('package')} <b>Учёт кладов</b>",
        "",
        "Новые позиции добавляйте в Mini App:",
        "фото, GPS и адрес сохраняются сами.",
        "",
        f"{pe('file')} <b>Склад</b> — фото и описания",
        f"{pe('stats')} <b>Сводка</b> — вес, сумма, количество",
    ]
    if stats is not None:
        lines.extend(
            [
                "",
                f"{pe('analytics')} Сейчас: <b>{int(stats['count'])}</b> поз. · "
                f"{escape(format_grams(stats['weight']))} · "
                f"{escape(format_money(stats['revenue']))}",
            ]
        )
    return "\n".join(lines)


def help_text(is_admin: bool) -> str:
    if not is_admin:
        return (
            f"{pe('lock')} <b>Справка</b>\n\n"
            "Доступ в учёт есть только у администраторов."
        )
    return (
        f"{pe('info')} <b>Справка</b>\n\n"
        f"{pe('package')} <b>Учёт</b> — Mini App: новые клады, карта, фото.\n"
        f"{pe('file')} <b>Склад</b> — просмотр позиций и фото в боте.\n"
        f"{pe('stats')} <b>Сводка</b> — вес, сумма и количество.\n\n"
        "Чтобы сохранить фото, нужен GPS.\n"
        "Открывайте Mini App кнопкой из этого бота."
    )


def profile_text(
    *,
    user_id: int,
    full_name: str,
    is_admin: bool,
    sync_id: int | None,
    sync_items: int | None,
) -> str:
    role = "Администратор" if is_admin else "Гость"
    if sync_id is not None:
        sync_line = (
            f"{pe('loading')} Последняя синхронизация: "
            f"<b>#{escape(str(sync_id))}</b> · {int(sync_items or 0)} поз."
        )
    else:
        sync_line = f"{pe('time')} Синхронизаций пока не было"
    return (
        f"{pe('profile')} <b>Профиль</b>\n\n"
        f"{escape(full_name or '—')}\n"
        f"ID: <code>{user_id}</code>\n"
        f"Роль: <b>{role}</b>\n\n"
        f"{sync_line}"
    )


def stats_text(
    *,
    stats: dict[str, float | int],
    bot_users: int,
    syncs: int,
) -> str:
    return (
        f"{pe('stats')} <b>Сводка склада</b>\n\n"
        f"{pe('package')} Позиции: <b>{int(stats['count'])}</b>\n"
        f"{pe('analytics')} Вес: <b>{escape(format_grams(stats['weight']))}</b>\n"
        f"{pe('coins')} Сумма: <b>{escape(format_money(stats['revenue']))}</b>\n"
        f"{pe('file')} Фото: <b>{int(stats['photos'])}</b>\n\n"
        f"{pe('users')} Пользователи бота: <b>{bot_users}</b>\n"
        f"{pe('loading')} Синхронизации: <b>{syncs}</b>"
    )


def warehouse_empty_text() -> str:
    return (
        f"{pe('file')} <b>Склад</b>\n"
        "Позиций: <b>0</b>\n\n"
        "Добавьте клад в учёте, и он появится здесь."
    )


def warehouse_list_text(
    items: list[dict[str, Any]],
    *,
    page: int,
    total_pages: int,
    total: int,
    start_index: int,
) -> str:
    lines = [
        f"{pe('file')} <b>Склад</b> · стр. {page + 1}/{total_pages}",
        f"Позиций: <b>{total}</b>",
        "",
        "Нажмите позицию, чтобы открыть фото.",
        "",
    ]
    for idx, item in enumerate(items, start=start_index):
        loc = location_label(str(item.get("location") or ""))
        weight = format_grams(item.get("weight") or 0)
        tape = TAPE_LABELS.get(str(item.get("tape_color") or ""), item.get("tape_color") or "—")
        n_photos = len(item.get("photos") or [])
        note = (item.get("note") or "").strip()
        if len(note) > 48:
            note = note[:47] + "…"
        lines.append(
            f"<b>{idx}.</b> {escape(loc)} · {escape(weight)} · {escape(str(tape))} · фото {n_photos}"
            + (f"\n     <i>{escape(note)}</i>" if note else "")
        )
    return "\n".join(lines)


def item_button_title(item: dict[str, Any], index: int) -> str:
    loc = location_label(str(item.get("location") or ""))
    weight = format_grams(item.get("weight") or 0)
    note = " ".join(str(item.get("note") or "").split())
    if note:
        if len(note) > 20:
            note = note[:19] + "…"
        title = f"{index}. {loc} · {weight} · {note}"
    else:
        title = f"{index}. {loc} · {weight}"
    return title[:64]


def item_caption(item: dict[str, Any]) -> str:
    loc = location_label(str(item.get("location") or ""))
    tape = TAPE_LABELS.get(str(item.get("tape_color") or ""), item.get("tape_color") or "—")
    note = (item.get("note") or "").strip() or "—"
    return (
        f"{pe('package')} <b>{escape(loc)}</b>\n"
        f"Граммовка: {escape(format_grams(item.get('weight') or 0))}\n"
        f"Изолента: {escape(str(tape))}\n"
        f"Описание: {escape(note)}"
    )
