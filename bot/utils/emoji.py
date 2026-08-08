"""Telegram Premium Emoji helpers."""

from __future__ import annotations

PREMIUM = {
    "settings": ("5870982283724328568", "⚙️"),
    "profile": ("5870994129244131212", "👤"),
    "users": ("5870772616305839506", "👥"),
    "file": ("5870528606328852614", "📁"),
    "stats": ("5870921681735781843", "📊"),
    "analytics": ("5870930636742595124", "📈"),
    "home": ("5873147866364514353", "🏠"),
    "lock": ("6037249452824072506", "🔒"),
    "broadcast": ("6039422865189638057", "📣"),
    "success": ("5870633910337015697", "✅"),
    "error": ("5870657884844462243", "❌"),
    "edit": ("5870676941614354370", "🖋"),
    "delete": ("5870875489362513438", "🗑"),
    "link": ("5769289093221454192", "🔗"),
    "info": ("6028435952299413210", "ℹ"),
    "bot": ("6030400221232501136", "🤖"),
    "package": ("5884479287171485878", "📦"),
    "location": ("6042011682497106307", "📍"),
    "calendar": ("5890937706803894250", "📅"),
    "coins": ("5904462880941545555", "🪙"),
    "loading": ("5345906554510012647", "🔄"),
}


def pe(key: str) -> str:
    """HTML premium emoji tag with unicode fallback."""
    emoji_id, fallback = PREMIUM[key]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def pe_id(key: str) -> str:
    return PREMIUM[key][0]
