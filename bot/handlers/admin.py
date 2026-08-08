from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InputMediaPhoto,
    Message,
)

from config import Settings
from database import Database
from keyboards import admin_keyboard
from keyboards.menu import photos_list_keyboard
from services import MediaStore
from utils.emoji import pe
from utils.formatting import TAPE_LABELS, format_grams, location_label

router = Router(name="admin")

PAGE_SIZE = 5


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message, settings: Settings) -> None:
    user = message.from_user
    if user is None or not _is_admin(user.id, settings):
        await message.answer(f"{pe('lock')} Недостаточно прав.")
        return

    await message.answer(
        f"{pe('settings')} <b>admin</b>",
        reply_markup=admin_keyboard(),
    )


@router.callback_query(F.data == "admin:home")
async def admin_home(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            f"{pe('settings')} <b>admin</b>",
            reply_markup=admin_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def admin_stats(
    callback: CallbackQuery,
    settings: Settings,
    db: Database,
    media_store: MediaStore,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return

    users = await db.count_users()
    syncs = await db.count_syncs()
    items = media_store.list_items()
    photos = sum(len(i.get("photos") or []) for i in items)
    text = (
        f"{pe('stats')} <b>Статистика бота</b>\n\n"
        f"{pe('users')} Пользователи: <b>{users}</b>\n"
        f"{pe('analytics')} Синхронизации: <b>{syncs}</b>\n"
        f"{pe('package')} Позиции: <b>{len(items)}</b>\n"
        f"{pe('file')} Фото: <b>{photos}</b>"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=admin_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:photos:"))
async def admin_photos_list(
    callback: CallbackQuery,
    settings: Settings,
    media_store: MediaStore,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return

    page = int(callback.data.split(":")[-1] or 0)
    items = media_store.list_items()
    if not items:
        await callback.answer("Позиций пока нет", show_alert=True)
        return

    total_pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    lines = [
        f"{pe('file')} <b>Все фото</b> · стр. {page + 1}/{total_pages}",
        f"Позиций: <b>{len(items)}</b>",
        "",
    ]
    for item in chunk:
        loc = location_label(str(item.get("location") or ""))
        weight = format_grams(item.get("weight") or 0)
        tape = item.get("tape_color") or "—"
        n_photos = len(item.get("photos") or [])
        note = (item.get("note") or "")[:40]
        lines.append(
            f"• <b>{loc}</b> · {weight} · изолента {tape} · фото {n_photos}"
            + (f"\n  <i>{note}</i>" if note else "")
        )

    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=photos_list_keyboard(
                page,
                total_pages,
                [str(i.get("id")) for i in chunk],
            ),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:photo:"))
async def admin_photo_item(
    callback: CallbackQuery,
    settings: Settings,
    media_store: MediaStore,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return

    item_id = callback.data.split(":", 2)[-1]
    item = media_store.get_item(item_id)
    if not item:
        await callback.answer("Позиция не найдена", show_alert=True)
        return

    paths = media_store.photo_paths(item)
    if not paths:
        await callback.answer("Фото нет на сервере", show_alert=True)
        return

    loc = location_label(str(item.get("location") or ""))
    caption = (
        f"{pe('package')} <b>{loc}</b>\n"
        f"Граммовка: {format_grams(item.get('weight') or 0)}\n"
        f"Изолента: {TAPE_LABELS.get(str(item.get('tape_color') or ''), item.get('tape_color') or '—')}\n"
        f"Описание: {item.get('note') or '—'}"
    )

    await callback.answer()
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id

    if len(paths) == 1:
        data = paths[0].read_bytes()
        await callback.bot.send_photo(
            chat_id,
            BufferedInputFile(data, filename=paths[0].name),
            caption=caption,
            parse_mode="HTML",
        )
        return

    media: list[InputMediaPhoto] = []
    for i, path in enumerate(paths[:5]):
        data = path.read_bytes()
        media.append(
            InputMediaPhoto(
                media=BufferedInputFile(data, filename=path.name),
                caption=caption if i == 0 else None,
                parse_mode="HTML" if i == 0 else None,
            )
        )
    await callback.bot.send_media_group(chat_id, media=media)
