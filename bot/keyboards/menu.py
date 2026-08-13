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
                    text="Учёт",
                    web_app=WebAppInfo(url=webapp_url),
                    icon_custom_emoji_id=pe_id("package"),
                )
            ],
            [
                KeyboardButton(
                    text="Склад",
                    icon_custom_emoji_id=pe_id("file"),
                ),
                KeyboardButton(
                    text="Сводка",
                    icon_custom_emoji_id=pe_id("stats"),
                ),
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
                    text="Учёт",
                    web_app=WebAppInfo(url=webapp_url),
                    icon_custom_emoji_id=pe_id("package"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Склад",
                    callback_data="admin:photos:0",
                    icon_custom_emoji_id=pe_id("file"),
                ),
                InlineKeyboardButton(
                    text="Сводка",
                    callback_data="admin:stats",
                    icon_custom_emoji_id=pe_id("stats"),
                ),
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


def back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="В меню",
                    callback_data="menu:home",
                    icon_custom_emoji_id=pe_id("home"),
                )
            ]
        ]
    )


def section_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Склад",
                    callback_data="admin:photos:0",
                    icon_custom_emoji_id=pe_id("file"),
                ),
                InlineKeyboardButton(
                    text="Сводка",
                    callback_data="admin:stats",
                    icon_custom_emoji_id=pe_id("stats"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="В меню",
                    callback_data="menu:home",
                    icon_custom_emoji_id=pe_id("home"),
                )
            ],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    return section_keyboard()


def photos_list_keyboard(
    page: int,
    total_pages: int,
    buttons: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item_id, title in buttons:
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"admin:item:{item_id}",
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
                icon_custom_emoji_id=pe_id("file"),
            )
        )
    if total_pages > 1:
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=f"admin:photos:{page}",
                icon_custom_emoji_id=pe_id("stats"),
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
                text="Сводка",
                callback_data="admin:stats",
                icon_custom_emoji_id=pe_id("stats"),
            ),
            InlineKeyboardButton(
                text="В меню",
                callback_data="menu:home",
                icon_custom_emoji_id=pe_id("home"),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
