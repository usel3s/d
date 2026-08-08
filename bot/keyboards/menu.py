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


def guest_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
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


def guest_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
                    text="Мои фото",
                    callback_data="admin:photos:0",
                    icon_custom_emoji_id=pe_id("file"),
                ),
                InlineKeyboardButton(
                    text="Экспорт",
                    callback_data="admin:export",
                    icon_custom_emoji_id=pe_id("coins"),
                ),
            ],
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


def photos_list_keyboard(page: int, total_pages: int, item_ids: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item_id in item_ids:
        short = item_id[-8:]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Позиция …{short}",
                    callback_data=f"admin:photo:{item_id}",
                    icon_custom_emoji_id=pe_id("package"),
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="Назад",
                callback_data=f"admin:photos:{page - 1}",
                icon_custom_emoji_id=pe_id("home"),
            )
        )
    if page + 1 < total_pages:
        nav.append(
            InlineKeyboardButton(
                text="Далее",
                callback_data=f"admin:photos:{page + 1}",
                icon_custom_emoji_id=pe_id("link"),
            )
        )
    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text="В админку",
                callback_data="admin:home",
                icon_custom_emoji_id=pe_id("settings"),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
