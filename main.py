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


def _is_loopback(request: web.Request) -> bool:
    peer = str(request.remote or "")
    if peer not in {"127.0.0.1", "::1", "localhost"}:
        return False
    # Прокси (Bothost) часто ставит remote=127.0.0.1 — не считаем это local-dev.
    forwarded = (
        request.headers.get("X-Forwarded-For")
        or request.headers.get("X-Real-IP")
        or ""
    ).strip()
    return not forwarded


def _is_local_dev_request(request: web.Request) -> bool:
    settings = request.app["settings"]
    return bool(settings.local_dev and _is_loopback(request))


def _resolve_request_user_id(request: web.Request, payload: dict | None = None) -> int:
    from utils.webapp_auth import resolve_webapp_user_id

    settings = request.app["settings"]
    payload = payload or {}
    try:
        user_id = int(payload.get("userId") or 0)
    except (TypeError, ValueError):
        user_id = 0
    init_data = str(
        payload.get("initData")
        or request.headers.get("X-Telegram-Init-Data")
        or ""
    )
    if init_data:
        resolved = resolve_webapp_user_id(init_data, settings.bot_token)
        if resolved:
            return int(resolved)
        if not _is_local_dev_request(request):
            return 0
    # userId из тела принимаем только в local-dev с loopback
    if _is_local_dev_request(request):
        if user_id:
            return user_id
        if settings.local_dev_user:
            return int(settings.local_dev_user)
    return 0


def _is_admin_user(request: web.Request, user_id: int) -> bool:
    settings = request.app["settings"]
    if bool(user_id) and user_id in settings.admin_ids:
        return True
    if (
        settings.local_dev
        and _is_loopback(request)
        and user_id
        and user_id == settings.local_dev_user
    ):
        return True
    return False


async def handle_auth(request: web.Request) -> web.Response:
    """Проверка: доступ в WebApp только у ADMIN_IDS (или LOCAL_DEV)."""
    settings = request.app["settings"]
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    user_id = _resolve_request_user_id(request, payload)
    admin = _is_admin_user(request, user_id)
    if not user_id:
        return web.json_response(
            {"ok": False, "admin": False, "error": "no_user"},
            status=401,
        )
    if not admin:
        return web.json_response(
            {"ok": False, "admin": False, "userId": user_id, "error": "forbidden"},
            status=403,
        )
    return web.json_response(
        {
            "ok": True,
            "admin": True,
            "userId": user_id,
            "localDev": bool(settings.local_dev and _is_loopback(request)),
        }
    )


async def handle_sync_items(request: web.Request) -> web.Response:
    """WebApp → сервер: merge позиций (не затирает чужие клады того же админа)."""
    media_store = request.app["media_store"]
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    user_id = _resolve_request_user_id(request, payload)
    if not user_id:
        return web.json_response({"ok": False, "error": "no_user"}, status=401)
    if not _is_admin_user(request, user_id):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    items = payload.get("items") or []
    if not isinstance(items, list):
        return web.json_response({"ok": False, "error": "bad_payload"}, status=400)

    deleted_ids = payload.get("deletedIds") or payload.get("deleted_ids") or []
    if isinstance(deleted_ids, list) and deleted_ids:
        media_store.delete_item_ids(user_id, [str(x) for x in deleted_ids])

    saved = media_store.merge_items(user_id, items)
    total = len(media_store.list_items(user_id=user_id))
    return web.json_response(
        {"ok": True, "saved": saved, "total": total, "userId": user_id}
    )


async def handle_sync_item(request: web.Request) -> web.Response:
    """Одна позиция с фото — основной путь автосохранения."""
    media_store = request.app["media_store"]
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    user_id = _resolve_request_user_id(request, payload)
    if not user_id:
        return web.json_response({"ok": False, "error": "no_user"}, status=401)
    if not _is_admin_user(request, user_id):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    item = payload.get("item")
    if not isinstance(item, dict):
        return web.json_response({"ok": False, "error": "bad_payload"}, status=400)

    saved = media_store.merge_items(user_id, [item])
    total = len(media_store.list_items(user_id=user_id))
    return web.json_response(
        {"ok": True, "saved": saved, "total": total, "userId": user_id}
    )


async def handle_delete_item(request: web.Request) -> web.Response:
    media_store = request.app["media_store"]
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    user_id = _resolve_request_user_id(request, payload)
    if not user_id:
        return web.json_response({"ok": False, "error": "no_user"}, status=401)
    if not _is_admin_user(request, user_id):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    item_id = str(payload.get("itemId") or payload.get("id") or "").strip()
    if not item_id:
        return web.json_response({"ok": False, "error": "bad_payload"}, status=400)

    removed = media_store.delete_item_ids(user_id, [item_id])
    total = len(media_store.list_items(user_id=user_id))
    return web.json_response(
        {"ok": True, "removed": removed, "total": total, "userId": user_id}
    )


async def handle_inventory(request: web.Request) -> web.Response:
    """WebApp ← сервер: позиции админа (без фото-бинарников)."""
    media_store = request.app["media_store"]
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    user_id = _resolve_request_user_id(request, payload)
    if not user_id:
        return web.json_response({"ok": False, "error": "no_user"}, status=401)
    if not _is_admin_user(request, user_id):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    items = media_store.list_webapp_items(user_id)
    return web.json_response(
        {
            "ok": True,
            "userId": user_id,
            "count": len(items),
            "items": items,
            "prices": {
                "0.5": 850,
                "1": 1100,
                "2": 260,
                "3": 380,
                "4": 490,
                "5": 600,
            },
        }
    )


def _resolve_query_user_id(request: web.Request) -> int:
    from utils.webapp_auth import resolve_webapp_user_id

    settings = request.app["settings"]
    init_data = str(
        request.headers.get("X-Telegram-Init-Data")
        or request.rel_url.query.get("initData")
        or ""
    )
    if init_data:
        resolved = resolve_webapp_user_id(init_data, settings.bot_token)
        if resolved:
            return int(resolved)
        if not _is_local_dev_request(request):
            return 0
    if _is_local_dev_request(request):
        try:
            query_uid = int(request.rel_url.query.get("userId") or 0)
        except (TypeError, ValueError):
            query_uid = 0
        if query_uid:
            return query_uid
        if settings.local_dev_user:
            return int(settings.local_dev_user)
    return 0


async def handle_photo(request: web.Request) -> web.Response:
    """Отдать JPEG с диска для галереи WebApp (<img src>)."""
    media_store = request.app["media_store"]
    item_id = str(request.match_info.get("item_id") or "").strip()
    photo_id = str(request.match_info.get("photo_id") or "").strip()
    if not item_id or not photo_id:
        return web.json_response({"ok": False, "error": "bad_path"}, status=400)

    user_id = _resolve_query_user_id(request)
    if not user_id:
        return web.json_response({"ok": False, "error": "no_user"}, status=401)
    if not _is_admin_user(request, user_id):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    path = media_store.resolve_photo_file(user_id, item_id, photo_id)
    if not path:
        return web.json_response({"ok": False, "error": "not_found"}, status=404)

    return web.FileResponse(
        path,
        headers={
            "Cache-Control": "private, max-age=86400",
            "Content-Type": "image/jpeg",
        },
    )


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    log = logging.getLogger("main")

    settings = load_settings()
    bot, dp, db, _logistics, media_store = await build_app(settings)
    await bot.delete_webhook(drop_pending_updates=True)

    app = web.Application(client_max_size=64 * 1024 * 1024)
    app["media_store"] = media_store
    app["bot"] = bot
    app["settings"] = settings

    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/api/auth", handle_auth)
    app.router.add_post("/api/sync-items", handle_sync_items)
    app.router.add_post("/api/sync-item", handle_sync_item)
    app.router.add_post("/api/delete-item", handle_delete_item)
    app.router.add_post("/api/inventory", handle_inventory)
    app.router.add_get("/api/photo/{item_id}/{photo_id}", handle_photo)

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
