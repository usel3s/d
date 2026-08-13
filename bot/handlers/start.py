from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from config import Settings
from keyboards import (
    back_home_keyboard,
    guest_inline_keyboard,
    guest_reply_keyboard,
    main_inline_keyboard,
    main_reply_keyboard,
)
from services import LogisticsService, MediaStore
from utils.screens import help_text, home_text, profile_text, warehouse_stats

router = Router(name="start")


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


def _home_markup(is_admin: bool, webapp_url: str):
    if is_admin:
        return main_inline_keyboard(webapp_url)
    return guest_inline_keyboard()


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    settings: Settings,
    logistics: LogisticsService,
    media_store: MediaStore,
) -> None:
    user = message.from_user
    if user is None:
        return

    await logistics.register_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )

    admin = _is_admin(user.id, settings)
    stats = warehouse_stats(user.id, media_store) if admin else None
    if admin:
        await message.answer(
            home_text(True, stats),
            reply_markup=main_reply_keyboard(settings.webapp_url),
        )
    else:
        await message.answer(
            home_text(False),
            reply_markup=guest_reply_keyboard(),
        )


@router.message(Command("help"))
@router.message(F.text == "Справка")
async def cmd_help(message: Message, settings: Settings) -> None:
    user = message.from_user
    admin = bool(user and _is_admin(user.id, settings))
    await message.answer(help_text(admin), reply_markup=back_home_keyboard())


@router.message(F.text == "Профиль")
@router.callback_query(F.data == "menu:profile")
async def show_profile(
    event: Message | CallbackQuery,
    logistics: LogisticsService,
    settings: Settings,
) -> None:
    if isinstance(event, CallbackQuery):
        user = event.from_user
        message = event.message
        if message is None:
            await event.answer()
            return
    else:
        user = event.from_user
        message = event

    if user is None:
        return

    await logistics.register_user(user.id, user.username, user.full_name)
    row = await logistics.latest_sync(user.id)
    text = profile_text(
        user_id=user.id,
        full_name=user.full_name or "",
        is_admin=_is_admin(user.id, settings),
        sync_id=row.id if row else None,
        sync_items=row.items_count if row else None,
    )
    markup = back_home_keyboard()

    if isinstance(event, CallbackQuery):
        await message.edit_text(text, reply_markup=markup)
        await event.answer()
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None:
        await callback.answer()
        return
    admin = _is_admin(callback.from_user.id, settings)
    await callback.message.edit_text(
        help_text(admin),
        reply_markup=back_home_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:home")
async def cb_home(
    callback: CallbackQuery,
    settings: Settings,
    media_store: MediaStore,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    admin = _is_admin(callback.from_user.id, settings)
    stats = warehouse_stats(callback.from_user.id, media_store) if admin else None
    await callback.message.edit_text(
        home_text(admin, stats),
        reply_markup=_home_markup(admin, settings.webapp_url),
    )
    await callback.answer()
