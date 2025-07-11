# Путь файла: bot/handlers/antispam.py

from aiogram import F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ChatMemberOwner, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from loguru import logger
import aiogram
import time
import re
import unicodedata
from typing import Optional, Dict
import aiohttp
import asyncio
from ..modules.no_sql.user_db import (
    get_user,
    add_warning,
    mute_user,
    unmute_user,
    ban_user,
    unban_user,
    log_moderation_action,
    OWNER_BOT_ID,
    set_server_owner,
    update_user,
    ensure_user_exists,
    get_moderation_logs
)
from ..modules.no_sql.redis_client import redis_client, get_settings, save_settings, kick_inactive_users, is_spamming, get_ttl, reset_spam_state
import hashlib
from ..keyboards.antispam import get_main_menu, get_filter_menu, get_filter_settings_menu, get_action_menu

# Проверка версии aiogram
assert aiogram.__version__ == "3.20.0.post0", f"Expected aiogram version 3.20.0.post0, but found {aiogram.__version__}"

# Настройка логирования
logger.add("../../../app.log", format="{time} {level} {message}", level="INFO", rotation="10 MB", retention="7 days")

router = Router()

# Определение состояний для FSM
class AntispamStates(StatesGroup):
    main_menu = State()
    select_filter = State()
    set_limit = State()
    set_action = State()
    set_duration = State()
    set_spam_words = State()
    set_exceptions_users = State()
    set_exceptions_domains = State()
    set_admin_group = State()
    set_media_filter = State()
    set_flood_seconds = State()

# Тексты и шаблоны
TEXTS = {
    "main_menu": (
        "📨 <b>Антиспам: Главное меню</b>\n\n"
        "Выберите действие для настройки антиспама.\n"
        "Для назначения админ-группы используйте /set_admin_group."
    ),
    "filter_menu": (
        "⚙️ <b>Настройка фильтров</b>\n\n"
        "Выберите фильтр для настройки."
    ),
    "filter_settings": (
        "⚙️ <b>Настройка фильтра: {}</b>\n\n"
        "Текущие параметры:\n"
        "└ Лимит: {}\n"
        "└ Действие: {}\n"
        "└ Длительность: {}\n"
        "└ Период флуда (сек): {}\n\n"
        "Выберите параметр для изменения."
    ),
    "set_limit": "📏 Введите лимит (например, 5 для повторяющихся слов/сообщений или 10 для флуда).",
    "set_action": "🎯 Выберите действие: удалить, предупредить, мут, бан.",
    "set_duration": (
        "⏱ Введите длительность наказания (от 30 секунд для владельцев сервера/бота).\n"
        "Пример: 3d, 2h, 15m, 30s"
    ),
    "set_flood_seconds": "⏱ Введите период для проверки флуда в секундах (например, 10).",
    "set_spam_words": "🚫 Введите запрещенные слова через запятую (например, viagra,casino).",
    "set_exceptions_users": "👤 Введите ID пользователей для исключения через запятую (например, 123,456).",
    "set_exceptions_domains": "🔗 Введите домены для исключения через запятую (например, example.com,google.com).",
    "set_admin_group": "📢 Введите ID админ-группы (например, -1001234567890).",
    "set_media_filter": "🎥 Включить фильтр медиа? (да/нет)",
    "settings": (
        "⚙️ <b>Настройки антиспама</b>\n\n"
        "📄 Статус: {}\n"
        "🔢 Повторяющиеся слова: {} (действие: {})\n"
        "🔄 Повторяющиеся сообщения: {} (действие: {})\n"
        "⏱ Флуд: {} сообщений/{} сек (действие: {})\n"
        "🚫 Запрещенные слова: {} (действие: {})\n"
        "🔗 Telegram ссылки: {} (действие: {})\n"
        "🔗 Внешние ссылки: {} (действие: {})\n"
        "🎥 Медиа: {} (действие: {})\n"
        "🧹 Автокик неактивных: {}\n"
        "👤 Исключения (пользователи): {}\n"
        "🔗 Исключения (домены): {}\n"
        "📢 Админ-группа: {}\n"
        "📋 Игнорируемые слова: {}\n"
        "⏱ Максимум сообщений в минуту: {}"
    ),
    "success": "✅ Настройки успешно обновлены.",
    "error": "❌ Произошла ошибка. Попробуйте снова.",
    "admin_notification": (
        "🚨 <b>Обнаружен спам</b>\n"
        "Пользователь: {}\n"
        "Чат: {}\n"
        "Причина: {}\n"
        "Действие: {}\n"
        "Сообщение: {}"
    ),
    "reset_spam": "✅ Состояние спама сброшено для пользователя {} в чате {}.",
    "invalid_user": "❌ Пользователь не найден. Укажите корректный ID, @username или username."
}

async def is_chat_owner(bot: Bot, user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь владельцем чата."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if isinstance(member, ChatMemberOwner):
            await set_server_owner(user_id, chat_id)  # Автоматическое назначение роли "Владелец сервера"
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке владельца чата user_id={user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def parse_duration(text: str) -> Optional[int]:
    """Парсит длительность из текста (например, '2d 3h 4m 5s') в секунды."""
    try:
        total_seconds = 0
        matches = re.findall(r"(\d+)\s*([dhms])", text.lower())
        for value, unit in matches:
            value = int(value)
            if unit == "d":
                total_seconds += value * 86400
            elif unit == "h":
                total_seconds += value * 3600
            elif unit == "m":
                total_seconds += value * 60
            elif unit == "s":
                total_seconds += value
        return total_seconds
    except Exception as e:
        logger.error(f"Ошибка при парсинге длительности '{text}': {str(e)}")
        return None

async def check_dnsbl(domain: str) -> bool:
    """Проверяет домен против DNSBL (например, zen.spamhaus.org) асинхронно."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://zen.spamhaus.org/query/dnsbl?domain={domain}") as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"Ошибка при проверке DNSBL для домена {domain}: {str(e)}")
        return False

async def get_message_hash(text: str) -> str:
    """Генерирует хэш сообщения для сравнения."""
    normalized = unicodedata.normalize("NFKC", text.strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()

async def initialize_default_settings(chat_id: str) -> Dict:
    """Инициализирует настройки антиспама по умолчанию."""
    default_settings = {
        "enabled": False,
        "repeated_words": {"limit": 5, "action": "warn", "duration": 1800, "enabled": True},
        "repeated_messages": {"limit": 5, "action": "warn", "duration": 1800, "enabled": True},
        "flood": {"limit": 5, "seconds": 10, "action": "mute", "duration": 1800, "enabled": True},
        "spam_words": {"words": [], "action": "ban", "duration": 86400, "enabled": True},
        "telegram_links": {"enabled": False, "action": "mute", "duration": 1800},
        "external_links": {"enabled": False, "action": "delete", "duration": 0},
        "media_filter": {"enabled": False, "action": "delete", "duration": 0},
        "exceptions": {"users": [], "domains": []},
        "auto_kick_inactive": False,
        "case_sensitive": False,
        "warning_threshold": 3,
        "admin_group": None,
        "max_messages_per_minute": 10,
        "ignored_words": [],
        "ban_duration": 86400,
        "mute_duration": 1800,  # 30 минут по умолчанию
        "action": "warn",
        "repeated_words_limit": 5
    }
    await save_settings("antispam", str(chat_id), default_settings)
    return default_settings

async def retry_on_flood_control(func, *args, max_retries=3, initial_delay=1, **kwargs):
    """Выполняет функцию с повторными попытками при ошибке TooManyRequests."""
    attempt = 0
    delay = initial_delay
    while attempt < max_retries:
        try:
            return await func(*args, **kwargs)
        except TelegramRetryAfter as e:
            logger.warning(f"TooManyRequests: retry after {e.retry_after} секунд, попытка {attempt + 1}/{max_retries}")
            await asyncio.sleep(e.retry_after)
            attempt += 1
            delay *= 2  # Экспоненциальная задержка
        except Exception as e:
            logger.error(f"Ошибка при выполнении {func.__name__}: {str(e)}")
            raise
    logger.error(f"Достигнуто максимальное количество попыток ({max_retries}) для {func.__name__}")
    raise TelegramRetryAfter(f"Max retries reached for {func.__name__}", retry_after=delay)

async def notify_admins(bot: Bot, settings: Dict, user_id: int, chat_id: int, reason: str, action: str, message_text: str):
    """Отправляет уведомление администраторам в admin_group, если она задана."""
    admin_group = settings.get("admin_group")
    if admin_group and isinstance(admin_group, str) and admin_group.startswith("-100"):
        try:
            await bot.get_chat(admin_group)
            user = await get_user(user_id)
            user_mention = f"@{user.username}" if user.username else user.display_name or f"User {user_id}"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подтвердить", callback_data=f"spam_confirm_{user_id}_{chat_id}_{action}")],
                [InlineKeyboardButton(text="Отменить", callback_data=f"spam_cancel_{user_id}_{chat_id}_{action}")]
            ])
            await retry_on_flood_control(
                bot.send_message,
                admin_group,
                TEXTS["admin_notification"].format(
                    user_mention,
                    chat_id,
                    reason,
                    action,
                    message_text[:100] if message_text else "Без текста"
                ),
                reply_markup=keyboard
            )
            logger.info(f"Уведомление отправлено в admin_group={admin_group} для user_id={user_id}, chat_id={chat_id}, action={action}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления в admin_group={admin_group}: {str(e)}")
            return False

async def check_spam(message: Message, bot: Bot) -> bool:
    """Проверяет сообщения на спам и возвращает True, если спам обнаружен и обработан."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text or message.caption or ""
    try:
        await ensure_user_exists(
            user_id=user_id,
            chat_id=chat_id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
            is_bot=message.from_user.is_bot
        )
        settings = await get_settings("antispam", str(chat_id)) or await initialize_default_settings(str(chat_id))
        if not settings.get("enabled", False):
            logger.debug(f"Антиспам отключен для chat_id={chat_id}")
            return False
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        is_exempt = user.get_role_for_chat(chat_id) in ["Владелец сервера", "Владелец бота"] or str(user_id) in settings.get("exceptions", {}).get("users", [])
        if is_exempt:
            logger.debug(f"Пользователь {user_id} исключен из антиспама в chat_id={chat_id}")
            return False
        # Проверка, отправлено ли сообщение от канала
        if message.sender_chat:
            logger.debug(f"Сообщение от канала sender_chat={message.sender_chat.id} в chat_id={chat_id}, антиспам не применяется")
            return False
        # Проверка Telegram-ссылок
        if settings.get("telegram_links", {}).get("enabled", False):
            telegram_pattern = r"(?:https?:\/\/)?(?:t(?:elegram)?\.me|t\.me|tg:\/\/resolve\?domain=|telegram\.me)\/[\w\d_+]+|@[\w\d_]{4,}"
            matches = re.findall(telegram_pattern, text, re.IGNORECASE)
            if matches:
                # Проверка исключений для доменов
                is_domain_exempt = False
                for match in matches:
                    domain = match.lstrip('@').lstrip('https://').lstrip('http://').lstrip('t.me/').lstrip('telegram.me/').lstrip('tg://resolve?domain=')
                    if domain in settings.get("exceptions", {}).get("domains", []):
                        is_domain_exempt = True
                        break
                if not is_domain_exempt:
                    # Удаление сообщения перед применением действия
                    try:
                        await retry_on_flood_control(message.delete)
                        logger.info(f"Удалено сообщение с Telegram-ссылкой от user_id={user_id} в chat_id={chat_id}")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение с Telegram-ссылкой: {str(e)}")
                    logger.info(
                        f"СПАМ/НАРУШЕНИЕ: user_id={user_id}, username=@{user.username or 'Unknown'}, "
                        f"chat_id={chat_id}, причина=Telegram-ссылка: {', '.join(matches)}, "
                        f"действие={settings.get('telegram_links', {}).get('action', settings.get('action', 'mute'))}"
                    )
                    await apply_antispam_action(user_id, chat_id, settings, message, bot, f"Telegram-ссылка: {', '.join(matches)}", "telegram_links")
                    return True
        # Проверка медиа
        if settings.get("media_filter", {}).get("enabled", False) and any([
            message.photo, message.video, message.audio, message.document, message.sticker, message.animation
        ]):
            logger.info(
                f"СПАМ/НАРУШЕНИЕ: user_id={user_id}, username=@{user.username or 'Unknown'}, "
                f"chat_id={chat_id}, причина=Медиа-контент, "
                f"действие={settings.get('media_filter', {}).get('action', settings.get('action', 'delete'))}"
            )
            await apply_antispam_action(user_id, chat_id, settings, message, bot, "Медиа-контент", "media_filter")
            return True
        # Проверка флуда через Redis
        if settings.get("flood", {}).get("enabled", True):
            limit = settings.get("flood", {}).get("limit", settings.get("max_messages_per_minute", 10))
            seconds = settings.get("flood", {}).get("seconds", 10)
            if await is_spamming(chat_id, user_id, limit, seconds):
                ttl = await get_ttl(chat_id, user_id)
                logger.info(
                    f"СПАМ/НАРУШЕНИЕ: user_id={user_id}, username=@{user.username or 'Unknown'}, "
                    f"chat_id={chat_id}, причина=Флуд: превышен лимит ({limit}/{seconds} сек), "
                    f"действие={settings.get('flood', {}).get('action', settings.get('action', 'mute'))}, ttl={ttl} сек"
                )
                await apply_antispam_action(user_id, chat_id, settings, message, bot, f"Флуд: превышен лимит ({limit}/{seconds} сек)", "flood")
                return True
        # Проверка повторяющихся сообщений
        if settings.get("repeated_messages", {}).get("enabled", True):
            async with redis_client() as redis:
                message_key = f"antispam:{chat_id}:{user_id}:messages"
                message_hash = await get_message_hash(text)
                await redis.lpush(message_key, message_hash)
                await redis.ltrim(message_key, 0, settings.get("repeated_messages", {}).get("limit", 5) - 1)
                recent_messages = await redis.lrange(message_key, 0, -1)
                await redis.expire(message_key, 3600)
                recent_messages = [msg.decode("utf-8") if isinstance(msg, bytes) else msg for msg in recent_messages]
                if len(recent_messages) >= settings.get("repeated_messages", {}).get("limit", 5):
                    if all(msg == message_hash for msg in recent_messages):
                        logger.info(
                            f"СПАМ/НАРУШЕНИЕ: user_id={user_id}, username=@{user.username or 'Unknown'}, "
                            f"chat_id={chat_id}, причина=Повторение сообщений: {text[:100]}, "
                            f"действие={settings.get('repeated_messages', {}).get('action', settings.get('action', 'warn'))}"
                        )
                        await apply_antispam_action(user_id, chat_id, settings, message, bot, f"Повторение сообщений: {text[:100]}", "repeated_messages")
                        await redis.delete(message_key)
                        return True
        # Проверка повторяющихся слов
        if settings.get("repeated_words", {}).get("enabled", True):
            words = [word for word in text.split() if word.lower() not in settings.get("ignored_words", [])]
            if len(words) >= settings.get("repeated_words", {}).get("limit", settings.get("repeated_words_limit", 5)):
                repeated_count = 1
                prev_word = None
                for word in words:
                    current_word = word.lower() if not settings.get("case_sensitive", False) else word
                    if prev_word and current_word == prev_word:
                        repeated_count += 1
                        if repeated_count >= settings.get("repeated_words", {}).get("limit", settings.get("repeated_words_limit", 5)):
                            logger.info(
                                f"СПАМ/НАРУШЕНИЕ: user_id={user_id}, username=@{user.username or 'Unknown'}, "
                                f"chat_id={chat_id}, причина=Повторение слов: {word}, "
                                f"действие={settings.get('repeated_words', {}).get('action', settings.get('action', 'warn'))}"
                            )
                            await apply_antispam_action(user_id, chat_id, settings, message, bot, f"Повторение слов: {word}", "repeated_words")
                            return True
                    else:
                        repeated_count = 1
                    prev_word = current_word
        # Проверка запрещенных слов
        if settings.get("spam_words", {}).get("enabled", True) and settings.get("spam_words", {}).get("words", []):
            pattern = "|".join([re.escape(word) for word in settings["spam_words"]["words"]])
            if re.search(pattern, text, re.IGNORECASE if not settings.get("case_sensitive", False) else 0):
                logger.info(
                    f"СПАМ/НАРУШЕНИЕ: user_id={user_id}, username=@{user.username or 'Unknown'}, "
                    f"chat_id={chat_id}, причина=Запрещенные слова: {text[:100]}, "
                    f"действие={settings.get('spam_words', {}).get('action', settings.get('action', 'ban'))}"
                )
                await apply_antispam_action(user_id, chat_id, settings, message, bot, f"Запрещенные слова: {text[:100]}", "spam_words")
                return True
        # Проверка внешних ссылок
        if settings.get("external_links", {}).get("enabled", False):
            url_pattern = r"https?://([A-Za-z0-9.-]+)"
            urls = re.findall(url_pattern, text, re.IGNORECASE)
            for domain in urls:
                if domain.lower() not in settings.get("exceptions", {}).get("domains", []):
                    if await check_dnsbl(domain):
                        logger.info(
                            f"СПАМ/НАРУШЕНИЕ: user_id={user_id}, username=@{user.username or 'Unknown'}, "
                            f"chat_id={chat_id}, причина=Спам-ссылка: {domain}, "
                            f"действие={settings.get('external_links', {}).get('action', settings.get('action', 'delete'))}"
                        )
                        await apply_antispam_action(user_id, chat_id, settings, message, bot, f"Спам-ссылка: {domain}", "external_links")
                        return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке спама для user_id={user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def apply_antispam_action(user_id: int, chat_id: int, settings: Dict, message: Optional[Message], bot: Bot, reason: str, filter_type: str) -> bool:
    """Применяет антиспам-действие и уведомляет администраторов."""
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        filter_settings = settings.get(filter_type, settings.get("telegram_links", {}))
        action = filter_settings.get("action", settings.get("action", "warn"))
        duration = filter_settings.get("duration", settings.get("mute_duration", 1800))  # 30 минут по умолчанию
        warnings = user.warnings.get(str(chat_id), [])
        warning_count = len(warnings)

        # Проверка исключений
        if user.get_role_for_chat(chat_id) in ["Владелец сервера", "Владелец бота"] or str(user_id) in settings.get("exceptions", {}).get("users", []):
            logger.info(f"Действие {action} пропущено: пользователь {user_id} является владельцем или в исключениях")
            return False

        # Формируем упоминание пользователя
        user_mention = f"@{user.username}" if user.username else user.display_name or f"User {user_id}"

        # Проверка прав бота
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if not bot_member.can_restrict_members:
            logger.error(f"Бот не имеет прав ограничивать пользователей в chat_id={chat_id}")
            await notify_admins(bot, settings, user_id, chat_id, f"Ошибка: бот не имеет прав для ограничения пользователей", "error", message.text or message.caption or "" if message else "Без текста")
            return False

        # Проверка текущего статуса пользователя в чате
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            is_muted = member.status == "restricted" and not member.can_send_messages
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса пользователя {user_id} в chat_id={chat_id}: {str(e)}")
            is_muted = False

        # Если пользователь уже в муте, пропускаем действие mute и уведомления
        if action == "mute" and is_muted:
            logger.info(f"Пользователь {user_id} уже в активном муте в chat_id={chat_id}, действие пропущено")
            return False

        # Флаг, указывающий, было ли сообщение уже удалено
        is_message_deleted = filter_type == "telegram_links" or (action == "delete" and filter_type != "telegram_links")

        if action == "delete":
            # Удаление сообщения, если оно не было удалено ранее и message не None
            if not is_message_deleted and message:
                try:
                    await retry_on_flood_control(message.delete)
                    logger.info(f"Удалено сообщение для user_id={user_id} в chat_id={chat_id}: {reason}")
                    is_message_deleted = True
                except Exception as e:
                    logger.warning(f"Не удалось удалить сообщение: {str(e)}")
            await log_moderation_action(user_id, chat_id, "delete", reason, bot.id)
            await notify_admins(bot, settings, user_id, chat_id, reason, "delete", message.text or message.caption or "" if message else "Без текста")
            return True

        if action == "warn":
            if warning_count < settings.get("warning_threshold", 3):
                success = await add_warning(user_id, chat_id, reason, bot.id)
                if success:
                    if message and not is_message_deleted:
                        try:
                            await retry_on_flood_control(
                                message.reply,
                                f"⚠️ Пользователь {user_mention} получил предупреждение: {reason}"
                            )
                        except TelegramBadRequest as e:
                            if "message to be replied to is not found" in str(e):
                                logger.warning(f"Сообщение для ответа не найдено для user_id={user_id} в chat_id={chat_id}, отправка через bot.send_message")
                                await retry_on_flood_control(
                                    bot.send_message,
                                    chat_id,
                                    f"⚠️ Пользователь {user_mention} получил предупреждение: {reason}"
                                )
                            else:
                                logger.error(f"Ошибка при отправке ответа для user_id={user_id} в chat_id={chat_id}: {str(e)}")
                                return False
                    elif not message:
                        logger.warning(f"Сообщение None, отправка предупреждения через bot.send_message для user_id={user_id} в chat_id={chat_id}")
                        await retry_on_flood_control(
                            bot.send_message,
                            chat_id,
                            f"⚠️ Пользователь {user_mention} получил предупреждение: {reason}"
                        )
                    await log_moderation_action(user_id, chat_id, "warn", reason, bot.id)
                    await notify_admins(bot, settings, user_id, chat_id, reason, "warn", message.text or message.caption or "" if message else "Без текста")
                    logger.info(f"Предупреждение выдано пользователю {user_id} в chat_id={chat_id}: {reason}")
                    return True
                return False
            action = "mute"  # Переход к муту, если превышен лимит предупреждений

        if action == "mute":
            # Применяем мут с длительностью по умолчанию или из настроек
            if user.get_role_for_chat(chat_id) not in ["Владелец сервера", "Владелец бота"]:
                duration = 1800  # Форсируем 30 минут для всех, кроме владельцев
            min_duration = 30  # Минимум 30 секунд
            duration = max(duration, min_duration)  # Убедимся, что длительность не меньше 30 секунд
            try:
                until_date = int(time.time()) + duration
                success = await mute_user(user_id, chat_id, duration, reason, bot.id)
                if success:
                    await retry_on_flood_control(
                        bot.restrict_chat_member,
                        chat_id,
                        user_id,
                        permissions={
                            "can_send_messages": False,
                            "can_send_media_messages": False,
                            "can_send_polls": False,
                            "can_send_other_messages": False
                        },
                        until_date=until_date
                    )
                    if message and not is_message_deleted:
                        try:
                            await retry_on_flood_control(
                                message.reply,
                                f"🔇 Пользователь {user_mention} замучен на {duration // 60} минут: {reason}"
                            )
                        except TelegramBadRequest as e:
                            if "message to be replied to is not found" in str(e):
                                logger.warning(f"Сообщение для ответа не найдено для user_id={user_id} в chat_id={chat_id}, отправка через bot.send_message")
                                await retry_on_flood_control(
                                    bot.send_message,
                                    chat_id,
                                    f"🔇 Пользователь {user_mention} замучен на {duration // 60} минут: {reason}"
                                )
                            else:
                                logger.error(f"Ошибка при отправке ответа для user_id={user_id} в chat_id={chat_id}: {str(e)}")
                                return False
                    elif not message:
                        logger.warning(f"Сообщение None, отправка мута через bot.send_message для user_id={user_id} в chat_id={chat_id}")
                        await retry_on_flood_control(
                            bot.send_message,
                            chat_id,
                            f"🔇 Пользователь {user_mention} замучен на {duration // 60} минут: {reason}"
                        )
                    await log_moderation_action(user_id, chat_id, "mute", reason, bot.id)
                    await notify_admins(bot, settings, user_id, chat_id, reason, "mute", message.text or message.caption or "" if message else "Без текста")
                    logger.info(f"Пользователь {user_id} замучен на {duration} секунд в chat_id={chat_id}: {reason}")
                    return True
                return False
            except Exception as e:
                logger.error(f"Ошибка при наложении мута для user_id={user_id} в chat_id={chat_id}: {str(e)}")
                await notify_admins(bot, settings, user_id, chat_id, f"Ошибка при наложении мута: {str(e)}", "error", message.text or message.caption or "" if message else "Без текста")
                return False

        if action == "ban":
            success = await ban_user(user_id, chat_id, reason, bot.id, duration)
            if success:
                if message and not is_message_deleted:
                    try:
                        await retry_on_flood_control(
                            message.reply,
                            f"🚫 Пользователь {user_mention} забанен на {duration // 3600} часов: {reason}"
                        )
                    except TelegramBadRequest as e:
                        if "message to be replied to is not found" in str(e):
                            logger.warning(f"Сообщение для ответа не найдено для user_id={user_id} в chat_id={chat_id}, отправка через bot.send_message")
                            await retry_on_flood_control(
                                bot.send_message,
                                chat_id,
                                f"🚫 Пользователь {user_mention} забанен на {duration // 3600} часов: {reason}"
                            )
                        else:
                            logger.error(f"Ошибка при отправке ответа для user_id={user_id} в chat_id={chat_id}: {str(e)}")
                            return False
                elif not message:
                    logger.warning(f"Сообщение None, отправка бана через bot.send_message для user_id={user_id} в chat_id={chat_id}")
                    await retry_on_flood_control(
                        bot.send_message,
                        chat_id,
                        f"🚫 Пользователь {user_mention} забанен на {duration // 3600} часов: {reason}"
                    )
                await log_moderation_action(user_id, chat_id, "ban", reason, bot.id)
                await notify_admins(bot, settings, user_id, chat_id, reason, "ban", message.text or message.caption or "" if message else "Без текста")
                logger.info(f"Пользователь {user_id} забанен в chat_id={chat_id}: {reason}")
                return True
            return False

        return False
    except Exception as e:
        logger.error(f"Ошибка при применении антиспам-действия для user_id={user_id} в chat_id={chat_id}: {str(e)}")
        return False

@router.message(Command("antispam_settings"))
async def cmd_antispam_settings(message: Message, bot: Bot, state: FSMContext):
    """Открывает главное меню настройки антиспама."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.get_role_for_chat(chat_id) not in ["Старший админ", "Заместитель", "Владелец сервера", "Владелец бота"]:
            await retry_on_flood_control(message.reply, "🚫 У вас нет прав для настройки антиспама.")
            logger.warning(f"Пользователь {user_id} без прав попытался выполнить /antispam_settings в chat_id={chat_id}")
            return
        settings = await get_settings("antispam", str(chat_id))
        if not settings:
            settings = await initialize_default_settings(str(chat_id))
        else:
            default_settings = await initialize_default_settings(str(chat_id))
            for key, value in default_settings.items():
                if key not in settings:
                    settings[key] = value
            await save_settings("antispam", str(chat_id), settings)
        await state.update_data(chat_id=str(chat_id), settings=settings)
        await retry_on_flood_control(
            message.reply,
            TEXTS["settings"].format(
                "Включен" if settings["enabled"] else "Выключен",
                f"{settings['repeated_words']['limit']} слов" if settings["repeated_words"]["enabled"] else "Выключен",
                settings["repeated_words"]["action"],
                f"{settings['repeated_messages']['limit']} сообщений" if settings["repeated_messages"]["enabled"] else "Выключен",
                settings["repeated_messages"]["action"],
                settings["flood"]["limit"],
                settings["flood"]["seconds"],
                settings["flood"]["action"],
                ", ".join(settings["spam_words"]["words"]) or "Отсутствуют",
                settings["spam_words"]["action"],
                "Включен" if settings["telegram_links"]["enabled"] else "Выключен",
                settings["telegram_links"]["action"],
                "Включен" if settings["external_links"]["enabled"] else "Выключен",
                settings["external_links"]["action"],
                "Включен" if settings["media_filter"]["enabled"] else "Выключен",
                settings["media_filter"]["action"],
                "Включен" if settings["auto_kick_inactive"] else "Выключен",
                ", ".join(settings["exceptions"]["users"]) or "Отсутствуют",
                ", ".join(settings["exceptions"]["domains"]) or "Отсутствуют",
                settings["admin_group"] or "Не задана",
                ", ".join(settings["ignored_words"]) or "Отсутствуют",
                settings["max_messages_per_minute"]
            ),
            reply_markup=get_main_menu(settings)
        )
        await state.set_state(AntispamStates.main_menu)
        logger.info(f"Открыто меню антиспама для user_id={user_id} в chat_id={chat_id}")
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при открытии меню антиспама для chat_id={chat_id}: {str(e)}")

@router.message(Command("set_admin_group"))
async def cmd_set_admin_group(message: Message, bot: Bot, state: FSMContext):
    """Устанавливает ID админ-группы для уведомлений."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.get_role_for_chat(chat_id) not in ["Старший админ", "Заместитель", "Владелец сервера", "Владелец бота"]:
            await retry_on_flood_control(message.reply, "🚫 У вас нет прав для настройки админ-группы.")
            logger.warning(f"Пользователь {user_id} без прав попытался выполнить /set_admin_group в chat_id={chat_id}")
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await retry_on_flood_control(message.reply, TEXTS["set_admin_group"])
            await state.set_state(AntispamStates.set_admin_group)
            return
        admin_group = args[1].strip()
        if not admin_group.startswith("-100") or not admin_group[1:].isdigit():
            await retry_on_flood_control(message.reply, "❌ Введите корректный ID группы (например, -1001234567890).")
            return
        settings = await get_settings("antispam", str(chat_id)) or await initialize_default_settings(str(chat_id))
        settings["admin_group"] = admin_group
        await save_settings("antispam", str(chat_id), settings)
        await retry_on_flood_control(message.reply, "✅ Админ-группа установлена.")
        logger.info(f"Админ-группа {admin_group} установлена для chat_id={chat_id}")
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке админ-группы для chat_id={chat_id}: {str(e)}")

@router.message(AntispamStates.set_admin_group)
async def set_admin_group(message: Message, state: FSMContext):
    """Устанавливает ID админ-группы через FSM."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.get_role_for_chat(chat_id) not in ["Старший админ", "Заместитель", "Владелец сервера", "Владелец бота"]:
            await retry_on_flood_control(message.reply, "🚫 У вас нет прав для настройки админ-группы.")
            return
        admin_group = message.text.strip()
        if not admin_group.startswith("-100") or not admin_group[1:].isdigit():
            await retry_on_flood_control(message.reply, "❌ Введите корректный ID группы (например, -1001234567890).")
            return
        settings = (await state.get_data()).get("settings", await initialize_default_settings(str(chat_id)))
        settings["admin_group"] = admin_group
        await save_settings("antispam", str(chat_id), settings)
        await state.update_data(settings=settings)
        await retry_on_flood_control(message.reply, "✅ Админ-группа установлена.")
        await retry_on_flood_control(
            message.reply,
            TEXTS["settings"].format(
                "Включен" if settings["enabled"] else "Выключен",
                f"{settings['repeated_words']['limit']} слов" if settings["repeated_words"]["enabled"] else "Выключен",
                settings["repeated_words"]["action"],
                f"{settings['repeated_messages']['limit']} сообщений" if settings["repeated_messages"]["enabled"] else "Выключен",
                settings["repeated_messages"]["action"],
                settings["flood"]["limit"],
                settings["flood"]["seconds"],
                settings["flood"]["action"],
                ", ".join(settings["spam_words"]["words"]) or "Отсутствуют",
                settings["spam_words"]["action"],
                "Включен" if settings["telegram_links"]["enabled"] else "Выключен",
                settings["telegram_links"]["action"],
                "Включен" if settings["external_links"]["enabled"] else "Выключен",
                settings["external_links"]["action"],
                "Включен" if settings["media_filter"]["enabled"] else "Выключен",
                settings["media_filter"]["action"],
                "Включен" if settings["auto_kick_inactive"] else "Выключен",
                ", ".join(settings["exceptions"]["users"]) or "Отсутствуют",
                ", ".join(settings["exceptions"]["domains"]) or "Отсутствуют",
                settings["admin_group"] or "Не задана",
                ", ".join(settings["ignored_words"]) or "Отсутствуют",
                settings["max_messages_per_minute"]
            ),
            reply_markup=get_main_menu(settings)
        )
        await state.set_state(AntispamStates.main_menu)
        logger.info(f"Админ-группа {admin_group} установлена через FSM для chat_id={chat_id}")
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке админ-группы через FSM: {str(e)}")

@router.callback_query(AntispamStates.main_menu)
async def process_main_menu(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор в главном меню."""
    chat_id = int((await state.get_data()).get("chat_id"))
    settings = (await state.get_data()).get("settings", {})
    try:
        if callback.data == "antispam_toggle":
            settings["enabled"] = not settings.get("enabled", False)
            await save_settings("antispam", str(chat_id), settings)
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["settings"].format(
                    "Включен" if settings["enabled"] else "Выключен",
                    f"{settings['repeated_words']['limit']} слов" if settings["repeated_words"]["enabled"] else "Выключен",
                    settings["repeated_words"]["action"],
                    f"{settings['repeated_messages']['limit']} сообщений" if settings["repeated_messages"]["enabled"] else "Выключен",
                    settings["repeated_messages"]["action"],
                    settings["flood"]["limit"],
                    settings["flood"]["seconds"],
                    settings["flood"]["action"],
                    ", ".join(settings["spam_words"]["words"]) or "Отсутствуют",
                    settings["spam_words"]["action"],
                    "Включен" if settings["telegram_links"]["enabled"] else "Выключен",
                    settings["telegram_links"]["action"],
                    "Включен" if settings["external_links"]["enabled"] else "Выключен",
                    settings["external_links"]["action"],
                    "Включен" if settings["media_filter"]["enabled"] else "Выключен",
                    settings["media_filter"]["action"],
                    "Включен" if settings["auto_kick_inactive"] else "Выключен",
                    ", ".join(settings["exceptions"]["users"]) or "Отсутствуют",
                    ", ".join(settings["exceptions"]["domains"]) or "Отсутствуют",
                    settings["admin_group"] or "Не задана",
                    ", ".join(settings["ignored_words"]) or "Отсутствуют",
                    settings["max_messages_per_minute"]
                ),
                reply_markup=get_main_menu(settings)
            )
            logger.info(f"Антиспам {'включен' if settings['enabled'] else 'выключен'} для chat_id={chat_id}")
        elif callback.data == "select_filter":
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["filter_menu"],
                reply_markup=get_filter_menu()
            )
            await state.set_state(AntispamStates.select_filter)
        elif callback.data == "set_exceptions_users":
            await retry_on_flood_control(callback.message.edit_text, TEXTS["set_exceptions_users"])
            await state.set_state(AntispamStates.set_exceptions_users)
        elif callback.data == "set_exceptions_domains":
            await retry_on_flood_control(callback.message.edit_text, TEXTS["set_exceptions_domains"])
            await state.set_state(AntispamStates.set_exceptions_domains)
        elif callback.data == "set_media_filter":
            await retry_on_flood_control(callback.message.edit_text, TEXTS["set_media_filter"])
            await state.set_state(AntispamStates.set_media_filter)
        elif callback.data == "toggle_auto_kick":
            if not await is_chat_owner(callback.message.bot, callback.from_user.id, chat_id):
                await retry_on_flood_control(callback.message.reply, "🚫 Только владелец чата может управлять автокиком.")
                return
            settings["auto_kick_inactive"] = not settings.get("auto_kick_inactive", False)
            if settings["auto_kick_inactive"]:
                await set_server_owner(callback.from_user.id, chat_id)
            await save_settings("antispam", str(chat_id), settings)
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["settings"].format(
                    "Включен" if settings["enabled"] else "Выключен",
                    f"{settings['repeated_words']['limit']} слов" if settings["repeated_words"]["enabled"] else "Выключен",
                    settings["repeated_words"]["action"],
                    f"{settings['repeated_messages']['limit']} сообщений" if settings["repeated_messages"]["enabled"] else "Выключен",
                    settings["repeated_messages"]["action"],
                    settings["flood"]["limit"],
                    settings["flood"]["seconds"],
                    settings["flood"]["action"],
                    ", ".join(settings["spam_words"]["words"]) or "Отсутствуют",
                    settings["spam_words"]["action"],
                    "Включен" if settings["telegram_links"]["enabled"] else "Выключен",
                    settings["telegram_links"]["action"],
                    "Включен" if settings["external_links"]["enabled"] else "Выключен",
                    settings["external_links"]["action"],
                    "Включен" if settings["media_filter"]["enabled"] else "Выключен",
                    settings["media_filter"]["action"],
                    "Включен" if settings["auto_kick_inactive"] else "Выключен",
                    ", ".join(settings["exceptions"]["users"]) or "Отсутствуют",
                    ", ".join(settings["exceptions"]["domains"]) or "Отсутствуют",
                    settings["admin_group"] or "Не задана",
                    ", ".join(settings["ignored_words"]) or "Отсутствуют",
                    settings["max_messages_per_minute"]
                ),
                reply_markup=get_main_menu(settings)
            )
            logger.info(f"Автокик неактивных {'включен' if settings['auto_kick_inactive'] else 'выключен'} для chat_id={chat_id}")
        await callback.answer()
    except Exception as e:
        await retry_on_flood_control(callback.message.reply, TEXTS["error"])
        logger.error(f"Ошибка в главном меню для chat_id={chat_id}: {str(e)}")

@router.callback_query(AntispamStates.select_filter)
async def process_filter_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор фильтра."""
    filter_map = {
        "filter_repeated_words": "repeated_words",
        "filter_repeated_messages": "repeated_messages",
        "filter_flood": "flood",
        "filter_spam_words": "spam_words",
        "filter_telegram_links": "telegram_links",
        "filter_external_links": "external_links"
    }
    try:
        if callback.data == "back_to_main":
            settings = (await state.get_data()).get("settings", {})
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["settings"].format(
                    "Включен" if settings["enabled"] else "Выключен",
                    f"{settings['repeated_words']['limit']} слов" if settings["repeated_words"]["enabled"] else "Выключен",
                    settings["repeated_words"]["action"],
                    f"{settings['repeated_messages']['limit']} сообщений" if settings["repeated_messages"]["enabled"] else "Выключен",
                    settings["repeated_messages"]["action"],
                    settings["flood"]["limit"],
                    settings["flood"]["seconds"],
                    settings["flood"]["action"],
                    ", ".join(settings["spam_words"]["words"]) or "Отсутствуют",
                    settings["spam_words"]["action"],
                    "Включен" if settings["telegram_links"]["enabled"] else "Выключен",
                    settings["telegram_links"]["action"],
                    "Включен" if settings["external_links"]["enabled"] else "Выключен",
                    settings["external_links"]["action"],
                    "Включен" if settings["media_filter"]["enabled"] else "Выключен",
                    settings["media_filter"]["action"],
                    "Включен" if settings["auto_kick_inactive"] else "Выключен",
                    ", ".join(settings["exceptions"]["users"]) or "Отсутствуют",
                    ", ".join(settings["exceptions"]["domains"]) or "Отсутствуют",
                    settings["admin_group"] or "Не задана",
                    ", ".join(settings["ignored_words"]) or "Отсутствуют",
                    settings["max_messages_per_minute"]
                ),
                reply_markup=get_main_menu(settings)
            )
            await state.set_state(AntispamStates.main_menu)
        elif callback.data in filter_map:
            filter_name = filter_map[callback.data]
            await state.update_data(current_filter=filter_name)
            settings = (await state.get_data()).get("settings", {})
            filter_settings = settings.get(filter_name, {"limit": 5, "action": "warn", "duration": 1800, "seconds": 10})
            duration = filter_settings.get("duration", 1800) // 60
            seconds = filter_settings.get("seconds", 10) if filter_name == "flood" else "N/A"
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["filter_settings"].format(
                    filter_name,
                    filter_settings.get("limit", 5),
                    filter_settings.get("action", "warn"),
                    f"{duration} минут" if duration else "Не указано",
                    seconds
                ),
                reply_markup=get_filter_settings_menu(filter_name)
            )
            await state.set_state(AntispamStates.set_limit)
        await callback.answer()
    except Exception as e:
        await retry_on_flood_control(callback.message.reply, TEXTS["error"])
        logger.error(f"Ошибка при выборе фильтра для chat_id={callback.message.chat.id}: {str(e)}")

@router.callback_query(AntispamStates.set_limit)
async def process_filter_settings(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает настройку параметров фильтра."""
    data = await state.get_data()
    filter_name = data.get("current_filter")
    settings = data.get("settings", {})
    try:
        if callback.data == "select_filter":
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["filter_menu"],
                reply_markup=get_filter_menu()
            )
            await state.set_state(AntispamStates.select_filter)
        elif callback.data.startswith("set_limit_"):
            await retry_on_flood_control(callback.message.edit_text, TEXTS["set_limit"])
            await state.set_state(AntispamStates.set_limit)
        elif callback.data.startswith("set_action_"):
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["set_action"],
                reply_markup=get_action_menu(filter_name)
            )
            await state.set_state(AntispamStates.set_action)
        elif callback.data.startswith("set_duration_"):
            await retry_on_flood_control(callback.message.edit_text, TEXTS["set_duration"])
            await state.set_state(AntispamStates.set_duration)
        elif callback.data.startswith("set_flood_seconds_"):
            await retry_on_flood_control(callback.message.edit_text, TEXTS["set_flood_seconds"])
            await state.set_state(AntispamStates.set_flood_seconds)
        await callback.answer()
    except Exception as e:
        await retry_on_flood_control(callback.message.reply, TEXTS["error"])
        logger.error(f"Ошибка при настройке фильтра {filter_name} для chat_id={callback.message.chat.id}: {str(e)}")

@router.callback_query(AntispamStates.set_action)
async def process_action_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор действия для фильтра."""
    data = await state.get_data()
    filter_name = data.get("current_filter")
    settings = data.get("settings", {})
    chat_id = int(data.get("chat_id"))
    try:
        if callback.data.startswith("action_"):
            action = callback.data.split("_")[-1]
            settings[filter_name]["action"] = action
            settings[filter_name]["enabled"] = True
            await save_settings("antispam", str(chat_id), settings)
            await state.update_data(settings=settings)
            filter_settings = settings.get(filter_name, {"limit": 5, "action": "warn", "duration": 1800, "seconds": 10})
            duration = filter_settings.get("duration", 1800) // 60
            seconds = filter_settings.get("seconds", 10) if filter_name == "flood" else "N/A"
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["filter_settings"].format(
                    filter_name,
                    filter_settings.get("limit", 5),
                    filter_settings.get("action", "warn"),
                    f"{duration} минут" if duration else "Не указано",
                    seconds
                ),
                reply_markup=get_filter_settings_menu(filter_name)
            )
            await state.set_state(AntispamStates.set_limit)
        elif callback.data == f"set_filter_{filter_name}":
            filter_settings = settings.get(filter_name, {"limit": 5, "action": "warn", "duration": 1800, "seconds": 10})
            duration = filter_settings.get("duration", 1800) // 60
            seconds = filter_settings.get("seconds", 10) if filter_name == "flood" else "N/A"
            await retry_on_flood_control(
                callback.message.edit_text,
                TEXTS["filter_settings"].format(
                    filter_name,
                    filter_settings.get("limit", 5),
                    filter_settings.get("action", "warn"),
                    f"{duration} минут" if duration else "Не указано",
                    seconds
                ),
                reply_markup=get_filter_settings_menu(filter_name)
            )
            await state.set_state(AntispamStates.set_limit)
        await callback.answer()
    except Exception as e:
        await retry_on_flood_control(callback.message.reply, TEXTS["error"])
        logger.error(f"Ошибка при выборе действия для фильтра {filter_name}: {str(e)}")

@router.message(AntispamStates.set_limit)
async def set_filter_limit(message: Message, state: FSMContext):
    """Устанавливает лимит для фильтра."""
    data = await state.get_data()
    filter_name = data.get("current_filter")
    settings = data.get("settings", {})
    chat_id = int(data.get("chat_id"))
    try:
        limit = int(message.text)
        if limit < 1:
            await retry_on_flood_control(message.reply, "❌ Лимит должен быть больше 0.")
            return
        settings[filter_name]["limit"] = limit
        settings[filter_name]["enabled"] = True
        await save_settings("antispam", str(chat_id), settings)
        await state.update_data(settings=settings)
        filter_settings = settings.get(filter_name, {"limit": 5, "action": "warn", "duration": 1800, "seconds": 10})
        duration = filter_settings.get("duration", 1800) // 60
        seconds = filter_settings.get("seconds", 10) if filter_name == "flood" else "N/A"
        await retry_on_flood_control(
            message.reply,
            TEXTS["filter_settings"].format(
                filter_name,
                filter_settings.get("limit", 5),
                filter_settings.get("action", "warn"),
                f"{duration} минут",
                seconds
            ),
            reply_markup=get_filter_settings_menu(filter_name)
        )
        await state.set_state(AntispamStates.set_limit)
    except ValueError:
        await retry_on_flood_control(message.reply, "❌ Введите числовое значение для лимита.")
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке лимита для фильтра {filter_name}: {str(e)}")

@router.message(AntispamStates.set_duration)
async def set_filter_duration(message: Message, state: FSMContext):
    """Устанавливает длительность наказания для фильтра."""
    data = await state.get_data()
    filter_name = data.get("current_filter")
    settings = data.get("settings", {})
    chat_id = int(data.get("chat_id"))
    try:
        user = await get_user(message.from_user.id, create_if_not_exists=True, chat_id=chat_id)
        if user.get_role_for_chat(chat_id) not in ["Владелец сервера", "Владелец бота"]:
            await retry_on_flood_control(
                message.reply,
                "🚫 Только владелец сервера или бота может изменять длительность наказания."
            )
            return
        duration = await parse_duration(message.text)
        if duration is None:
            await retry_on_flood_control(message.reply, "❌ Неверный формат длительности. Пример: 3d, 2h, 15m, 30s")
            return
        min_duration = 30  # 30 секунд минимум для владельцев
        if duration < min_duration:
            await retry_on_flood_control(
                message.reply,
                f"❌ Длительность мута не может быть меньше {min_duration} секунд."
            )
            return
        if duration > 365 * 86400:  # Ограничение в 1 год
            await retry_on_flood_control(
                message.reply,
                "❌ Длительность мута не может превышать 1 год."
            )
            return
        settings[filter_name]["duration"] = duration
        settings[filter_name]["enabled"] = True
        await save_settings("antispam", str(chat_id), settings)
        await state.update_data(settings=settings)
        filter_settings = settings.get(filter_name, {"limit": 5, "action": "warn", "duration": 1800, "seconds": 10})
        duration = filter_settings.get("duration", 1800) // 60
        seconds = filter_settings.get("seconds", 10) if filter_name == "flood" else "N/A"
        await retry_on_flood_control(
            message.reply,
            TEXTS["filter_settings"].format(
                filter_name,
                filter_settings.get("limit", 5),
                filter_settings.get("action", "warn"),
                f"{duration} минут",
                seconds
            ),
            reply_markup=get_filter_settings_menu(filter_name)
        )
        await state.set_state(AntispamStates.set_limit)
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке длительности для фильтра {filter_name}: {str(e)}")

@router.message(AntispamStates.set_flood_seconds)
async def set_flood_seconds(message: Message, state: FSMContext):
    """Устанавливает период проверки флуда в секундах."""
    data = await state.get_data()
    filter_name = data.get("current_filter")
    settings = data.get("settings", {})
    chat_id = int(data.get("chat_id"))
    try:
        seconds = int(message.text)
        if seconds < 5 or seconds > 60:
            await retry_on_flood_control(message.reply, "❌ Период должен быть от 5 до 60 секунд.")
            return
        settings[filter_name]["seconds"] = seconds
        settings[filter_name]["enabled"] = True
        await save_settings("antispam", str(chat_id), settings)
        await state.update_data(settings=settings)
        filter_settings = settings.get(filter_name, {"limit": 5, "action": "warn", "duration": 1800, "seconds": 10})
        duration = filter_settings.get("duration", 1800) // 60
        seconds = filter_settings.get("seconds", 10)
        await retry_on_flood_control(
            message.reply,
            TEXTS["filter_settings"].format(
                filter_name,
                filter_settings.get("limit", 5),
                filter_settings.get("action", "warn"),
                f"{duration} минут",
                seconds
            ),
            reply_markup=get_filter_settings_menu(filter_name)
        )
        await state.set_state(AntispamStates.set_limit)
    except ValueError:
        await retry_on_flood_control(message.reply, "❌ Введите числовое значение для периода.")
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке периода флуда: {str(e)}")

@router.message(AntispamStates.set_spam_words)
async def set_spam_words(message: Message, state: FSMContext):
    """Устанавливает запрещенные слова."""
    data = await state.get_data()
    settings = data.get("settings", {})
    chat_id = int(data.get("chat_id"))
    try:
        words = [word.strip() for word in message.text.split(",") if word.strip()]
        settings["spam_words"]["words"] = words
        settings["spam_words"]["enabled"] = True
        await save_settings("antispam", str(chat_id), settings)
        await state.update_data(settings=settings)
        await retry_on_flood_control(message.reply, TEXTS["success"])
        await retry_on_flood_control(
            message.reply,
            TEXTS["filter_settings"].format(
                "spam_words",
                len(words),
                settings["spam_words"].get("action", "ban"),
                f"{settings['spam_words'].get('duration', 1800) // 60} минут",
                "N/A"
            ),
            reply_markup=get_filter_settings_menu("spam_words")
        )
        await state.set_state(AntispamStates.set_limit)
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке запрещенных слов: {str(e)}")

@router.message(AntispamStates.set_exceptions_users)
async def set_exceptions_users(message: Message, state: FSMContext):
    """Устанавливает исключения для пользователей."""
    data = await state.get_data()
    settings = data.get("settings", {})
    chat_id = int(data.get("chat_id"))
    try:
        users = [user.strip() for user in message.text.split(",") if user.strip().isdigit()]
        settings["exceptions"]["users"] = users
        await save_settings("antispam", str(chat_id), settings)
        await state.update_data(settings=settings)
        await retry_on_flood_control(message.reply, TEXTS["success"])
        await retry_on_flood_control(
            message.reply,
            TEXTS["settings"].format(
                "Включен" if settings["enabled"] else "Выключен",
                f"{settings['repeated_words']['limit']} слов" if settings["repeated_words"]["enabled"] else "Выключен",
                settings["repeated_words"]["action"],
                f"{settings['repeated_messages']['limit']} сообщений" if settings["repeated_messages"]["enabled"] else "Выключен",
                settings["repeated_messages"]["action"],
                settings["flood"]["limit"],
                settings["flood"]["seconds"],
                settings["flood"]["action"],
                ", ".join(settings["spam_words"]["words"]) or "Отсутствуют",
                settings["spam_words"]["action"],
                "Включен" if settings["telegram_links"]["enabled"] else "Выключен",
                settings["telegram_links"]["action"],
                "Включен" if settings["external_links"]["enabled"] else "Выключен",
                settings["external_links"]["action"],
                "Включен" if settings["media_filter"]["enabled"] else "Выключен",
                settings["media_filter"]["action"],
                "Включен" if settings["auto_kick_inactive"] else "Выключен",
                ", ".join(settings["exceptions"]["users"]) or "Отсутствуют",
                ", ".join(settings["exceptions"]["domains"]) or "Отсутствуют",
                settings["admin_group"] or "Не задана",
                ", ".join(settings["ignored_words"]) or "Отсутствуют",
                settings["max_messages_per_minute"]
            ),
            reply_markup=get_main_menu(settings)
        )
        await state.set_state(AntispamStates.main_menu)
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке исключений пользователей: {str(e)}")

@router.message(AntispamStates.set_exceptions_domains)
async def set_exceptions_domains(message: Message, state: FSMContext):
    """Устанавливает исключения для доменов."""
    data = await state.get_data()
    settings = data.get("settings", {})
    chat_id = int(data.get("chat_id"))
    try:
        domains = [domain.strip().lower() for domain in message.text.split(",") if domain.strip()]
        settings["exceptions"]["domains"] = domains
        await save_settings("antispam", str(chat_id), settings)
        await state.update_data(settings=settings)
        await retry_on_flood_control(message.reply, TEXTS["success"])
        await retry_on_flood_control(
            message.reply,
            TEXTS["settings"].format(
                "Включен" if settings["enabled"] else "Выключен",
                f"{settings['repeated_words']['limit']} слов" if settings["repeated_words"]["enabled"] else "Выключен",
                settings["repeated_words"]["action"],
                f"{settings['repeated_messages']['limit']} сообщений" if settings["repeated_messages"]["enabled"] else "Выключен",
                settings["repeated_messages"]["action"],
                settings["flood"]["limit"],
                settings["flood"]["seconds"],
                settings["flood"]["action"],
                ", ".join(settings["spam_words"]["words"]) or "Отсутствуют",
                settings["spam_words"]["action"],
                "Включен" if settings["telegram_links"]["enabled"] else "Выключен",
                settings["telegram_links"]["action"],
                "Включен" if settings["external_links"]["enabled"] else "Выключен",
                settings["external_links"]["action"],
                "Включен" if settings["media_filter"]["enabled"] else "Выключен",
                settings["media_filter"]["action"],
                "Включен" if settings["auto_kick_inactive"] else "Выключен",
                ", ".join(settings["exceptions"]["users"]) or "Отсутствуют",
                ", ".join(settings["exceptions"]["domains"]) or "Отсутствуют",
                settings["admin_group"] or "Не задана",
                ", ".join(settings["ignored_words"]) or "Отсутствуют",
                settings["max_messages_per_minute"]
            ),
            reply_markup=get_main_menu(settings)
        )
        await state.set_state(AntispamStates.main_menu)
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке исключений доменов: {str(e)}")

@router.message(AntispamStates.set_media_filter)
async def set_media_filter(message: Message, state: FSMContext):
    """Устанавливает фильтр медиа."""
    data = await state.get_data()
    settings = data.get("settings", {})
    chat_id = int(data.get("chat_id"))
    try:
        response = message.text.lower().strip()
        if response not in ["да", "нет"]:
            await retry_on_flood_control(message.reply, "❌ Введите 'да' или 'нет'.")
            return
        settings["media_filter"]["enabled"] = response == "да"
        await save_settings("antispam", str(chat_id), settings)
        await state.update_data(settings=settings)
        await retry_on_flood_control(message.reply, TEXTS["success"])
        await retry_on_flood_control(
            message.reply,
            TEXTS["settings"].format(
                "Включен" if settings["enabled"] else "Выключен",
                f"{settings['repeated_words']['limit']} слов" if settings["repeated_words"]["enabled"] else "Выключен",
                settings["repeated_words"]["action"],
                f"{settings['repeated_messages']['limit']} сообщений" if settings["repeated_messages"]["enabled"] else "Выключен",
                settings["repeated_messages"]["action"],
                settings["flood"]["limit"],
                settings["flood"]["seconds"],
                settings["flood"]["action"],
                ", ".join(settings["spam_words"]["words"]) or "Отсутствуют",
                settings["spam_words"]["action"],
                "Включен" if settings["telegram_links"]["enabled"] else "Выключен",
                settings["telegram_links"]["action"],
                "Включен" if settings["external_links"]["enabled"] else "Выключен",
                settings["external_links"]["action"],
                "Включен" if settings["media_filter"]["enabled"] else "Выключен",
                settings["media_filter"]["action"],
                "Включен" if settings["auto_kick_inactive"] else "Выключен",
                ", ".join(settings["exceptions"]["users"]) or "Отсутствуют",
                ", ".join(settings["exceptions"]["domains"]) or "Отсутствуют",
                settings["admin_group"] or "Не задана",
                ", ".join(settings["ignored_words"]) or "Отсутствуют",
                settings["max_messages_per_minute"]
            ),
            reply_markup=get_main_menu(settings)
        )
        await state.set_state(AntispamStates.main_menu)
        logger.info(f"Фильтр медиа {'включен' if settings['media_filter']['enabled'] else 'выключен'} для chat_id={chat_id}")
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при установке фильтра медиа: {str(e)}")

@router.message(Command("kick_inactive"))
async def cmd_kick_inactive(message: Message, bot: Bot):
    """Обработчик команды /kick_inactive для исключения неактивных пользователей."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        if not await is_chat_owner(bot, user_id, chat_id):
            await retry_on_flood_control(message.reply, "🚫 Только владелец чата может выполнить эту команду.")
            return
        settings = await get_settings("antispam", str(chat_id)) or await initialize_default_settings(str(chat_id))
        if not settings.get("auto_kick_inactive", False):
            await retry_on_flood_control(message.reply, "🚫 Автокик неактивных пользователей отключен.")
            return
        args = message.text.split()[1:]
        inactivity_days = 30
        for arg in args:
            if arg.startswith("days=") and arg[len("days="):].isdigit():
                inactivity_days = int(arg[len("days="):])
        kicked_count = await kick_inactive_users(chat_id, bot, inactivity_days)
        await retry_on_flood_control(message.reply, f"✅ Исключено {kicked_count} неактивных пользователей.")
        logger.info(f"Исключено {kicked_count} пользователей в chat_id={chat_id}")
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при выполнении /kick_inactive для chat_id={chat_id}: {str(e)}")

@router.message(Command("reset_spam"))
async def cmd_reset_spam(message: Message, bot: Bot):
    """Сбрасывает состояние спама для пользователя."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if user.get_role_for_chat(chat_id) not in ["Старший админ", "Заместитель", "Владелец сервера", "Владелец бота"]:
            await retry_on_flood_control(message.reply, "🚫 У вас нет прав для сброса состояния спама.")
            logger.warning(f"Пользователь {user_id} без прав попытался выполнить /reset_spam в chat_id={chat_id}")
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await retry_on_flood_control(message.reply, "❌ Укажите пользователя: ID, @username или username (например, /reset_spam @Okumi_di).")
            return
        target = args[1].strip()
        target_user_id = None
        target_username = None

        # Проверка формата аргумента
        if target.isdigit():
            target_user_id = int(target)
            logger.debug(f"Обработка /reset_spam: указан ID {target_user_id}")
        elif target.startswith("@"):
            target_username = target[1:]
            logger.debug(f"Обработка /reset_spam: указано упоминание @{target_username}")
        else:
            target_username = target
            logger.debug(f"Обработка /reset_spam: указан username {target_username}")

        # Поиск пользователя
        if target_user_id:
            target_user = await get_user(target_user_id)
            if not target_user:
                await retry_on_flood_control(message.reply, TEXTS["invalid_user"])
                logger.warning(f"Пользователь с ID {target_user_id} не найден")
                return
        else:
            # Поиск по username в MongoDB
            target_user = None
            async for user_doc in get_user(username=target_username):
                target_user = user_doc
                break
            if not target_user:
                await retry_on_flood_control(message.reply, TEXTS["invalid_user"])
                logger.warning(f"Пользователь с username {target_username} не найден")
                return
            target_user_id = target_user.id

        await reset_spam_state(chat_id, target_user_id)
        await retry_on_flood_control(message.reply, TEXTS["reset_spam"].format(f"@{target_user.username or 'Unknown'} ({target_user_id})", chat_id))
        logger.info(f"Состояние спама сброшено для user_id={target_user_id} в chat_id={chat_id} пользователем {user_id}")
    except Exception as e:
        await retry_on_flood_control(message.reply, TEXTS["error"])
        logger.error(f"Ошибка при /reset_spam для user_id={user_id} в chat_id={chat_id}: {str(e)}")

@router.message(F.text)
async def check_spam_message(message: Message, bot: Bot):
    """Обработчик всех текстовых сообщений для проверки спама."""
    await check_spam(message, bot)

@router.message(F.content_type.in_({'photo', 'video', 'audio', 'document', 'sticker', 'animation'}))
async def check_spam_media(message: Message, bot: Bot):
    """Обработчик медиа-сообщений для проверки спама."""
    await check_spam(message, bot)

@router.callback_query(F.data.startswith("spam_confirm_") | F.data.startswith("spam_cancel_"))
async def handle_spam_action(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает подтверждение или отмену антиспам-действия."""
    try:
        parts = callback.data.split("_")
        action_type = parts[1]  # confirm или cancel
        user_id = int(parts[2])
        chat_id = int(parts[3])
        spam_action = parts[4]
        user = await get_user(user_id)
        user_mention = f"@{user.username}" if user.username else user.display_name or f"User {user_id}"
        if action_type == "confirm":
            await retry_on_flood_control(
                callback.message.edit_text,
                f"✅ Действие {spam_action} для пользователя {user_mention} подтверждено."
            )
            logger.info(f"Подтверждено действие {spam_action} для user_id={user_id} в chat_id={chat_id}")
        else:
            if spam_action == "warn":
                warnings = user.warnings.get(str(chat_id), [])
                if warnings:
                    warnings.pop()
                    await update_user(user_id, {f"warnings.{chat_id}": warnings})
            elif spam_action == "mute":
                await unmute_user(user_id, chat_id, callback.from_user.id)
                await retry_on_flood_control(
                    callback.message.bot.restrict_chat_member,
                    chat_id,
                    user_id,
                    permissions={"can_send_messages": True, "can_send_media_messages": True, "can_send_polls": True, "can_send_other_messages": True}
                )
            elif spam_action == "ban":
                await unban_user(user_id, chat_id, callback.from_user.id)
                await retry_on_flood_control(
                    callback.message.bot.unban_chat_member,
                    chat_id,
                    user_id,
                    only_if_banned=True
                )
            await retry_on_flood_control(
                callback.message.edit_text,
                f"❌ Действие {spam_action} для пользователя {user_mention} отменено."
            )
            logger.info(f"Отменено действие {spam_action} для user_id={user_id} в chat_id={chat_id}")
        await callback.answer()
    except Exception as e:
        await retry_on_flood_control(callback.message.reply, TEXTS["error"])
        logger.error(f"Ошибка при обработке spam_action для user_id={user_id} в chat_id={chat_id}: {str(e)}")