from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from config import Settings
from services import LogisticsService
from utils.emoji import pe
from utils.formatting import summarize_sync

logger = logging.getLogger(__name__)

router = Router(name="webapp")


@router.message(F.web_app_data)
async def on_web_app_data(
    message: Message,
    logistics: LogisticsService,
    settings: Settings,
) -> None:
    user = message.from_user
    data = message.web_app_data
    if user is None or data is None:
        return

    if user.id not in settings.admin_ids:
        await message.answer(f"{pe('lock')} Нет доступа к учёту.")
        return

    await logistics.register_user(user.id, user.username, user.full_name)

    try:
        payload = await logistics.ingest_webapp_payload(user.id, data.data)
    except ValueError as exc:
        logger.warning("Invalid web_app_data from %s: %s", user.id, exc)
        await message.answer(
            f"{pe('error')} Не удалось принять данные из Mini App.\n"
            f"<code>{exc}</code>"
        )
        return
    except Exception:
        logger.exception("Failed to ingest web_app_data")
        await message.answer(f"{pe('error')} Не удалось сохранить данные. Попробуйте ещё раз.")
        return

    sync_id = payload.get("_sync_id")
    summary = summarize_sync(payload)
    await message.answer(
        f"{pe('success')} <b>Склад обновлён</b>\n"
        f"Синхронизация <code>#{sync_id}</code>\n\n"
        f"{pe('stats')} {summary}"
    )
