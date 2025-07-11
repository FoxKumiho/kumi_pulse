from aiogram import Router, F
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from loguru import logger
import aiogram
from ..modules.no_sql.user_db import register_chat_member, get_user, save_chat, OWNER_BOT_ID, get_all_user_ids, \
    increment_activity_count, get_moderation_logs
from .antispam import check_spam
import time

# Используем aiogram версии 3.20.0.post0
assert aiogram.__version__ == "3.20.0.post0", f"Expected aiogram version 3.20.0.post0, but found {aiogram.__version__}"

router = Router()

@router.message(Command(commands=["start"]))
async def start_handler(message: Message):
    """
    Обработчик команды /start. Регистрирует пользователя и приветствует его.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.debug(f"Обработка команды /start от user_id={user_id}, chat_id={chat_id}")
    try:
        await register_chat_member(
            user_id=user_id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
            chat_id=chat_id,
            is_bot=message.from_user.is_bot
        )
        await message.answer(
            f"Привет, {message.from_user.full_name}! Я бот Kumi Pulse. "
            "Используй /help_moderation для списка модераторских команд, если у тебя есть права."
        )
        logger.info(f"Пользователь {user_id} успешно зарегистрирован через /start в chat_id={chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /start для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        await message.answer("Произошла ошибка. Попробуйте позже или свяжитесь с поддержкой.")

@router.message(F.new_chat_members)
async def new_member_handler(message: Message):
    """
    Обработчик новых участников чата. Регистрирует их в базе данных.
    """
    chat_id = message.chat.id
    try:
        for member in message.new_chat_members:
            await register_chat_member(
                user_id=member.id,
                username=member.username,
                display_name=member.full_name,
                chat_id=chat_id,
                is_bot=member.is_bot
            )
            logger.info(f"Добавлен участник {member.id} (is_bot={member.is_bot}) в group_ids для chat_id={chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при регистрации новых участников в chat_id={chat_id}: {str(e)}")

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added_to_chat_handler(update: ChatMemberUpdated):
    """
    Обработчик добавления бота в чат. Сохраняет chat_id и регистрирует всех доступных участников.
    """
    chat_id = update.chat.id
    chat_title = update.chat.title
    try:
        bot_member = await update.bot.get_chat_member(chat_id=chat_id, user_id=update.bot.id)
        if bot_member.status != "administrator" or not bot_member.can_manage_chat:
            logger.warning(f"Бот не имеет прав администратора или 'Manage Chat' в chat_id={chat_id}")
            return
        await save_chat(chat_id, chat_title)
        logger.info(f"Бот добавлен в чат: chat_id={chat_id}, chat_title={chat_title}")
        await register_all_chat_members(chat_id, update.bot)
        logger.info(f"Зарегистрированы участники для chat_id={chat_id}")
    except TelegramBadRequest as e:
        logger.error(f"Ошибка при проверке прав бота в chat_id={chat_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении чата или регистрации участников для chat_id={chat_id}: {str(e)}")

@router.message(~Command(commands=["start", "antispam","view_spam_logs", "update_antispam_settings", "reset_spam", "antispam_settings", "set_admin_group", "kick_inactive", "warn", "clear_warnings", "clear", "mute", "unmute", "ban", "unban", "kick", "user_status", "mod_logs", "help_moderation", "register_all", "force_register_all", "spam_stats", "antispam_toggle", "test_antispam"]))
async def message_handler(message: Message):
    """
    Обработчик любых сообщений, кроме команд, для проверки спама и регистрации активности.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    logger.debug(f"Получено сообщение от user_id={user_id}, is_bot={message.from_user.is_bot}, chat_id={chat_id}, message_id={message.message_id}")
    try:
        bot_member = await message.bot.get_chat_member(chat_id=chat_id, user_id=message.bot.id)
        if bot_member.status != "administrator" or not bot_member.can_manage_chat:
            logger.warning(f"Бот не имеет прав администратора или 'Manage Chat' в chat_id={chat_id}, сообщение от user_id={user_id} проигнорировано")
            return

        # Проверка спама
        is_spam = await check_spam(message, message.bot)
        if is_spam:
            logger.info(f"Спам обнаружен для user_id={user_id} в chat_id={chat_id}, обработка сообщения прекращена")
            return

        # Регистрация и увеличение активности
        await register_chat_member(
            user_id=user_id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
            chat_id=chat_id,
            is_bot=message.from_user.is_bot
        )
        if not message.from_user.is_bot:
            success = await increment_activity_count(user_id, chat_id)
            if success:
                updated_user = await get_user(user_id, chat_id=chat_id)
                logger.info(f"Счетчик активности увеличен для user_id={user_id} в chat_id={chat_id}, новый счет: {updated_user.get_activity_count(chat_id)}")
            else:
                logger.warning(f"Не удалось увеличить счетчик активности для user_id={user_id} в chat_id={chat_id}")
        else:
            logger.debug(f"Пропущено увеличение активности для бота: user_id={user_id}, chat_id={chat_id}")
        logger.info(f"Обработано сообщение от user_id={user_id} (is_bot={message.from_user.is_bot}) в chat_id={chat_id}")
    except TelegramBadRequest as e:
        logger.error(f"Ошибка при проверке прав бота или регистрации пользователя {user_id} в chat_id={chat_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения от user_id={user_id} в chat_id={chat_id}: {str(e)}")

async def register_all_chat_members(chat_id: int, bot):
    """
    Регистрирует всех доступных участников чата в базе данных.
    """
    try:
        bot_member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
        if bot_member.status != "administrator" or not bot_member.can_manage_chat:
            logger.warning(f"Бот не имеет прав администратора или 'Manage Chat' в chat_id={chat_id}")
            return
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            await register_chat_member(
                user_id=admin.user.id,
                username=admin.user.username,
                display_name=admin.user.full_name,
                chat_id=chat_id,
                is_bot=admin.user.is_bot
            )
            logger.info(f"Зарегистрирован администратор {admin.user.id} (is_bot={admin.user.is_bot}) для chat_id={chat_id}")

        all_user_ids = await get_all_user_ids()
        for user_id in all_user_ids:
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                if member.status not in ("left", "kicked"):
                    await register_chat_member(
                        user_id=member.user.id,
                        username=member.user.username,
                        display_name=member.user.full_name,
                        chat_id=chat_id,
                        is_bot=member.user.is_bot
                    )
                    logger.info(f"Зарегистрирован участник {member.user.id} (is_bot={member.user.is_bot}) для chat_id={chat_id} через get_chat_member")
            except TelegramBadRequest as e:
                logger.debug(f"Пользователь {user_id} не найден в chat_id={chat_id}: {str(e)}")
                continue
    except TelegramBadRequest as e:
        logger.error(f"Ошибка при получении списка администраторов для chat_id={chat_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Неизвестная ошибка при регистрации участников для chat_id={chat_id}: {str(e)}")
        raise

@router.message(Command(commands=["register_all"]))
async def register_all_handler(message: Message):
    """
    Обработчик команды /register_all. Регистрирует всех администраторов чата.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.role_level < 6 and user.user_id != OWNER_BOT_ID and chat_id not in user.server_owner_chat_ids:
            await message.answer("У вас нет прав для этой команды! Требуется роль Владелец сервера или выше.")
            logger.warning(f"Пользователь {user_id} попытался выполнить /register_all без прав, chat_id={chat_id}")
            return
        await save_chat(chat_id, message.chat.title)
        await register_all_chat_members(chat_id, message.bot)
        await message.answer(
            "Все администраторы чата зарегистрированы. Для регистрации остальных участников они должны быть активны или используйте /force_register_all.")
        logger.info(f"Команда /register_all выполнена для chat_id={chat_id} пользователем {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при выполнении /register_all для chat_id={chat_id}: {str(e)}")
        await message.answer(
            "Произошла ошибка при регистрации администраторов. Проверьте логи или свяжитесь с поддержкой.")

@router.message(Command(commands=["force_register_all"]))
async def force_register_all_handler(message: Message):
    """
    Обработчик команды /force_register_all. Пытается зарегистрировать всех участников чата.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.role_level < 6 and user.user_id != OWNER_BOT_ID and chat_id not in user.server_owner_chat_ids:
            await message.answer("У вас нет прав для этой команды! Требуется роль Владелец сервера или выше.")
            logger.warning(f"Пользователь {user_id} попытался выполнить /force_register_all без прав, chat_id={chat_id}")
            return
        await save_chat(chat_id, message.chat.title)

        chat = await message.bot.get_chat(chat_id)
        member_count = chat.approximate_member_count or 0
        logger.info(f"Попытка регистрации всех участников для chat_id={chat_id}, общее количество: {member_count}")

        await register_all_chat_members(chat_id, message.bot)

        registered_count = 0
        all_user_ids = await get_all_user_ids()
        for user_id in all_user_ids:
            try:
                member = await message.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                if member.status not in ("left", "kicked"):
                    await register_chat_member(
                        user_id=member.user.id,
                        username=member.user.username,
                        display_name=member.user.full_name,
                        chat_id=chat_id,
                        is_bot=member.user.is_bot
                    )
                    registered_count += 1
                    logger.info(f"Зарегистрирован участник {member.user.id} (is_bot={member.user.is_bot}) для chat_id={chat_id} через /force_register_all")
            except TelegramBadRequest:
                continue

        await message.answer(
            f"Зарегистрировано {registered_count} участников. Если не все участники зарегистрированы, убедитесь, что бот имеет права администратора.")
        logger.info(f"Команда /force_register_all выполнена для chat_id={chat_id} пользователем {user_id}, зарегистрировано: {registered_count}")
    except Exception as e:
        logger.error(f"Ошибка при выполнении /force_register_all для chat_id={chat_id}: {str(e)}")
        await message.answer(
            "Произошла ошибка при регистрации участников. Проверьте логи или убедитесь, что бот имеет права администратора.")

@router.callback_query(F.data.in_(["user_status", "mod_logs"]))
async def handle_moderation_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    logger.debug(f"Обработка callback {callback.data} от user_id={user_id}, chat_id={chat_id}")
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.role_level < 1 and user.user_id != OWNER_BOT_ID and chat_id not in user.server_owner_chat_ids:
            await callback.message.answer("🚫 У вас недостаточно прав для выполнения этой команды.")
            logger.warning(f"Пользователь {user_id} попытался использовать callback {callback.data} без прав, chat_id={chat_id}")
            await callback.answer()
            return

        if callback.data == "user_status":
            await callback.message.answer(
                "📊 Укажите пользователя для проверки статуса:\n"
                "📋 Пример: `/user_status @Username` или `/user_status Аристарх`"
            )
        elif callback.data == "mod_logs":
            await callback.message.answer(
                "📜 Для просмотра логов модерации используйте: `/mod_logs`"
            )
        await callback.answer()
        logger.info(f"Callback {callback.data} обработан для user_id={user_id}, chat_id={chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при обработке callback {callback.data} для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        await callback.message.answer("🚫 Ошибка. Попробуйте позже или свяжитесь с поддержкой.")
        await callback.answer()

@router.message(Command("view_spam_logs"))
async def cmd_view_spam_logs(message: Message):
    """Просматривает последние 10 записей логов спама из MongoDB."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.get_role_for_chat(chat_id) not in ["Старший админ", "Заместитель", "Владелец сервера", "Владелец бота"]:
            await message.reply("🚫 У вас нет прав для просмотра логов.")
            return
        logs = await get_moderation_logs(chat_id, limit=10)
        if not logs:
            await message.reply("📜 Логи спама пусты.")
            return
        log_text = []
        for log in logs:
            action = log.get("action", "unknown")
            reason = log.get("reason", "No reason")
            issued_by = log.get("issued_by", 0)
            issued_at = time.ctime(log.get("issued_at", 0))
            user_id = log.get("user_id", "Unknown")
            log_text.append(f"[{issued_at}] User {user_id}: {action} ({reason}) by {issued_by}")
        await message.reply("\n".join(log_text))
        logger.info(f"Пользователь {user_id} просмотрел логи спама для chat_id={chat_id}")
    except Exception as e:
        await message.reply(f"❌ Ошибка при чтении логов: {str(e)}")
        logger.error(f"Ошибка при чтении логов для chat_id={chat_id}: {str(e)}")