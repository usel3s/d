from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from utils.emoji import pe_id


def main_reply_keyboard(webapp_url: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Открыть учёт",
                    web_app=WebAppInfo(url=webapp_url),
                    icon_custom_emoji_id=pe_id("package"),
                )
            ],
            [
                KeyboardButton(
                    text="Профиль",
                    icon_custom_emoji_id=pe_id("profile"),
                ),
                KeyboardButton(
                    text="Справка",
                    icon_custom_emoji_id=pe_id("info"),
                ),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_inline_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть учёт",
                    web_app=WebAppInfo(url=webapp_url),
                    icon_custom_emoji_id=pe_id("package"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Профиль",
                    callback_data="menu:profile",
                    icon_custom_emoji_id=pe_id("profile"),
                ),
                InlineKeyboardButton(
                    text="Справка",
                    callback_data="menu:help",
                    icon_custom_emoji_id=pe_id("info"),
                ),
            ],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Статистика",
                    callback_data="admin:stats",
                    icon_custom_emoji_id=pe_id("stats"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="menu:home",
                    icon_custom_emoji_id=pe_id("home"),
                )
            ],
        ]
    )
