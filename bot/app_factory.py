from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import Settings
from database import Database
from handlers import setup_routers
from middlewares import ServicesMiddleware
from services import LogisticsService

logger = logging.getLogger(__name__)


async def build_app(settings: Settings) -> tuple[Bot, Dispatcher, Database, LogisticsService]:
    db = Database(settings.database_path)
    await db.connect()
    logistics = LogisticsService(db)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp.update.middleware(ServicesMiddleware(db, logistics))

    @dp.update.outer_middleware()
    async def settings_middleware(handler, event, data):
        data["settings"] = settings
        return await handler(event, data)

    setup_routers(dp, settings)
    logger.info("Dispatcher ready")
    return bot, dp, db, logistics
