from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from config import Settings
from keyboards import main_inline_keyboard, main_reply_keyboard
from services import LogisticsService
from utils.emoji import pe

router = Router(name="start")


def _home_text() -> str:
    return f"{pe('package')} <b>Логистика</b>"


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

    await message.answer(
        _home_text(),
        reply_markup=main_reply_keyboard(settings.webapp_url),
    )
    await message.answer(
        f"{pe('link')} menu",
        reply_markup=main_inline_keyboard(settings.webapp_url),
    )


@router.message(Command("help"))
@router.message(F.text == "Справка")
async def cmd_help(message: Message) -> None:
    await message.answer(
        f"{pe('info')} <b>help</b>\n"
        "webapp · photo · gps · sync\n"
        "/admin"
    )


@router.message(F.text == "Профиль")
@router.callback_query(F.data == "menu:profile")
async def show_profile(
    event: Message | CallbackQuery,
    logistics: LogisticsService,
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

    text = (
        f"{pe('profile')} <b>profile</b>\n"
        f"<code>{user.id}</code>\n"
        f"{user.full_name}\n"
        f"{pe('analytics')} {sync_line}"
    )

    if isinstance(event, CallbackQuery):
        await message.edit_text(text)
        await event.answer()
    else:
        await message.answer(text)


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.message.edit_text(
        f"{pe('info')} <b>help</b>\n"
        "local storage · sync → /api"
    )
    await callback.answer()


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.message.edit_text(
        _home_text(),
        reply_markup=main_inline_keyboard(settings.webapp_url),
    )
    await callback.answer()
