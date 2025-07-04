# Путь файла: bot/handlers/moderation.py

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from loguru import logger
import aiogram
import time
import re
import unicodedata
from ..modules.no_sql.user_db import get_user, add_warning, ban_user, unban_user, mute_user, unmute_user, \
    clear_warnings, get_moderation_logs, OWNER_BOT_ID, log_moderation_action, ROLE_NAMES
from motor.motor_asyncio import AsyncIOMotorCollection

# Используем aiogram версии 3.20.0.post0
assert aiogram.__version__ == "3.20.0.post0", f"Expected aiogram version 3.20.0.post0, but found {aiogram.__version__}"

router = Router()

async def check_permissions(message: Message, user, required_role: int, chat_id: int, command: str) -> bool:
    """Проверяет, имеет ли пользователь достаточную роль для выполнения команды."""
    if user.role_level >= required_role or user.user_id == OWNER_BOT_ID or chat_id in user.server_owner_chat_ids:
        return True
    await message.answer(f"🚫 У вас недостаточно прав! Требуется роль **{ROLE_NAMES[required_role]}** или выше.")
    logger.warning(f"Пользователь {user.user_id} попытался выполнить {command} без прав, chat_id={chat_id}")
    return False

async def check_bot_permissions(message: Message, required_permissions: dict) -> bool:
    """Проверяет, имеет ли бот необходимые права администратора."""
    try:
        bot_member = await message.bot.get_chat_member(chat_id=message.chat.id, user_id=message.bot.id)
        has_permissions = bot_member.status == "administrator" and all(
            getattr(bot_member, perm, False) for perm in required_permissions
        )
        if not has_permissions:
            perms_text = ", ".join(required_permissions.keys())
            await message.answer(
                f"🚫 Бот не имеет прав администратора или прав на {perms_text}. "
                f"Пожалуйста, предоставьте права администратора."
            )
            logger.warning(f"Бот не имеет прав администратора или {perms_text} в chat_id={message.chat.id}")
        return has_permissions
    except TelegramBadRequest as e:
        logger.error(f"Ошибка проверки прав бота в chat_id={message.chat.id}: {str(e)}")
        await message.answer("🚫 Ошибка проверки прав бота. Убедитесь, что бот является администратором.")
        return False

async def normalize_name(name: str) -> str:
    """Нормализует имя, сохраняя пробелы и эмодзи, удаляя только лишние специальные символы."""
    name = name.strip()
    name = re.sub(r'[\u200B-\u200F\u202A-\u202E]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return unicodedata.normalize('NFKC', name)

async def extract_user_id(message: Message, for_unmute: bool = False) -> tuple[int | None, str | None, str | None]:
    """Извлекает user_id, duration и reason из команды."""
    args = message.text.split(maxsplit=2 if for_unmute else 3)
    reason = "Не указана"
    duration = None
    target_user_id = None

    clean_args = [re.sub(r'[<>[\]]', '', arg) for arg in args[1:]] if len(args) > 1 else []

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user_id = message.reply_to_message.from_user.id
        if for_unmute:
            return target_user_id, None, None
        reason = ' '.join(clean_args) if clean_args else "Не указана"
        if message.text.startswith('/mute') and clean_args:
            try:
                duration = clean_args[0] if clean_args[0].isdigit() else None
                reason = ' '.join(clean_args[1:]) if len(clean_args) > 1 else "Не указана"
            except IndexError:
                reason = "Не указана"
    elif not clean_args:
        logger.warning(f"Недостаточно аргументов для команды: {message.text}")
        return None, None, None
    else:
        first_arg = clean_args[0]
        remaining_args = clean_args[1:] if len(clean_args) > 1 else []
        collection = await get_user_collection()

        if first_arg.isdigit():
            target_user_id = int(first_arg)
            if for_unmute or message.text.startswith('/clear_warnings'):
                return target_user_id, None, None
            reason = ' '.join(remaining_args) if remaining_args else "Не указана"
            if message.text.startswith('/mute'):
                duration = remaining_args[0] if remaining_args and remaining_args[0].isdigit() else None
                reason = ' '.join(remaining_args[1:]) if len(remaining_args) > 1 else "Не указана"
        elif first_arg.startswith("@"):
            for entity in message.entities or []:
                if entity.type == "mention" and message.text[entity.offset:entity.offset + entity.length].strip('<>') == first_arg:
                    if entity.user:
                        target_user_id = entity.user.id
                        await get_user(target_user_id, create_if_not_exists=True, chat_id=message.chat.id, display_name=first_arg.lstrip('@'))
                        logger.info(f"Зарегистрирован пользователь {target_user_id} с display_name={first_arg.lstrip('@')}")
                    else:
                        username = first_arg.lstrip('@')
                        user_data = await collection.find_one(
                            {"username": {"$regex": f"^{re.escape(username)}$", "$options": "i"}, "group_ids": message.chat.id}
                        )
                        if user_data:
                            target_user_id = user_data["user_id"]
                            logger.info(f"Найден пользователь по username={username}, user_id={target_user_id}")
                        else:
                            logger.warning(f"Пользователь с username={username} не найден в chat_id={message.chat.id}")
                            return None, None, None
            if for_unmute or message.text.startswith('/clear_warnings'):
                return target_user_id, None, None
            reason = ' '.join(remaining_args) if remaining_args else "Не указана"
            if message.text.startswith('/mute'):
                duration = remaining_args[0] if remaining_args and remaining_args[0].isdigit() else None
                reason = ' '.join(remaining_args[1:]) if len(remaining_args) > 1 else "Не указана"
        else:
            user_data = await collection.find_one(
                {"display_name": first_arg, "group_ids": message.chat.id}
            )
            if not user_data:
                normalized_name = await normalize_name(first_arg)
                user_data = await collection.find_one(
                    {"display_name": {"$regex": f"^{re.escape(normalized_name)}$", "$options": "i"}, "group_ids": message.chat.id}
                )
            if not user_data:
                partial_name = ' '.join(first_arg.split())
                user_data = await collection.find_one(
                    {"display_name": {"$regex": f"^{re.escape(partial_name)}", "$options": "i"}, "group_ids": message.chat.id}
                )
            if user_data:
                target_user_id = user_data["user_id"]
                logger.info(f"Найден пользователь по display_name={first_arg}, user_id={target_user_id}")
                if for_unmute or message.text.startswith('/clear_warnings'):
                    return target_user_id, None, None
                reason = ' '.join(remaining_args) if remaining_args else "Не указана"
                if message.text.startswith('/mute'):
                    duration = remaining_args[0] if remaining_args and remaining_args[0].isdigit() else None
                    reason = ' '.join(remaining_args[1:]) if len(remaining_args) > 1 else "Не указана"
            else:
                logger.warning(f"Пользователь с display_name={first_arg} или normalized={await normalize_name(first_arg)} или partial={' '.join(first_arg.split())} не найден в chat_id={message.chat.id}")
                return None, None, None

    logger.debug(f"Извлечено: user_id={target_user_id}, duration={duration}, reason={reason}")
    return target_user_id, duration, reason

@router.message(Command(commands=["warn"]))
async def warn_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /warn от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 1, chat_id, "/warn"):
        return
    if not await check_bot_permissions(message, {"can_restrict_members": True}):
        return

    target_user_id, _, reason = await extract_user_id(message)  # noqa: F841 для duration
    if not target_user_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")]
        ])
        await message.answer(
            "⚠️ Пользователь не найден в чате или базе данных. Проверьте @username, имя или используйте user_id. "
            "Используйте /list_users для списка участников.\n"
            "📋 Пример: `/warn @Username спам`, `/warn 🦈⃤ҔᴀнЧᴀнk спам`, `/warn 123456789 спам`",
            reply_markup=keyboard
        )
        logger.warning(f"Пользователь не найден для команды /warn от user_id={user_id}, chat_id={chat_id}, команда: {message.text}")
        return

    try:
        target_user = await get_user(target_user_id, create_if_not_exists=True, chat_id=chat_id)
    except ValueError:
        await message.answer("🚫 Пользователь не найден в базе данных.")
        logger.warning(f"Пользователь {target_user_id} не найден в базе данных для команды /warn, chat_id={chat_id}")
        return
    if target_user_id == OWNER_BOT_ID or target_user.role_level >= user.role_level:
        await message.answer("🚫 Нельзя выдать предупреждение владельцу бота или пользователю с равной/высшей ролью.")
        logger.warning(
            f"Пользователь {user_id} попытался выдать предупреждение {target_user_id} с равной/высшей ролью в chat_id={chat_id}")
        return

    success = await add_warning(target_user_id, chat_id, reason, user_id)
    if not success:
        await message.answer("🚫 Не удалось выдать предупреждение. Попробуйте снова.")
        logger.error(f"Не удалось добавить предупреждение для user_id={target_user_id}, chat_id={chat_id}")
        return

    target_user = await get_user(target_user_id, create_if_not_exists=False, chat_id=chat_id)
    warnings_count = len(target_user.warnings.get(str(chat_id), []))
    response = (
        f"⚠️ Пользователю **{target_user.display_name or target_user_id}** выдано предупреждение.\n"
        f"📝 Причина: {reason}\n"
        f"🔢 Всего предупреждений: {warnings_count}"
    )
    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"⚠️ Вы получили предупреждение в чате **{message.chat.title}**.\n"
                f"📝 Причина: {reason}\n"
                f"🔢 Всего предупреждений: {warnings_count}"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📩 Начать диалог с ботом", url=f"tg://user?id={message.bot.id}")]
            ])
        )
        logger.info(f"Уведомление успешно отправлено пользователю {target_user_id}")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        if "bot can't initiate conversation with a user" in str(e):
            response += (
                "\n📩 Уведомление не отправлено: пользователь не начинал диалог с ботом. "
                "Для получения уведомлений отправьте /start боту."
            )
            logger.info(f"Уведомление не отправлено пользователю {target_user_id}: пользователь не начинал диалог")
        else:
            response += f"\n📩 Не удалось отправить уведомление: {str(e)}"
            logger.error(f"Ошибка отправки уведомления пользователю {target_user_id}: {str(e)}")
    await message.answer(response)
    logger.info(
        f"Пользователь {user_id} выдал предупреждение {target_user_id} в chat_id={chat_id}, причина: {reason}")

@router.message(Command(commands=["clear_warnings"]))
async def clear_warnings_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /clear_warnings от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 2, chat_id, "/clear_warnings"):
        return
    if not await check_bot_permissions(message, {"can_restrict_members": True}):
        return

    target_user_id, _, _ = await extract_user_id(message, for_unmute=True)  # noqa: F841
    if not target_user_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")]
        ])
        await message.answer(
            "⚠️ Пользователь не найден в чате или базе данных. Проверьте @username, имя или используйте user_id. "
            "Используйте /list_users для списка участников.\n"
            "📋 Пример: `/clear_warnings @Username`, `/clear_warnings 🦈⃤ҔᴀнЧᴀнk`",
            reply_markup=keyboard
        )
        logger.warning(f"Пользователь не найден для команды /clear_warnings от user_id={user_id}, chat_id={chat_id}, команда: {message.text}")
        return

    try:
        target_user = await get_user(target_user_id, create_if_not_exists=True, chat_id=chat_id)
    except ValueError:
        await message.answer("🚫 Пользователь не найден в базе данных.")
        logger.warning(f"Пользователь {target_user_id} не найден в базе данных для команды /clear_warnings, chat_id={chat_id}")
        return

    success = await clear_warnings(target_user_id, chat_id, user_id)
    if not success:
        await message.answer("🚫 Не удалось очистить предупреждения. Возможно, их нет.")
        logger.error(f"Не удалось очистить предупреждения для user_id={target_user_id}, chat_id={chat_id}")
        return

    response = f"🧹 Предупреждения пользователя **{target_user.display_name or target_user_id}** очищены."
    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=f"🧹 Ваши предупреждения в чате **{message.chat.title}** были очищены.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📩 Начать диалог с ботом", url=f"tg://user?id={message.bot.id}")]
            ])
        )
        logger.info(f"Уведомление успешно отправлено пользователю {target_user_id}")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        if "bot can't initiate conversation with a user" in str(e):
            response += (
                "\n📩 Уведомление не отправлено: пользователь не начинал диалог с ботом. "
                "Для получения уведомлений отправьте /start боту."
            )
            logger.info(f"Уведомление не отправлено пользователю {target_user_id}: пользователь не начинал диалог")
        else:
            response += f"\n📩 Не удалось отправить уведомление: {str(e)}"
            logger.error(f"Ошибка отправки уведомления пользователю {target_user_id}: {str(e)}")
    await message.answer(response)
    logger.info(f"Пользователь {user_id} очистил предупреждения {target_user_id} в chat_id={chat_id}")

@router.message(Command(commands=["clear"]))
async def clear_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /clear от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 1, chat_id, "/clear"):
        return
    if not await check_bot_permissions(message, {"can_delete_messages": True}):
        return

    if message.reply_to_message:
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=message.reply_to_message.message_id)
            await message.answer("🗑️ Сообщение удалено.")
            logger.info(
                f"Пользователь {user_id} удалил сообщение {message.reply_to_message.message_id} в chat_id={chat_id}")
        except TelegramBadRequest:
            await message.answer("🚫 Не удалось удалить сообщение. Возможно, оно уже удалено.")
            logger.warning(f"Не удалось удалить сообщение {message.reply_to_message.message_id} в chat_id={chat_id}")
        return

    args = message.text.split(maxsplit=1)
    clean_args = [re.sub(r'[<>[\]]', '', arg) for arg in args[1:]] if len(args) > 1 else []
    if not clean_args or not clean_args[0].isdigit():
        await message.answer(
            "🗑️ Укажите количество сообщений для удаления:\n"
            "📋 Пример: `/clear 10` или ответить на сообщение."
        )
        logger.warning(f"Неверный формат команды /clear от user_id={user_id}, chat_id={chat_id}")
        return
    count = int(clean_args[0])
    if count < 1 or count > 100:
        await message.answer("🚫 Укажите количество от 1 до 100 сообщений.")
        logger.warning(f"Недопустимое количество сообщений ({count}) в команде /clear от user_id={user_id}, chat_id={chat_id}")
        return

    current_message_id = message.message_id
    deleted = 0
    for i in range(current_message_id - count, current_message_id):
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=i)
            deleted += 1
        except TelegramBadRequest:
            continue
    await message.answer(f"🗑️ Удалено {deleted} сообщений.")
    logger.info(f"Пользователь {user_id} удалил {deleted} сообщений в chat_id={chat_id}")

@router.message(Command(commands=["mute"]))
async def mute_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /mute от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 2, chat_id, "/mute"):
        return
    if not await check_bot_permissions(message, {"can_restrict_members": True}):
        return

    target_user_id, duration_str, reason = await extract_user_id(message)
    if not target_user_id or not duration_str:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")]
        ])
        await message.answer(
            "🔇 Пользователь или длительность не указаны. Укажите корректный user_id, @username, имя и длительность в минутах. "
            "Используйте /list_users для списка участников.\n"
            "📋 Пример: `/mute @Username 10 спам`, `/mute 🦈⃤ҔᴀнЧᴀнk 30 нарушил правила`",
            reply_markup=keyboard
        )
        logger.warning(f"Пользователь не найден или неверный формат команды /mute от user_id={user_id}, chat_id={chat_id}, команда: {message.text}")
        return

    try:
        duration = float(duration_str) * 60
    except ValueError:
        await message.answer(
            "🚫 Длительность должна быть числом в минутах.\n"
            "📋 Пример: `/mute 🦈⃤ҔᴀнЧᴀнk 10 спам`"
        )
        logger.warning(f"Недопустимая длительность ({duration_str}) в команде /mute от user_id={user_id}, chat_id={chat_id}")
        return

    try:
        target_user = await get_user(target_user_id, create_if_not_exists=True, chat_id=chat_id)
    except ValueError:
        await message.answer("🚫 Пользователь не найден в базе данных.")
        logger.warning(f"Пользователь {target_user_id} не найден в базе данных для команды /mute, chat_id={chat_id}")
        return
    if target_user_id == OWNER_BOT_ID or target_user.role_level >= user.role_level:
        await message.answer("🚫 Нельзя замутить владельца бота или пользователя с равной/высшей ролью.")
        logger.warning(
            f"Пользователь {user_id} попытался замутить {target_user_id} с равной/высшей ролью в chat_id={chat_id}")
        return

    ban_info = target_user.bans.get(str(chat_id), {"is_banned": False})
    if ban_info["is_banned"]:
        await message.answer(
            f"🚫 Пользователь **{target_user.display_name or target_user_id}** забанен. Сначала используйте `/unban`."
        )
        logger.warning(f"Попытка мута забаненного пользователя {target_user_id} в chat_id={chat_id}")
        return

    until_date = int(time.time() + duration)
    await message.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=target_user_id,
        permissions={"can_send_messages": False},
        until_date=until_date
    )
    success = await mute_user(target_user_id, chat_id, duration, reason, user_id)
    if not success:
        await message.answer("🚫 Не удалось замутить пользователя. Попробуйте снова.")
        logger.error(f"Не удалось замутить user_id={target_user_id}, chat_id={chat_id}")
        return

    response = (
        f"🔇 Пользователь **{target_user.display_name or target_user_id}** замучен на **{duration_str} минут**.\n"
        f"📝 Причина: {reason}"
    )
    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🔇 Вы замучены в чате **{message.chat.title}** на **{duration_str} минут**.\n"
                f"📝 Причина: {reason}"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📩 Начать диалог с ботом", url=f"tg://user?id={message.bot.id}")]
            ])
        )
        logger.info(f"Уведомление успешно отправлено пользователю {target_user_id}")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        if "bot can't initiate conversation with a user" in str(e):
            response += (
                "\n📩 Уведомление не отправлено: пользователь не начинал диалог с ботом. "
                "Для получения уведомлений отправьте /start боту."
            )
            logger.info(f"Уведомление не отправлено пользователю {target_user_id}: пользователь не начинал диалог")
        else:
            response += f"\n📩 Не удалось отправить уведомление: {str(e)}"
            logger.error(f"Ошибка отправки уведомления пользователю {target_user_id}: {str(e)}")
    await message.answer(response)
    logger.info(
        f"Пользователь {user_id} замучил {target_user_id} в chat_id={chat_id} на {duration_str} минут, причина: {reason}")

@router.message(Command(commands=["unmute"]))
async def unmute_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /unmute от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 2, chat_id, "/unmute"):
        return
    if not await check_bot_permissions(message, {"can_restrict_members": True}):
        return

    target_user_id, _, _ = await extract_user_id(message, for_unmute=True)  # noqa: F841
    if not target_user_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")]
        ])
        await message.answer(
            "🔊 Пользователь не найден в чате или базе данных. Проверьте @username, имя или используйте user_id. "
            "Используйте /list_users для списка участников.\n"
            "📋 Пример: `/unmute @Username`, `/unmute 🦈⃤ҔᴀнЧᴀнk`",
            reply_markup=keyboard
        )
        logger.warning(f"Пользователь не найден для команды /unmute от user_id={user_id}, chat_id={chat_id}, команда: {message.text}")
        return

    try:
        target_user = await get_user(target_user_id, create_if_not_exists=True, chat_id=chat_id)
    except ValueError:
        await message.answer("🚫 Пользователь не найден в базе данных.")
        logger.warning(f"Пользователь {target_user_id} не найден в базе данных для команды /unmute, chat_id={chat_id}")
        return

    mute_info = target_user.mutes.get(str(chat_id), {"is_muted": False, "until": 0.0})
    if not mute_info["is_muted"] or mute_info["until"] <= time.time():
        await message.answer(f"🔊 Пользователь **{target_user.display_name or target_user_id}** не замучен.")
        logger.info(f"Попытка снять мут с незамученного пользователя {target_user_id} в chat_id={chat_id}")
        return

    ban_info = target_user.bans.get(str(chat_id), {"is_banned": False})
    if ban_info["is_banned"]:
        await message.answer(
            f"🚫 Пользователь **{target_user.display_name or target_user_id}** забанен. Сначала используйте `/unban`."
        )
        logger.warning(f"Попытка снять мут с забаненного пользователя {target_user_id} в chat_id={chat_id}")
        return

    await message.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=target_user_id,
        permissions={
            "can_send_messages": True,
            "can_send_media_messages": True,
            "can_send_polls": True,
            "can_send_other_messages": True,
            "can_add_web_page_previews": True
        }
    )
    success = await unmute_user(target_user_id, chat_id, user_id)
    if not success:
        await message.answer("🚫 Не удалось снять мут. Попробуйте снова.")
        logger.error(f"Не удалось снять мут с user_id={target_user_id}, chat_id={chat_id}")
        return

    response = f"🔊 Мут снят с пользователя **{target_user.display_name or target_user_id}**."
    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=f"🔊 Ваш мут в чате **{message.chat.title}** снят.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📩 Начать диалог с ботом", url=f"tg://user?id={message.bot.id}")]
            ])
        )
        logger.info(f"Уведомление успешно отправлено пользователю {target_user_id}")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        if "bot can't initiate conversation with a user" in str(e):
            response += (
                "\n📩 Уведомление не отправлено: пользователь не начинал диалог с ботом. "
                "Для получения уведомлений отправьте /start боту."
            )
            logger.info(f"Уведомление не отправлено пользователю {target_user_id}: пользователь не начинал диалог")
        else:
            response += f"\n📩 Не удалось отправить уведомление: {str(e)}"
            logger.error(f"Ошибка отправки уведомления пользователю {target_user_id}: {str(e)}")
    await message.answer(response)
    logger.info(f"Пользователь {user_id} снял мут с {target_user_id} в chat_id={chat_id}")

@router.message(Command(commands=["ban"]))
async def ban_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /ban от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 3, chat_id, "/ban"):
        return
    if not await check_bot_permissions(message, {"can_restrict_members": True}):
        return

    target_user_id, duration_str, reason = await extract_user_id(message)
    if not target_user_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")]
        ])
        await message.answer(
            "🚫 Пользователь не найден в чате или базе данных. Проверьте @username, имя или используйте user_id. "
            "Используйте /list_users для списка участников.\n"
            "📋 Пример: `/ban @Username 60 спам`, `/ban 🦈⃤ҔᴀнЧᴀнk нарушил правила`",
            reply_markup=keyboard
        )
        logger.warning(f"Пользователь не найден для команды /ban от user_id={user_id}, chat_id={chat_id}, команда: {message.text}")
        return

    try:
        target_user = await get_user(target_user_id, create_if_not_exists=True, chat_id=chat_id)
    except ValueError:
        await message.answer("🚫 Пользователь не найден в базе данных.")
        logger.warning(f"Пользователь {target_user_id} не найден в базе данных для команды /ban, chat_id={chat_id}")
        return
    if target_user_id == OWNER_BOT_ID or target_user.role_level >= user.role_level:
        await message.answer("🚫 Нельзя забанить владельца бота или пользователя с равной/высшей ролью.")
        logger.warning(
            f"Пользователь {user_id} попытался забанить {target_user_id} с равной/высшей ролью в chat_id={chat_id}")
        return

    until_date = None
    if duration_str and duration_str.isdigit():
        duration = float(duration_str) * 60
        until_date = int(time.time() + duration)

    await message.bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id, until_date=until_date)
    success = await ban_user(target_user_id, chat_id, reason, user_id, until_date=until_date)
    if not success:
        await message.answer("🚫 Не удалось забанить пользователя. Попробуйте снова.")
        logger.error(f"Не удалось забанить user_id={target_user_id}, chat_id={chat_id}")
        return

    duration_text = f" на **{duration_str} минут**" if until_date else ""
    response = (
        f"🚫 Пользователь **{target_user.display_name or target_user_id}** забанен{duration_text}.\n"
        f"📝 Причина: {reason}"
    )
    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🚫 Вы забанены в чате **{message.chat.title}**{duration_text}.\n"
                f"📝 Причина: {reason}"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📩 Начать диалог с ботом", url=f"tg://user?id={message.bot.id}")]
            ])
        )
        logger.info(f"Уведомление успешно отправлено пользователю {target_user_id}")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        if "bot can't initiate conversation with a user" in str(e):
            response += (
                "\n📩 Уведомление не отправлено: пользователь не начинал диалог с ботом. "
                "Для получения уведомлений отправьте /start боту."
            )
            logger.info(f"Уведомление не отправлено пользователю {target_user_id}: пользователь не начинал диалог")
        else:
            response += f"\n📩 Не удалось отправить уведомление: {str(e)}"
            logger.error(f"Ошибка отправки уведомления пользователю {target_user_id}: {str(e)}")
    await message.answer(response)
    logger.info(f"Пользователь {user_id} забанил {target_user_id} в chat_id={chat_id}{duration_text}, причина: {reason}")

@router.message(Command(commands=["unban"]))
async def unban_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /unban от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 4, chat_id, "/unban"):
        return
    if not await check_bot_permissions(message, {"can_restrict_members": True}):
        return

    target_user_id, _, _ = await extract_user_id(message, for_unmute=True)  # noqa: F841
    if not target_user_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")]
        ])
        await message.answer(
            "✅ Пользователь не найден в чате или базе данных. Проверьте @username, имя или используйте user_id. "
            "Используйте /list_users для списка участников.\n"
            "📋 Пример: `/unban @Username`, `/unban 🦈⃤ҔᴀнЧᴀнk`",
            reply_markup=keyboard
        )
        logger.warning(f"Пользователь не найден для команды /unban от user_id={user_id}, chat_id={chat_id}, команда: {message.text}")
        return

    try:
        target_user = await get_user(target_user_id, create_if_not_exists=True, chat_id=chat_id)
    except ValueError:
        await message.answer("🚫 Пользователь не найден в базе данных.")
        logger.warning(f"Пользователь {target_user_id} не найден в базе данных для команды /unban, chat_id={chat_id}")
        return

    ban_info = target_user.bans.get(str(chat_id), {"is_banned": False})
    if not ban_info["is_banned"]:
        await message.answer(f"✅ Пользователь **{target_user.display_name or target_user_id}** не забанен.")
        logger.info(f"Попытка разбанить незабаненного пользователя {target_user_id} в chat_id={chat_id}")
        return

    await message.bot.unban_chat_member(chat_id=chat_id, user_id=target_user_id)
    success = await unban_user(target_user_id, chat_id, user_id)
    if not success:
        await message.answer("🚫 Не удалось разбанить пользователя. Попробуйте снова.")
        logger.error(f"Не удалось разбанить user_id={target_user_id}, chat_id={chat_id}")
        return

    response = f"✅ Пользователь **{target_user.display_name or target_user_id}** разбанен."
    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=f"✅ Ваш бан в чате **{message.chat.title}** снят.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📩 Начать диалог с ботом", url=f"tg://user?id={message.bot.id}")]
            ])
        )
        logger.info(f"Уведомление успешно отправлено пользователю {target_user_id}")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        if "bot can't initiate conversation with a user" in str(e):
            response += (
                "\n📩 Уведомление не отправлено: пользователь не начинал диалог с ботом. "
                "Для получения уведомлений отправьте /start боту."
            )
            logger.info(f"Уведомление не отправлено пользователю {target_user_id}: пользователь не начинал диалог")
        else:
            response += f"\n📩 Не удалось отправить уведомление: {str(e)}"
            logger.error(f"Ошибка отправки уведомления пользователю {target_user_id}: {str(e)}")
    await message.answer(response)
    logger.info(f"Пользователь {user_id} разбанил {target_user_id} в chat_id={chat_id}")

@router.message(Command(commands=["kick"]))
async def kick_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /kick от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 3, chat_id, "/kick"):
        return
    if not await check_bot_permissions(message, {"can_restrict_members": True}):
        return

    target_user_id, _, reason = await extract_user_id(message)  # noqa: F841
    if not target_user_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")]
        ])
        await message.answer(
            "👢 Пользователь не найден в чате или базе данных. Проверьте @username, имя или используйте user_id. "
            "Используйте /list_users для списка участников.\n"
            "📋 Пример: `/kick @Username спам`, `/kick 🦈⃤ҔᴀнЧᴀнk нарушил правила`",
            reply_markup=keyboard
        )
        logger.warning(f"Пользователь не найден для команды /kick от user_id={user_id}, chat_id={chat_id}, команда: {message.text}")
        return

    try:
        target_user = await get_user(target_user_id, create_if_not_exists=True, chat_id=chat_id)
    except ValueError:
        await message.answer("🚫 Пользователь не найден в базе данных.")
        logger.warning(f"Пользователь {target_user_id} не найден в базе данных для команды /kick, chat_id={chat_id}")
        return
    if target_user_id == OWNER_BOT_ID or target_user.role_level >= user.role_level:
        await message.answer("🚫 Нельзя исключить владельца бота или пользователя с равной/высшей ролью.")
        logger.warning(
            f"Пользователь {user_id} попытался исключить {target_user_id} с равной/высшей ролью в chat_id={chat_id}")
        return

    await message.bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id)
    await message.bot.unban_chat_member(chat_id=chat_id, user_id=target_user_id)
    await log_moderation_action(target_user_id, chat_id, "kick", reason, user_id)
    response = (
        f"👢 Пользователь **{target_user.display_name or target_user_id}** исключен из чата.\n"
        f"📝 Причина: {reason}"
    )
    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"👢 Вы были исключены из чата **{message.chat.title}**.\n"
                f"📝 Причина: {reason}"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📩 Начать диалог с ботом", url=f"tg://user?id={message.bot.id}")]
            ])
        )
        logger.info(f"Уведомление успешно отправлено пользователю {target_user_id}")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        if "bot can't initiate conversation with a user" in str(e):
            response += (
                "\n📩 Уведомление не отправлено: пользователь не начинал диалог с ботом. "
                "Для получения уведомлений отправьте /start боту."
            )
            logger.info(f"Уведомление не отправлено пользователю {target_user_id}: пользователь не начинал диалог")
        else:
            response += f"\n📩 Не удалось отправить уведомление: {str(e)}"
            logger.error(f"Ошибка отправки уведомления пользователю {target_user_id}: {str(e)}")
    await message.answer(response)
    logger.info(f"Пользователь {user_id} исключил {target_user_id} из chat_id={chat_id}, причина: {reason}")

@router.message(Command(commands=["user_status"]))
async def user_status_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /user_status от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 3, chat_id, "/user_status"):
        return

    target_user_id, _, _ = await extract_user_id(message, for_unmute=True)  # noqa: F841
    if not target_user_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")]
        ])
        await message.answer(
            "📊 Пользователь не найден в чате или базе данных. Проверьте @username, имя или используйте user_id. "
            "Используйте /list_users для списка участников.\n"
            "📋 Пример: `/user_status @Username`, `/user_status 🦈⃤ҔᴀнЧᴀнk`",
            reply_markup=keyboard
        )
        logger.warning(f"Пользователь не найден для команды /user_status от user_id={user_id}, chat_id={chat_id}, команда: {message.text}")
        return

    try:
        target_user = await get_user(target_user_id, create_if_not_exists=True, chat_id=chat_id)
    except ValueError:
        await message.answer("🚫 Пользователь не найден в базе данных.")
        logger.warning(f"Пользователь {target_user_id} не найден в базе данных для команды /user_status, chat_id={chat_id}")
        return

    warnings = target_user.warnings.get(str(chat_id), [])
    ban_info = target_user.bans.get(str(chat_id), {"is_banned": False, "reason": "", "issued_by": 0, "issued_at": 0.0, "until": 0.0})
    mute_info = target_user.mutes.get(str(chat_id), {"is_muted": False, "until": 0.0, "reason": "", "issued_by": 0, "issued_at": 0.0})

    response = (
        f"📊 **Статус пользователя {target_user.display_name or target_user_id}**:\n\n"
        f"🎭 **Роль**: {target_user.get_role_for_chat(chat_id)}\n"
        f"📈 **Активность**: {target_user.get_activity_count(chat_id)} сообщений\n"
        f"⚠️ **Предупреждений**: {len(warnings)}\n"
    )
    if warnings:
        response += "📜 **Предупреждения**:\n" + "\n".join(
            f"  • {w['reason']} (выдано {w['issued_by']} в {time.ctime(w['issued_at'])})"
            for w in warnings
        ) + "\n"
    response += f"🚫 **Бан**: {'Да' if ban_info['is_banned'] and (not ban_info.get('until') or ban_info['until'] > time.time()) else 'Нет'}\n"
    if ban_info["is_banned"]:
        duration_text = f" до {time.ctime(ban_info['until'])}" if ban_info.get("until") else ""
        response += f"  📝 Причина бана: {ban_info['reason']}\n"
        response += f"  👤 Выдано: {ban_info['issued_by']} в {time.ctime(ban_info['issued_at'])}{duration_text}\n"
    response += f"🔇 **Мут**: {'Да' if mute_info['is_muted'] and mute_info['until'] > time.time() else 'Нет'}\n"
    if mute_info["is_muted"] and mute_info["until"] > time.time():
        response += f"  📝 Причина мута: {mute_info['reason']}\n"
        response += f"  👤 Выдано: {mute_info['issued_by']} в {time.ctime(mute_info['issued_at'])}\n"
        response += f"  ⏰ До: {time.ctime(mute_info['until'])}"

    await message.answer(response)
    logger.info(f"Пользователь {user_id} запросил статус {target_user_id} в chat_id={chat_id}")

@router.message(Command(commands=["mod_logs"]))
async def mod_logs_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /mod_logs от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 2, chat_id, "/mod_logs"):
        return

    logs = await get_moderation_logs(chat_id, limit=10)
    if not logs:
        await message.answer("📜 Логи модерации отсутствуют.")
        logger.info(f"Логи модерации для chat_id={chat_id} пусты")
        return

    response = "📜 **Последние действия модерации**:\n\n"
    for log in logs:
        target_user = await get_user(log["user_id"], create_if_not_exists=False)
        issued_by_user = await get_user(log["issued_by"], create_if_not_exists=False)
        action_text = {
            "warn": "⚠️ Предупреждение",
            "clear_warnings": "🧹 Очистка предупреждений",
            "mute": f"🔇 Мут{' на ' + str(log.get('duration', 0) / 60) + ' минут' if log.get('duration') is not None else ''}",
            "unmute": "🔊 Снятие мута",
            "ban": f"🚫 Бан{' на ' + str(log.get('duration', 0) / 60) + ' минут' if log.get('until_date') and log.get('duration') is not None else ''}",
            "unban": "✅ Снятие бана",
            "kick": "👢 Исключение"
        }.get(log["action"], log["action"])
        response += (
            f"🔸 **{action_text}**\n"
            f"👤 Пользователь: {target_user.display_name or log['user_id']}\n"
            f"📝 Причина: {log['reason']}\n"
            f"🕒 Выдано: {issued_by_user.display_name or log['issued_by']} в {time.ctime(log['issued_at'])}\n\n"
        )
    await message.answer(response)
    logger.info(f"Пользователь {user_id} запросил логи модерации для chat_id={chat_id}")

@router.message(Command(commands=["list_users"]))
async def list_users_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /list_users от user_id={user_id}, chat_id={chat_id}, текст: {message.text}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 1, chat_id, "/list_users"):
        return

    collection = await get_user_collection()
    users = await collection.find({"group_ids": chat_id}, {"display_name": 1, "user_id": 1, "username": 1}).to_list(length=100)
    if not users:
        await message.answer("📋 В чате нет зарегистрированных пользователей.")
        logger.info(f"Список пользователей для chat_id={chat_id} пуст")
        return

    response = "📋 **Список пользователей в чате**:\n\n"
    for user in users:
        response += f"👤 {user.get('display_name', user['user_id'])} (@{user.get('username', 'нет')} | ID: {user['user_id']})\n"
    await message.answer(response)
    logger.info(f"Пользователь {user_id} запросил список пользователей для chat_id={chat_id}")

@router.message(Command(commands=["help_moderation"]))
async def help_moderation_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /help_moderation от user_id={user_id}, chat_id={chat_id}")
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if not await check_permissions(message, user, 1, chat_id, "/help_moderation"):
        return

    help_text = (
        "📜 **Модераторские команды**:\n\n"
        f"🔸 **/warn <user_id | @username | имя> [причина]** — Выдать предупреждение (роль: **{ROLE_NAMES[1]}**).\n"
        "  📋 Пример: `/warn @Username спам`, `/warn 🦈⃤ҔᴀнЧᴀнk спам`, `/warn 123456789 спам`\n\n"
        f"🔸 **/clear_warnings <user_id | @username | имя>** — Очистить предупреждения (роль: **{ROLE_NAMES[2]}**).\n"
        "  📋 Пример: `/clear_warnings @Username`, `/clear_warnings 🦈⃤ҔᴀнЧᴀнk`\n\n"
        f"🔸 **/clear <количество> | reply** — Удалить сообщения (роль: **{ROLE_NAMES[1]}**).\n"
        "  📋 Пример: `/clear 10` или ответить на сообщение\n\n"
        f"🔸 **/mute <user_id | @username | имя> <длительность_в_минутах> [причина]** — Замутить пользователя (роль: **{ROLE_NAMES[2]}**).\n"
        "  📋 Пример: `/mute @Username 10 спам`, `/mute 🦈⃤ҔᴀнЧᴀнk 30 нарушил правила`\n\n"
        f"🔸 **/unmute <user_id | @username | имя>** — Снять мут (роль: **{ROLE_NAMES[2]}**).\n"
        "  📋 Пример: `/unmute @Username`, `/unmute 🦈⃤ҔᴀнЧᴀнk`\n\n"
        f"🔸 **/ban <user_id | @username | имя> [длительность_в_минутах] [причина]** — Забанить пользователя (роль: **{ROLE_NAMES[3]}**).\n"
        "  📋 Пример: `/ban @Username 60 спам`, `/ban 🦈⃤ҔᴀнЧᴀнk нарушил правила`\n\n"
        f"🔸 **/unban <user_id | @username | имя>** — Разбанить пользователя (роль: **{ROLE_NAMES[4]}**).\n"
        "  📋 Пример: `/unban @Username`, `/unban 🦈⃤ҔᴀнЧᴀнk`\n\n"
        f"🔸 **/kick <user_id | @username | имя> [причина]** — Исключить пользователя (роль: **{ROLE_NAMES[3]}**).\n"
        "  📋 Пример: `/kick @Username спам`, `/kick 🦈⃤ҔᴀнЧᴀнk нарушил правила`\n\n"
        f"🔸 **/user_status <user_id | @username | имя>** — Показать статус пользователя (роль: **{ROLE_NAMES[3]}**).\n"
        "  📋 Пример: `/user_status @Username`, `/user_status 🦈⃤ҔᴀнЧᴀнk`\n\n"
        f"🔸 **/mod_logs** — Показать последние действия модерации (роль: **{ROLE_NAMES[2]}**).\n"
        "  📋 Пример: `/mod_logs`\n\n"
        f"🔸 **/list_users** — Показать список пользователей чата (роль: **{ROLE_NAMES[1]}**).\n"
        "  📋 Пример: `/list_users`\n\n"
        "📌 Укажите пользователя через user_id, @username, имя или ответьте на сообщение."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Проверить статус", callback_data="user_status"),
            InlineKeyboardButton(text="📜 Логи модерации", callback_data="mod_logs"),
            InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")
        ]
    ])
    await message.answer(help_text, reply_markup=keyboard)
    logger.info(f"Пользователь {user_id} запросил помощь по модераторским командам в chat_id={chat_id}")

async def get_user_collection() -> AsyncIOMotorCollection:
    from ..modules.no_sql.mongo_client import get_database
    db = await get_database()
    return db["users"]