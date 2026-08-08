from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import Settings
from database import Database
from keyboards import admin_keyboard
from utils.emoji import pe

router = Router(name="admin")


@router.message(Command("admin"))
async def cmd_admin(message: Message, settings: Settings) -> None:
    user = message.from_user
    if user is None or user.id not in settings.admin_ids:
        await message.answer(f"{pe('lock')} Недостаточно прав.")
        return

    await message.answer(
        f"{pe('settings')} <b>Администрирование</b>\n"
        "Управление складским учётом и синхронизациями.",
        reply_markup=admin_keyboard(),
    )


@router.callback_query(F.data == "admin:stats")
async def admin_stats(
    callback: CallbackQuery,
    settings: Settings,
    db: Database,
) -> None:
    user = callback.from_user
    if user.id not in settings.admin_ids:
        await callback.answer("Нет доступа", show_alert=True)
        return

    users = await db.count_users()
    syncs = await db.count_syncs()
    text = (
        f"{pe('stats')} <b>Статистика бота</b>\n\n"
        f"{pe('users')} Пользователи: <b>{users}</b>\n"
        f"{pe('analytics')} Синхронизации: <b>{syncs}</b>"
    )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=admin_keyboard())
    await callback.answer()
