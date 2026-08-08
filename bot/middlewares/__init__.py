from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database import Database
from services import LogisticsService, MediaStore


class ServicesMiddleware(BaseMiddleware):
    def __init__(
        self,
        db: Database,
        logistics: LogisticsService,
        media_store: MediaStore,
    ) -> None:
        self.db = db
        self.logistics = logistics
        self.media_store = media_store

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["logistics"] = self.logistics
        data["media_store"] = self.media_store
        return await handler(event, data)
