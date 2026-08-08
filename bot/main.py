"""
Точка входа бота для Bothost: long polling.

HTTP/Mini App отдаёт корневой app.py через Uvicorn платформы.
Главный файл в панели: bot/main.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_factory import build_app
from config import load_settings


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    settings = load_settings()
    bot, dp, db, _ = await build_app(settings)

    # Bothost держит отдельный Uvicorn — webhook в этом процессе не слушаем
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info(
        "Bot polling started | webapp=%s",
        settings.webapp_url,
    )
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
