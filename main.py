"""
Точка входа для Bothost — как cannabis src/index.js:
один процесс = HTTP на PORT + aiogram long polling.

В панели Bothost:
  Главный файл: main.py
  HTTP / mini app / webhook: ВКЛ
  Порт: 3000 (или тот, что в PANEL → должен совпасть с PORT)
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

# бот-пакет лежит в ./bot
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


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    log = logging.getLogger("main")

    settings = load_settings()
    bot, dp, db, _ = await build_app(settings)

    # Cannabis-style: polling in-process, HTTP on platform PORT
    await bot.delete_webhook(drop_pending_updates=True)

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/health", handle_health)

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
