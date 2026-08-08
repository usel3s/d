"""
ASGI-приложение для Bothost (Uvicorn автоматически ищет app:app).

Отдаёт Telegram Mini App и health-check.
Бот при этом запускается отдельно через bot/main.py (long polling).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parent
CANDIDATES = [
    ROOT / "index.html",
    ROOT / "bot" / "public" / "index.html",
    ROOT / "public" / "index.html",
]

app = FastAPI(title="Logistics Mini App", docs_url=None, redoc_url=None)


def _index_path() -> Path:
    for path in CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("index.html not found")


@app.get("/")
@app.get("/index.html")
async def mini_app() -> FileResponse:
    return FileResponse(
        _index_path(),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "logistics-miniapp",
            "port": os.getenv("PORT", "3000"),
        }
    )
