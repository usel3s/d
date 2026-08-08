from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from config import Settings
from keyboards import (
    guest_inline_keyboard,
    guest_reply_keyboard,
    main_inline_keyboard,
    main_reply_keyboard,
)
from services import LogisticsService
from utils.emoji import pe

router = Router(name="start")


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


def _home_text(is_admin: bool) -> str:
    if is_admin:
        return f"{pe('package')} <b>Логистика</b>"
    return (
        f"{pe('lock')} <b>Доступ закрыт</b>\n"
        "WebApp только для администраторов."
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    settings: Settings,
    logistics: LogisticsService,
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
    if admin:
        await message.answer(
            _home_text(True),
            reply_markup=main_reply_keyboard(settings.webapp_url),
        )
        await message.answer(
            f"{pe('link')} menu",
            reply_markup=main_inline_keyboard(settings.webapp_url),
        )
    else:
        await message.answer(
            _home_text(False),
            reply_markup=guest_reply_keyboard(),
        )
        await message.answer(
            f"{pe('link')} menu",
            reply_markup=guest_inline_keyboard(),
        )


@router.message(Command("help"))
@router.message(F.text == "Справка")
async def cmd_help(message: Message, settings: Settings) -> None:
    user = message.from_user
    admin = bool(user and _is_admin(user.id, settings))
    if admin:
        await message.answer(
            f"{pe('info')} <b>help</b>\n"
            "webapp · photo · gps · sync\n"
            "/admin"
        )
    else:
        await message.answer(
            f"{pe('lock')} <b>help</b>\n"
            "доступ только у admin"
        )


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
    sync_line = (
        f"sync #{row.id} · {row.items_count}"
        if row
        else "sync: —"
    )
    role = "admin" if _is_admin(user.id, settings) else "guest"

    text = (
        f"{pe('profile')} <b>profile</b>\n"
        f"<code>{user.id}</code>\n"
        f"{user.full_name}\n"
        f"role: <b>{role}</b>\n"
        f"{pe('analytics')} {sync_line}"
    )

    if isinstance(event, CallbackQuery):
        await message.edit_text(text)
        await event.answer()
    else:
        await message.answer(text)


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None:
        await callback.answer()
        return
    admin = _is_admin(callback.from_user.id, settings)
    if admin:
        await callback.message.edit_text(
            f"{pe('info')} <b>help</b>\n"
            "local storage · sync → /api"
        )
    else:
        await callback.message.edit_text(
            f"{pe('lock')} <b>help</b>\n"
            "доступ только у admin"
        )
    await callback.answer()


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None:
        await callback.answer()
        return
    admin = _is_admin(callback.from_user.id, settings)
    if admin:
        await callback.message.edit_text(
            _home_text(True),
            reply_markup=main_inline_keyboard(settings.webapp_url),
        )
    else:
        await callback.message.edit_text(
            _home_text(False),
            reply_markup=guest_inline_keyboard(),
        )
    await callback.answer()
