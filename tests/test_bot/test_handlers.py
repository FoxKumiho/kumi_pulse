# Путь файла: tests/test_bot/test_handlers.py

import pytest
from aiogram.types import Message, User as AiogramUser, Chat
from bot.handlers.admin import list_users_handler
from bot.modules.no_sql.user_db import get_user, set_server_owner, register_chat_member, OWNER_BOT_ID, \
    get_users_by_chat_id
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_list_users_handler(mocker):
    chat_id = -100123456
    user_id = OWNER_BOT_ID

    message = MagicMock(spec=Message)
    message.message_id = 1
    message.date = datetime.now()

    message.chat = MagicMock(spec=Chat)
    message.chat.id = chat_id
    message.chat.type = "group"

    message.from_user = MagicMock(spec=AiogramUser)
    message.from_user.id = user_id
    message.from_user.is_bot = False
    message.from_user.first_name = "Test"
    message.from_user.username = "@testowner"

    message.text = "/list_users"

    message.answer = AsyncMock()

    # Регистрируем тестовых пользователей и ботов
    await set_server_owner(user_id, chat_id)
    await register_chat_member(12345, "@aristarch", "Aristarch", chat_id, is_bot=False)
    await register_chat_member(67890, "@user3", "User3", chat_id, is_bot=False)
    await register_chat_member(11111, "@bot1", "Bot1", chat_id, is_bot=True)
    await register_chat_member(22222, "@bot2", "Bot2", chat_id, is_bot=True) # Этот пользователь с user_id 22222 и is_bot=True

    await list_users_handler(message)

    users = await get_users_by_chat_id(chat_id)
    assert len(users) == 5
    assert any(u.user_id == OWNER_BOT_ID and u.role_level == 7 for u in users)
    assert any(u.user_id == 12345 and u.role_level == 0 for u in users)
    assert any(u.user_id == 67890 and u.role_level == 0 for u in users)
    assert any(u.user_id == 11111 and u.is_bot for u in users)
    assert any(u.user_id == 22222 and u.is_bot for u in users) # <--- Исправлено: u.id -> u.user_id

    message.answer.assert_called_once()
    assert "Пользователи в чате (всего: 5):" in message.answer.call_args[0][0]