# Путь файла: bot/keyboards/antispam.py

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Dict

def get_main_menu(settings: Dict) -> InlineKeyboardMarkup:
    """Создает главное меню антиспама."""
    enabled = settings.get("enabled", False)
    buttons = [
        [InlineKeyboardButton(text=f"{'Выключить' if enabled else 'Включить'} антиспам", callback_data="antispam_toggle")],
        [InlineKeyboardButton(text="Настроить фильтры", callback_data="select_filter")],
        [InlineKeyboardButton(text="Исключения (пользователи)", callback_data="set_exceptions_users")],
        [InlineKeyboardButton(text="Исключения (домены)", callback_data="set_exceptions_domains")],
        [InlineKeyboardButton(text="Фильтр медиа", callback_data="set_media_filter")],
        [InlineKeyboardButton(text="Автокик неактивных", callback_data="toggle_auto_kick")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_filter_menu() -> InlineKeyboardMarkup:
    """Создает меню выбора фильтров."""
    buttons = [
        [InlineKeyboardButton(text="Повторяющиеся слова", callback_data="filter_repeated_words")],
        [InlineKeyboardButton(text="Повторяющиеся сообщения", callback_data="filter_repeated_messages")],
        [InlineKeyboardButton(text="Флуд", callback_data="filter_flood")],
        [InlineKeyboardButton(text="Запрещенные слова", callback_data="filter_spam_words")],
        [InlineKeyboardButton(text="Telegram ссылки", callback_data="filter_telegram_links")],
        [InlineKeyboardButton(text="Внешние ссылки", callback_data="filter_external_links")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_filter_settings_menu(filter_name: str) -> InlineKeyboardMarkup:
    """Создает меню настроек конкретного фильтра."""
    buttons = [
        [InlineKeyboardButton(text="Лимит", callback_data=f"set_limit_{filter_name}")],
        [InlineKeyboardButton(text="Действие", callback_data=f"set_action_{filter_name}")],
        [InlineKeyboardButton(text="Длительность", callback_data=f"set_duration_{filter_name}")],
    ]
    if filter_name == "flood":
        buttons.append([InlineKeyboardButton(text="Период (сек)", callback_data=f"set_flood_seconds_{filter_name}")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="select_filter")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_action_menu(filter_name: str) -> InlineKeyboardMarkup:
    """Создает меню выбора действия для фильтра."""
    buttons = [
        [InlineKeyboardButton(text="Удалить", callback_data=f"action_{filter_name}_delete")],
        [InlineKeyboardButton(text="Предупредить", callback_data=f"action_{filter_name}_warn")],
        [InlineKeyboardButton(text="Мут", callback_data=f"action_{filter_name}_mute")],
        [InlineKeyboardButton(text="Бан", callback_data=f"action_{filter_name}_ban")],
        [InlineKeyboardButton(text="Назад", callback_data=f"set_filter_{filter_name}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)