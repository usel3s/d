"""
Bothost Uvicorn часто ищет main:app.
Мини-приложение здесь; бот запускается из bot/main.py.
"""

from app import app

__all__ = ["app"]
