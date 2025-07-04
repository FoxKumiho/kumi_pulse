# Путь файла: bot/handlers/admin.py

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
import aiogram

from .common import register_all_chat_members
from ..modules.no_sql.user_db import get_user, get_users_by_chat_id, set_server_owner, remove_server_owner, \
    register_chat_member, update_user, reset_activity_count, get_known_chats

# Используем aiogram версии 3.20.0.post0
assert aiogram.__version__ == "3.20.0.post0", f"Expected aiogram version 3.20.0.post0, but found {aiogram.__version__}"

router = Router()


@router.message(Command(commands=["set_owner"]))
async def set_owner_handler(message: Message):
    """
    Обработчик команды /set_owner. Назначает пользователя владельцем сервера.

    Args:
        message: Объект сообщения от aiogram
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.role_level < 7:
            await message.answer("У вас нет прав для этой команды! Требуется роль Владелец бота.")
            logger.warning(f"Пользователь {user_id} попытался выполнить /set_owner без прав, chat_id={chat_id}")
            return
        args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if args and args.isdigit():
            target_user_id = int(args)
            await set_server_owner(target_user_id, chat_id)
            await message.answer(f"Пользователь {target_user_id} назначен владельцем сервера.")
            logger.info(
                f"Пользователь {target_user_id} назначен владельцем сервера для chat_id={chat_id} пользователем {user_id}")
        else:
            await message.answer("Укажите user_id: /set_owner <user_id>")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /set_owner для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        await message.answer("Произошла ошибка. Попробуйте позже или свяжитесь с поддержкой.")


@router.message(Command(commands=["remove_owner"]))
async def remove_owner_handler(message: Message):
    """
    Обработчик команды /remove_owner. Удаляет роль владельца сервера у пользователя.

    Args:
        message: Объект сообщения от aiogram
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.role_level < 7:
            await message.answer("У вас нет прав для этой команды! Требуется роль Владелец бота.")
            logger.warning(f"Пользователь {user_id} попытался выполнить /remove_owner без прав, chat_id={chat_id}")
            return
        args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if args and args.isdigit():
            target_user_id = int(args)
            await remove_server_owner(target_user_id, chat_id)
            await message.answer(f"Роль владельца сервера удалена у пользователя {target_user_id}.")
            logger.info(
                f"Роль владельца сервера удалена у пользователя {target_user_id} для chat_id={chat_id} пользователем {user_id}")
        else:
            await message.answer("Укажите user_id: /remove_owner <user_id>")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /remove_owner для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        await message.answer("Произошла ошибка. Попробуйте позже или свяжитесь с поддержкой.")


@router.message(Command(commands=["list_users"]))
async def list_users_handler(message: Message):
    """
    Обработчик команды /list_users. Выводит список всех пользователей, связанных с текущим чатом.

    Args:
        message: Объект сообщения от aiogram
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
    include_bots = args == "include_bots"

    try:
        # Проверяем права бота
        bot_member = await message.bot.get_chat_member(chat_id=chat_id, user_id=message.bot.id)
        if bot_member.status != "administrator" or not bot_member.can_manage_chat:
            await message.answer(
                "Бот не имеет прав администратора или 'Manage Chat'. Пожалуйста, предоставьте необходимые права.")
            logger.warning(f"Бот не имеет прав администратора или 'Manage Chat' в chat_id={chat_id}")
            return

        # Проверяем роль пользователя
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.role_level < 6:
            await message.answer("У вас нет прав для этой команды! Требуется роль Владелец сервера или выше.")
            logger.warning(f"Пользователь {user_id} попытался выполнить /list_users без прав, chat_id={chat_id}")
            return

        # Регистрируем всех текущих участников чата
        await register_all_chat_members(chat_id, message.bot)

        # Получаем список пользователей
        users = await get_users_by_chat_id(chat_id)
        logger.info(
            f"Перед фильтрацией найдено пользователей: {len(users)} для chat_id={chat_id}: {[f'{u.user_id} ({u.get_role_for_chat(chat_id)}, is_bot={u.is_bot}, activity={u.get_activity_count(chat_id)})' for u in users]}")
        if not include_bots:
            users = [u for u in users if not u.is_bot]

        if not users:
            await message.answer("В этом чате нет зарегистрированных пользователей. Попробуйте /force_register_all.")
            logger.info(f"Не найдено пользователей для chat_id={chat_id}, include_bots={include_bots}")
            return

        # Сортируем пользователей по активности
        users = sorted(users, key=lambda u: u.get_activity_count(chat_id), reverse=True)
        # Формируем список пользователей
        user_list = [
            f"ID: {u.user_id}, Имя: {u.display_name or 'Не указано'}, "
            f"Username: {u.username or 'Не указано'}, Роль: {u.get_role_for_chat(chat_id)}, "
            f"Активность: {u.get_activity_count(chat_id)}, "
            f"Бот: {'Да' if u.is_bot else 'Нет'}, Бан: {'Да' if u.is_banned else 'Нет'}, Premium: {'Да' if u.is_premium else 'Нет'}"
            for u in users
        ]
        response = f"Пользователи в чате (всего: {len(users)}):\n" + "\n".join(user_list)
        await message.answer(response)
        logger.info(
            f"Обработана команда /list_users для user_id={user_id}, chat_id={chat_id}, найдено пользователей: {len(users)}, IDs: {[u.user_id for u in users]}, include_bots={include_bots}")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /list_users для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        await message.answer(
            "Произошла ошибка. Попробуйте /force_register_all или убедитесь, что бот имеет права администратора.")


@router.message(Command(commands=["reset_activity"]))
async def reset_activity_handler(message: Message):
    """
    Обработчик команды /reset_activity. Сбрасывает счетчик активности пользователя в текущем чате.

    Args:
        message: Объект сообщения от aiogram
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.role_level < 7:
            await message.answer("У вас нет прав для этой команды! Требуется роль Владелец бота.")
            logger.warning(f"Пользователь {user_id} попытался выполнить /reset_activity без прав, chat_id={chat_id}")
            return
        args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if args and args.isdigit():
            target_user_id = int(args)
            await reset_activity_count(target_user_id, chat_id)
            await message.answer(f"Счетчик активности для пользователя {target_user_id} сброшен в чате {chat_id}.")
            logger.info(
                f"Счетчик активности сброшен для user_id={target_user_id} в chat_id={chat_id} пользователем {user_id}")
        else:
            await message.answer("Укажите user_id: /reset_activity <user_id>")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /reset_activity для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        await message.answer("Произошла ошибка. Попробуйте позже или свяжитесь с поддержкой.")


@router.message(Command(commands=["check_bot_permissions"]))
async def check_bot_permissions_handler(message: Message):
    """
    Обработчик команды /check_bot_permissions. Проверяет права бота во всех известных чатах.

    Args:
        message: Объект сообщения от aiogram
    """
    user_id = message.from_user.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=message.chat.id)
        if user.role_level < 7:
            await message.answer("У вас нет прав для этой команды! Требуется роль Владелец бота.")
            logger.warning(f"Пользователь {user_id} попытался выполнить /check_bot_permissions без прав")
            return
        known_chats = await get_known_chats()
        if not known_chats:
            await message.answer("Бот не зарегистрирован ни в одном чате.")
            logger.info(f"Команда /check_bot_permissions выполнена, но известные чаты отсутствуют")
            return
        permissions_report = []
        for chat_id in known_chats:
            try:
                bot_member = await message.bot.get_chat_member(chat_id=chat_id, user_id=message.bot.id)
                status = bot_member.status
                can_manage_chat = bot_member.can_manage_chat if status == "administrator" else False
                permissions_report.append(
                    f"Чат ID: {chat_id}, Статус: {status}, "
                    f"Manage Chat: {'Да' if can_manage_chat else 'Нет'}"
                )
                logger.info(
                    f"Проверены права бота в chat_id={chat_id}: status={status}, can_manage_chat={can_manage_chat}")
            except TelegramBadRequest as e:
                permissions_report.append(f"Чат ID: {chat_id}, Ошибка: {str(e)}")
                logger.error(f"Ошибка при проверке прав бота в chat_id={chat_id}: {str(e)}")
        response = f"Права бота в чатах (всего: {len(known_chats)}):\n" + "\n".join(permissions_report)
        await message.answer(response)
        logger.info(
            f"Команда /check_bot_permissions выполнена для user_id={user_id}, найдено чатов: {len(known_chats)}")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /check_bot_permissions для user_id={user_id}: {str(e)}")
        await message.answer("Произошла ошибка. Проверьте логи или свяжитесь с поддержкой.")

