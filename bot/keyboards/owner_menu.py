# kumi_pulse/bot/keyboards/owner_menu.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..modules.no_sql.constants import ROLES

def get_owner_menu() -> InlineKeyboardMarkup:
    """Создает основное меню владельца сервера"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Управление ролями", callback_data="manage_roles")],
        [InlineKeyboardButton(text="Просмотр статистики", callback_data="view_stats")],
        [InlineKeyboardButton(text="Автомодерация", callback_data="auto_moderation")]
    ])
    return keyboard

def get_user_selection_menu(users: list) -> InlineKeyboardMarkup:
    """Создает меню выбора пользователя для назначения роли"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{user.full_name} ({user.id})", callback_data=f"user_{user.id}")]
        for user in users
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_menu")])
    return keyboard

def get_role_selection_menu() -> InlineKeyboardMarkup:
    """Создает меню выбора роли"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=role, callback_data=role)]
        for role in ["JUNIOR_MOD", "SENIOR_MOD", "JUNIOR_ADMIN", "SENIOR_ADMIN", "DEPUTY"]
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_menu")])
    return keyboard