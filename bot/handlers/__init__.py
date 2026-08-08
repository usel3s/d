from __future__ import annotations

from aiogram import Dispatcher, Router

from config import Settings
from handlers import admin, start, webapp


def setup_routers(dp: Dispatcher, settings: Settings) -> None:
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(webapp.router)
    root.include_router(admin.router)
    # Extra guard for /admin command body is inside handler;
    # keep admin callback open but checked in-handler.
    dp.include_router(root)
