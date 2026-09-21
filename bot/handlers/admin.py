from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InputMediaPhoto,
    Message,
)

from config import Settings
from keyboards import download_period_keyboard, section_keyboard
from keyboards.menu import photos_list_keyboard
from services import MediaStore
from utils.emoji import pe
from utils.screens import (
    download_period_text,
    item_button_title,
    item_caption,
    warehouse_empty_text,
    warehouse_list_text,
)
from utils.zip_export import build_position_archives, filter_recent_items

logger = logging.getLogger(__name__)

router = Router(name="admin")

PAGE_SIZE = 5
_zip_busy: set[int] = set()


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


async def _show_download(
    *,
    message: Message,
    edit: bool,
) -> None:
    text = download_period_text()
    markup = download_period_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _send_zip_archive(
    *,
    message: Message,
    user_id: int,
    period: str,
    media_store: MediaStore,
) -> None:
    if user_id in _zip_busy:
        await message.answer(f"{pe('loading')} Архив уже собирается.")
        return
    _zip_busy.add(user_id)
    status = None
    try:
        status = await message.answer(f"{pe('loading')} Собираю ZIP с позициями и фото…")

        def _prepare() -> tuple[list[dict], datetime, str]:
            items = media_store.list_items(user_id=user_id)
            return filter_recent_items(items, period)

        recent, cutoff, label = await asyncio.to_thread(_prepare)
        if not recent:
            await status.edit_text(
                f"{pe('file')} За выбранный период (<b>{label}</b>) позиций нет."
            )
            return

        photo_total = sum(len(item.get("photos") or []) for item in recent)
        await status.edit_text(
            f"{pe('loading')} Собираю ZIP: <b>{len(recent)}</b> поз. · "
            f"<b>{photo_total}</b> фото…"
        )

        zip_stem = f"sklad_{period}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"

        def _build() -> list[tuple[str, bytes]]:
            return build_position_archives(
                recent,
                photo_loader=media_store.photo_bytes,
                period_label=label,
                cutoff=cutoff,
                zip_stem=zip_stem,
            )

        loop = asyncio.get_running_loop()
        fut = loop.run_in_executor(None, _build)
        started = time.monotonic()
        while not fut.done():
            await asyncio.sleep(4)
            elapsed = int(time.monotonic() - started)
            try:
                await status.edit_text(
                    f"{pe('loading')} Собираю ZIP: <b>{len(recent)}</b> поз. · "
                    f"<b>{photo_total}</b> фото… {elapsed}с"
                )
            except Exception:
                pass
        archives = await fut
        caption = (
            f"{pe('file')} <b>Архив склада · {label}</b>\n"
            f"Позиций: <b>{len(recent)}</b> · фото: <b>{photo_total}</b>"
        )
        chat_id = message.chat.id
        for idx, (name, data) in enumerate(archives):
            part_caption = caption
            if len(archives) > 1:
                part_caption += f"\nЧасть {idx + 1}/{len(archives)}"
            await message.bot.send_document(
                chat_id,
                BufferedInputFile(data, filename=name),
                caption=part_caption,
                request_timeout=300,
            )
        try:
            await status.delete()
        except Exception:
            pass
    except Exception:
        logger.exception("ZIP export failed for user %s period %s", user_id, period)
        err = f"{pe('error')} Не удалось собрать архив. Попробуйте ещё раз."
        try:
            if status:
                await status.edit_text(err)
            else:
                await message.answer(err)
        except Exception:
            await message.answer(err)
    finally:
        _zip_busy.discard(user_id)


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


@router.message(F.text == "Скачать")
@router.message(Command("export"))
async def cmd_download(
    message: Message,
    settings: Settings,
) -> None:
    user = message.from_user
    if user is None or not _is_admin(user.id, settings):
        await message.answer(f"{pe('lock')} Недостаточно прав.")
        return
    await _show_download(message=message, edit=False)


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


@router.callback_query(F.data.in_({"admin:download", "admin:stats", "admin:export"}))
async def admin_download(
    callback: CallbackQuery,
    settings: Settings,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if callback.message:
        await _show_download(message=callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data.in_({"admin:zip:12h", "admin:zip:day"}))
async def admin_zip(
    callback: CallbackQuery,
    settings: Settings,
    media_store: MediaStore,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if callback.from_user.id in _zip_busy:
        await callback.answer("Архив уже собирается", show_alert=True)
        return
    period = "day" if str(callback.data).endswith(":day") else "12h"
    await callback.answer("Собираю архив…")
    if callback.message:
        await _send_zip_archive(
            message=callback.message,
            user_id=callback.from_user.id,
            period=period,
            media_store=media_store,
        )


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
    if not item or item.get("hidden"):
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
