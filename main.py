"""
Bothost entry: HTTP on PORT + aiogram polling (one process).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parent
BOT_DIR = ROOT / "bot"

if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from app_factory import build_app  # noqa: E402
from config import load_settings  # noqa: E402

INDEX_CANDIDATES = [
    ROOT / "index.html",
    BOT_DIR / "public" / "index.html",
]


def resolve_index() -> Path:
    for path in INDEX_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("index.html not found")


async def handle_index(_: web.Request) -> web.Response:
    return web.FileResponse(resolve_index())


async def handle_health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "logistics-bot"})


async def handle_sync_items(request: web.Request) -> web.Response:
    """WebApp → сервер: позиции + фото для админ-галереи."""
    media_store = request.app["media_store"]
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    user_id = int(payload.get("userId") or 0)
    items = payload.get("items") or []
    if not user_id or not isinstance(items, list):
        return web.json_response({"ok": False, "error": "bad_payload"}, status=400)

    saved = media_store.upsert_items(user_id, items)
    return web.json_response({"ok": True, "saved": saved})


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    log = logging.getLogger("main")

    settings = load_settings()
    bot, dp, db, _logistics, media_store = await build_app(settings)
    await bot.delete_webhook(drop_pending_updates=True)

    app = web.Application(client_max_size=40 * 1024 * 1024)
    app["media_store"] = media_store
    app["bot"] = bot
    app["settings"] = settings

    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/api/sync-items", handle_sync_items)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.host, port=settings.port)
    await site.start()
    log.info(
        "HTTP listening on http://%s:%s → %s",
        settings.host,
        settings.port,
        settings.webapp_url,
    )

    polling_task = asyncio.create_task(
        dp.start_polling(bot, handle_signals=False),
        name="aiogram-polling",
    )
    log.info("Bot polling started")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _ask_stop() -> None:
        stop.set()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _ask_stop)
    except NotImplementedError:
        pass

    await stop.wait()
    log.info("Shutting down…")
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await runner.cleanup()
    await db.close()
    await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
