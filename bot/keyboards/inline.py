# Путь файла: bot/keyboards/inline.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiogram
from loguru import logger
from bot.modules.no_sql.user_db import get_user

# Используем aiogram версии 3.20.0.post0
assert aiogram.__version__ == "3.20.0.post0", f"Expected aiogram version 3.20.0.post0, but found {aiogram.__version__}"


async def get_moderation_buttons(user_id: int, chat_id: int, caller_user_id: int) -> InlineKeyboardMarkup:
    """
    Создает inline-кнопки для модерации пользователя.
    Добавляет кнопку для просмотра логов модерации, если вызывающий пользователь имеет role_level >= 3.

    Args:
        user_id: ID пользователя, для которого создаются кнопки модерации.
        chat_id: ID чата, в котором выполняется модерация.
        caller_user_id: ID пользователя, вызывающего клавиатуру (для проверки прав).

    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками модерации.
    """
    buttons = [
        [
            InlineKeyboardButton(text="Выдать предупреждение", callback_data=f"mod_warn_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="Очистить предупреждения",
                                 callback_data=f"mod_clear_warnings_{user_id}_{chat_id}")
        ],
        [
            InlineKeyboardButton(text="Мут (10 мин)", callback_data=f"mod_mute_{user_id}_{chat_id}_10"),
            InlineKeyboardButton(text="Снять мут", callback_data=f"mod_unmute_{user_id}_{chat_id}")
        ],
        [
            InlineKeyboardButton(text="Бан (60 мин)", callback_data=f"mod_ban_{user_id}_{chat_id}_60"),
            InlineKeyboardButton(text="Снять бан", callback_data=f"mod_unban_{user_id}_{chat_id}")
        ],
        [InlineKeyboardButton(text="Исключить", callback_data=f"mod_kick_{user_id}_{chat_id}")]
    ]

    # Проверка роли вызывающего пользователя
    try:
        caller_user = await get_user(caller_user_id, create_if_not_exists=False, chat_id=chat_id)
        if caller_user.role_level >= 3 or chat_id in caller_user.server_owner_chat_ids or caller_user.user_id == caller_user.OWNER_BOT_ID:
            buttons.append(
                [InlineKeyboardButton(text="Просмотреть логи модерации", callback_data=f"mod_logs_{chat_id}")])
            logger.debug(
                f"Добавлена кнопка логов модерации для caller_user_id={caller_user_id}, role_level={caller_user.role_level}, chat_id={chat_id}")
    except ValueError as e:
        logger.warning(f"Не удалось проверить роль для caller_user_id={caller_user_id}: {e}")
        # Не добавляем кнопку логов, если пользователь не найден

    return InlineKeyboardMarkup(inline_keyboard=buttons)