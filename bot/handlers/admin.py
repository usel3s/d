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
from keyboards import section_keyboard
from keyboards.menu import photos_list_keyboard
from services import MediaStore
from utils.emoji import pe
from utils.screens import (
    item_button_title,
    item_caption,
    stats_text,
    warehouse_empty_text,
    warehouse_list_text,
    warehouse_stats,
)

router = Router(name="admin")

PAGE_SIZE = 5


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


async def _show_warehouse(
    *,
    message: Message,
    user_id: int,
    page: int,
    media_store: MediaStore,
    edit: bool,
) -> None:
    items = media_store.list_items(user_id=user_id)
    if not items:
        text = warehouse_empty_text()
        markup = section_keyboard()
        if edit:
            await message.edit_text(text, reply_markup=markup)
        else:
            await message.answer(text, reply_markup=markup)
        return

    total_pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    start_index = page * PAGE_SIZE + 1
    text = warehouse_list_text(
        chunk,
        page=page,
        total_pages=total_pages,
        total=len(items),
        start_index=start_index,
    )
    buttons = [
        (str(item.get("id") or ""), item_button_title(item, start_index + idx))
        for idx, item in enumerate(chunk)
        if item.get("id")
    ]
    markup = photos_list_keyboard(page, total_pages, buttons)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _show_stats(
    *,
    message: Message,
    user_id: int,
    db: Database,
    media_store: MediaStore,
    edit: bool,
) -> None:
    users = await db.count_users()
    syncs = await db.count_syncs()
    inv = warehouse_stats(user_id, media_store)
    text = stats_text(
        stats=inv,
        bot_users=users,
        syncs=syncs,
    )
    if edit:
        await message.edit_text(text, reply_markup=section_keyboard())
    else:
        await message.answer(text, reply_markup=section_keyboard())


@router.message(Command("admin"))
@router.message(F.text == "Склад")
async def cmd_warehouse(
    message: Message,
    settings: Settings,
    media_store: MediaStore,
) -> None:
    user = message.from_user
    if user is None or not _is_admin(user.id, settings):
        await message.answer(f"{pe('lock')} Недостаточно прав.")
        return
    await _show_warehouse(
        message=message,
        user_id=user.id,
        page=0,
        media_store=media_store,
        edit=False,
    )


@router.message(F.text == "Сводка")
async def cmd_stats(
    message: Message,
    settings: Settings,
    db: Database,
    media_store: MediaStore,
) -> None:
    user = message.from_user
    if user is None or not _is_admin(user.id, settings):
        await message.answer(f"{pe('lock')} Недостаточно прав.")
        return
    await _show_stats(
        message=message,
        user_id=user.id,
        db=db,
        media_store=media_store,
        edit=False,
    )


@router.message(Command("export"))
async def cmd_export(message: Message, settings: Settings) -> None:
    user = message.from_user
    if user is None or not _is_admin(user.id, settings):
        await message.answer(f"{pe('lock')} Недостаточно прав.")
        return
    await message.answer(f"{pe('error')} Экспорт сейчас отключён.")


@router.callback_query(F.data == "admin:home")
async def admin_home(
    callback: CallbackQuery,
    settings: Settings,
    media_store: MediaStore,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if callback.message:
        await _show_warehouse(
            message=callback.message,
            user_id=callback.from_user.id,
            page=0,
            media_store=media_store,
            edit=True,
        )
    await callback.answer()


@router.callback_query(F.data == "admin:export")
async def admin_export(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer("Экспорт отключён", show_alert=True)


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
    if callback.message:
        await _show_stats(
            message=callback.message,
            user_id=callback.from_user.id,
            db=db,
            media_store=media_store,
            edit=True,
        )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^admin:photos:\d+$"))
async def admin_photos_list(
    callback: CallbackQuery,
    settings: Settings,
    media_store: MediaStore,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    page = int(str(callback.data).rsplit(":", 1)[-1] or 0)
    if callback.message:
        await _show_warehouse(
            message=callback.message,
            user_id=callback.from_user.id,
            page=page,
            media_store=media_store,
            edit=True,
        )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^(?:admin:item:.+|admin:photo:(?!s:).+)$"))
async def admin_photo_item(
    callback: CallbackQuery,
    settings: Settings,
    media_store: MediaStore,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return

    raw = str(callback.data or "")
    if raw.startswith("admin:item:"):
        item_id = raw[len("admin:item:") :]
    else:
        item_id = raw.split(":", 2)[-1]
    item = media_store.get_item(item_id, user_id=callback.from_user.id)
    if not item:
        await callback.answer("Позиция не найдена", show_alert=True)
        return

    blobs = media_store.photo_bytes(item)
    if not blobs:
        await callback.answer("Фото нет на сервере", show_alert=True)
        return

    caption = item_caption(item)
    await callback.answer()
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id

    if len(blobs) == 1:
        name, data = blobs[0]
        await callback.bot.send_photo(
            chat_id,
            BufferedInputFile(data, filename=name),
            caption=caption,
            parse_mode="HTML",
        )
        return

    media: list[InputMediaPhoto] = []
    for i, (name, data) in enumerate(blobs[:5]):
        media.append(
            InputMediaPhoto(
                media=BufferedInputFile(data, filename=name),
                caption=caption if i == 0 else None,
                parse_mode="HTML" if i == 0 else None,
            )
        )
    await callback.bot.send_media_group(chat_id, media=media)
