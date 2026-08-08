"""
Главный файл для Bothost / PaaS с HTTP-доступом.

Что делает:
- поднимает HTTPS-ready HTTP сервер (SSL терминация на стороне Bothost)
- отдаёт Telegram Mini App (public/index.html)
- принимает Telegram webhook ИЛИ работает через long polling
- health-check для платформы: GET /health

В панели Bothost:
- Главный файл: server.py
- Опция «HTTP-сервер / mini app / webhook»: ВКЛЮЧЕНА
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_factory import build_app
from config import load_settings

PUBLIC_DIR = ROOT / "public"
INDEX_FILE = PUBLIC_DIR / "index.html"
# репозиторий с index.html рядом с bot/
ROOT_INDEX = ROOT.parent / "index.html"


def _resolve_index() -> Path:
    # Свежий файл из корня репо, иначе копия в public/ для деплоя только bot/
    if ROOT_INDEX.exists():
        return ROOT_INDEX
    if INDEX_FILE.exists():
        return INDEX_FILE
    raise FileNotFoundError(
        "index.html not found. Put WebApp into bot/public/index.html"
    )


async def handle_index(_: web.Request) -> web.Response:
    path = _resolve_index()
    return web.FileResponse(path)


async def handle_health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "logistics-bot"})


def create_http_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/health", handle_health)

    if PUBLIC_DIR.exists():
        app.router.add_static("/static/", PUBLIC_DIR, show_index=False)

    return app


async def _run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    settings = load_settings()
    bot, dp, db, _logistics = await build_app(settings)

    app = create_http_app()
    app["bot"] = bot
    app["dp"] = dp
    app["db"] = db
    app["settings"] = settings

    async def on_startup(_: web.Application) -> None:
        if settings.use_webhook:
            webhook_url = f"{settings.base_url}{settings.webhook_path}"
            await bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=dp.resolve_used_update_types(),
            )
            logging.info("Webhook set: %s", webhook_url)
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            logging.info("Webhook disabled — starting long polling in background")
            asyncio.create_task(
                dp.start_polling(bot, handle_signals=False),
                name="aiogram-polling",
            )

    async def on_shutdown(_: web.Application) -> None:
        logging.info("Shutting down…")
        try:
            if settings.use_webhook:
                await bot.delete_webhook(drop_pending_updates=False)
        finally:
            await dp.storage.close()
            await db.close()
            await bot.session.close()

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    if settings.use_webhook:
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(
            app,
            path=settings.webhook_path,
        )
        setup_application(app, dp, bot=bot)

    logging.info(
        "HTTP server on %s:%s | webapp=%s | webhook=%s",
        settings.host,
        settings.port,
        settings.webapp_url,
        settings.use_webhook,
    )
    # Bothost terminates SSL externally; app listens plain HTTP on PORT
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.host, port=settings.port)
    await site.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    except NotImplementedError:
        # Windows local run
        pass

    try:
        await stop_event.wait()
    finally:
        await runner.cleanup()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
