"""Local web server only (no Telegram polling)."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from aiohttp import web

import importlib.util

ROOT = Path(__file__).resolve().parent
BOT_DIR = ROOT / "bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

_spec = importlib.util.spec_from_file_location("webapp_main", ROOT / "main.py")
if _spec is None or _spec.loader is None:
    raise RuntimeError("Failed to load main.py")
app_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app_main)

from config import load_settings  # noqa: E402
from services.media_store_factory import create_media_store  # noqa: E402


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    log = logging.getLogger("web-only")

    settings = load_settings()
    media_store = create_media_store(settings)

    app = web.Application(client_max_size=64 * 1024 * 1024)
    app["media_store"] = media_store
    app["settings"] = settings

    app.router.add_get("/", app_main.handle_index)
    app.router.add_get("/index.html", app_main.handle_index)
    app.router.add_get("/dzen-icon.png", app_main.handle_dzen_icon)
    app.router.add_get("/health", app_main.handle_health)
    app.router.add_post("/api/auth", app_main.handle_auth)
    app.router.add_post("/api/sync-items", app_main.handle_sync_items)
    app.router.add_post("/api/sync-item", app_main.handle_sync_item)
    app.router.add_post("/api/delete-item", app_main.handle_delete_item)
    app.router.add_post("/api/inventory", app_main.handle_inventory)
    app.router.add_post("/api/hide-inventory", app_main.handle_hide_inventory)
    app.router.add_post("/api/restore-inventory", app_main.handle_restore_inventory)
    app.router.add_get("/api/photo/{item_id}/{photo_id}", app_main.handle_photo)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.host, port=settings.port)
    await site.start()
    log.info(
        "Web only: http://127.0.0.1:%s (LOCAL_DEV user %s)",
        settings.port,
        settings.local_dev_user,
    )

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        if hasattr(media_store, "close"):
            media_store.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
