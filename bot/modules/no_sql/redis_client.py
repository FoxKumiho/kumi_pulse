# Путь файла: bot/modules/no_sql/redis_client.py

import hashlib
import os
import asyncio
import time
from redis.asyncio import ConnectionPool, Redis
from contextlib import asynccontextmanager
from loguru import logger
import json
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from aiocache import cached, Cache
from aiocache.serializers import PickleSerializer
from ..no_sql.user_db import get_known_chats, get_user, register_chat_member, add_warning, mute_user, ban_user, \
    kick_user
from ..no_sql.mongo_client import get_database
import aiogram
from aiogram.types import Message, ChatMemberOwner

# Проверка версии aiogram
assert aiogram.__version__ == "3.20.0.post0", f"Expected aiogram version 3.20.0.post0, but found {aiogram.__version__}"

# Пул соединений Redis
redis_pool = ConnectionPool.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True
)

# Локальный кэш для настроек
settings_cache = Cache(Cache.MEMORY, serializer=PickleSerializer(), ttl=3600)  # Кэш на 1 час

# Кэш для уведомлений для предотвращения спама
notification_cache = Cache(Cache.MEMORY, serializer=PickleSerializer(), ttl=60)  # Кэш уведомлений на 1 минуту

async def init_redis() -> Redis:
    """
    Инициализирует и возвращает асинхронный Redis-клиент с использованием пула соединений.

    Возвращает:
        Redis: Асинхронный клиент Redis.

    Raises:
        ConnectionError: Если не удалось установить соединение после 3 попыток.
    """
    redis = Redis(connection_pool=redis_pool)
    for attempt in range(3):
        try:
            if await redis.ping():
                logger.debug("Подключение к Redis успешно установлено")
                return redis
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1} подключения к Redis не удалась: {str(e)}")
            if attempt == 2:
                raise ConnectionError(f"Не удалось подключиться к Redis после 3 попыток: {str(e)}")
            await asyncio.sleep(1)
    return redis

@asynccontextmanager
async def redis_client():
    """
    Контекстный менеджер для подключения к Redis с использованием пула соединений.

    Yields:
        Redis: Асинхронный клиент Redis.

    Raises:
        ConnectionError: Если не удалось установить соединение.
    """
    redis = await init_redis()
    try:
        yield redis
    except Exception as e:
        logger.error(f"Ошибка при работе с Redis: {str(e)}")
        raise
    finally:
        await redis.aclose()
        logger.debug("Соединение с Redis закрыто")

async def ensure_user_exists(user_id: int, chat_id: int, username: Optional[str] = None,
                             display_name: Optional[str] = None, is_bot: bool = False) -> bool:
    """
    Проверяет наличие пользователя в MongoDB и регистрирует его, если он отсутствует.

    Args:
        user_id: ID пользователя.
        chat_id: ID чата.
        username: Имя пользователя Telegram (опционально).
        display_name: Отображаемое имя пользователя (опционально).
        is_bot: Флаг, указывающий, является ли пользователь ботом.

    Возвращает:
        bool: True, если пользователь существует или успешно зарегистрирован, иначе False.
    """
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        if not user:
            await register_chat_member(user_id, username, display_name, chat_id, is_bot)
            logger.info(f"Зарегистрирован новый пользователь {user_id} в chat_id={chat_id}")
        else:
            if chat_id not in user.group_ids:
                await register_chat_member(user_id, username, display_name, chat_id, is_bot)
                logger.info(f"Пользователь {user_id} добавлен в chat_id={chat_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при проверке/регистрации пользователя {user_id} для chat_id={chat_id}: {str(e)}")
        return False

async def validate_settings(setting_type: str, settings: Dict) -> bool:
    """
    Валидирует настройки перед сохранением.

    Args:
        setting_type: Тип настроек (например, 'antispam').
        settings: Словарь настроек.

    Возвращает:
        bool: True, если настройки валидны, иначе False.
    """
    try:
        if setting_type == "antispam":
            required_keys = {
                "enabled", "repeated_words_limit", "case_sensitive", "action",
                "mute_duration", "ban_duration", "warning_threshold",
                "max_messages_per_minute", "ignored_words", "auto_kick_inactive"
            }
            optional_keys = {
                "telegram_links", "repeated_words", "repeated_messages",
                "flood", "external_links", "media_filter"
            }
            missing_keys = required_keys - settings.keys()
            if missing_keys:
                logger.error(f"Недостаточно ключей в настройках антиспама: {missing_keys}")
                return False

            if not isinstance(settings["repeated_words_limit"], int) or settings["repeated_words_limit"] < 2:
                logger.error(f"Недопустимое значение repeated_words_limit: {settings['repeated_words_limit']}")
                return False
            if settings["action"] not in ["warn", "mute", "ban"]:
                logger.error(f"Недопустимое действие: {settings['action']}")
                return False
            if not isinstance(settings["mute_duration"], int) or settings["mute_duration"] <= 0:
                logger.error(f"Недопустимое значение mute_duration: {settings['mute_duration']}")
                return False
            if not isinstance(settings["ban_duration"], int) or settings["ban_duration"] <= 0:
                logger.error(f"Недопустимое значение ban_duration: {settings['ban_duration']}")
                return False
            if not isinstance(settings["warning_threshold"], int) or settings["warning_threshold"] < 1:
                logger.error(f"Недопустимое значение warning_threshold: {settings['warning_threshold']}")
                return False
            if not isinstance(settings["max_messages_per_minute"], int) or settings["max_messages_per_minute"] < 1:
                logger.error(f"Недопустимое значение max_messages_per_minute: {settings['max_messages_per_minute']}")
                return False
            if not isinstance(settings["ignored_words"], list):
                logger.error(f"Недопустимое значение ignored_words: {settings['ignored_words']}")
                return False
            if not isinstance(settings["auto_kick_inactive"], bool):
                logger.error(f"Недопустимое значение auto_kick_inactive: {settings['auto_kick_inactive']}")
                return False

            for key in optional_keys & settings.keys():
                if not isinstance(settings[key], dict):
                    logger.error(f"Недопустимый формат для {key}: ожидается словарь, получено {type(settings[key])}")
                    return False
                sub_settings = settings[key]
                if "enabled" not in sub_settings or not isinstance(sub_settings["enabled"], bool):
                    logger.error(f"Недопустимое значение enabled в {key}: {sub_settings.get('enabled')}")
                    return False
                if "action" not in sub_settings or sub_settings["action"] not in ["warn", "mute", "ban", "delete"]:
                    logger.error(f"Недопустимое действие в {key}: {sub_settings.get('action')}")
                    return False
                if sub_settings["action"] in ["warn", "mute", "ban"]:
                    if "duration" not in sub_settings or not isinstance(sub_settings["duration"], int) or sub_settings[
                        "duration"] <= 0:
                        logger.error(f"Недопустимое значение duration в {key}: {sub_settings.get('duration')}")
                        return False
                if key in ["repeated_words", "repeated_messages", "flood"]:
                    if "limit" not in sub_settings or not isinstance(sub_settings["limit"], int) or sub_settings[
                        "limit"] < 1:
                        logger.error(f"Недопустимое значение limit в {key}: {sub_settings.get('limit')}")
                        return False
            return True
        return True
    except Exception as e:
        logger.error(f"Ошибка валидации настроек {setting_type}: {str(e)}")
        return False

async def is_spamming(chat_id: int, user_id: int, limit: int = 5, seconds: int = 10) -> bool:
    """
    Проверяет, превышает ли пользователь лимит сообщений за заданный интервал времени.

    Args:
        chat_id: ID чата.
        user_id: ID пользователя.
        limit: Максимальное количество сообщений за интервал (по умолчанию 5).
        seconds: Интервал времени в секундах для проверки (по умолчанию 10).

    Возвращает:
        bool: True, если пользователь спамит, иначе False.
    """
    try:
        async with redis_client() as redis:
            key = f"spam:{chat_id}:{user_id}"
            current_time = time.time()

            # Увеличиваем счетчик сообщений
            count = await redis.incr(key)
            if count == 1:
                # Устанавливаем TTL для нового счетчика
                await redis.expire(key, seconds)
                await redis.setex(f"last_message:{chat_id}:{user_id}", seconds, current_time)
                logger.debug(f"Начало отслеживания сообщений для user_id={user_id} в chat_id={chat_id}")
                return False

            # Проверяем превышение лимита
            if count > limit:
                # Устанавливаем флаг блокировки
                block_key = f"block:{chat_id}:{user_id}"
                block_duration = 30  # 30 секунд блокировки по умолчанию
                await redis.setex(block_key, block_duration, "1")
                logger.info(f"Пользователь {user_id} в chat_id={chat_id} помечен как спамер (сообщений: {count})")
                return True

            # Обновляем timestamp последнего сообщения
            await redis.setex(f"last_message:{chat_id}:{user_id}", seconds, current_time)
            logger.debug(f"Сообщение от user_id={user_id} в chat_id={chat_id}, счетчик: {count}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при проверке спама для user_id={user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def reset_spam_state(chat_id: int, user_id: int) -> None:
    """
    Сбрасывает состояние спама для пользователя в указанном чате (удаляет счетчик и timestamp).

    Args:
        chat_id: ID чата.
        user_id: ID пользователя.
    """
    try:
        async with redis_client() as redis:
            keys = [f"spam:{chat_id}:{user_id}", f"last_message:{chat_id}:{user_id}", f"repeated_messages:{chat_id}:{user_id}"]
            await redis.delete(*keys)
            logger.info(f"Состояние спама сброшено для user_id={user_id} в chat_id={chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при сбросе состояния спама для user_id={user_id} в chat_id={chat_id}: {str(e)}")

async def get_ttl(chat_id: int, user_id: int) -> int:
    """
    Возвращает оставшееся время до разблокировки пользователя в указанном чате.

    Args:
        chat_id: ID чата.
        user_id: ID пользователя.

    Возвращает:
        int: Оставшееся время в секундах до конца блокировки, или 0, если пользователь не заблокирован.
    """
    try:
        async with redis_client() as redis:
            block_key = f"block:{chat_id}:{user_id}"
            ttl = await redis.ttl(block_key)
            if ttl < 0:  # Ключ не существует или без TTL
                logger.debug(f"Пользователь user_id={user_id} в chat_id={chat_id} не заблокирован")
                return 0
            logger.debug(f"Оставшееся время блокировки для user_id={user_id} в chat_id={chat_id}: {ttl} секунд")
            return ttl
    except Exception as e:
        logger.error(f"Ошибка при получении TTL для user_id={user_id} в chat_id={chat_id}: {str(e)}")
        return 0

@cached(ttl=3600, cache=Cache.MEMORY, key_builder=lambda f, *args, **kwargs: f"{args[0]}:{args[1]}")
async def get_settings(setting_type: str, chat_id: int) -> Optional[Dict]:
    """
    Получает настройки указанного типа для чата из Redis с кэшированием.

    Args:
        setting_type: Тип настроек (например, 'antispam').
        chat_id: ID чата.

    Возвращает:
        Optional[Dict]: Словарь настроек или None, если настройки не найдены.
    """
    try:
        async with redis_client() as redis:
            key = f"settings:{setting_type}:{chat_id}"
            settings = await redis.get(key)
            if settings:
                parsed_settings = json.loads(settings)
                logger.debug(f"Найдены настройки {setting_type} для chat_id={chat_id}: {parsed_settings}")
                return parsed_settings
            logger.debug(f"Настройки {setting_type} для chat_id={chat_id} не найдены")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении настроек {setting_type} для chat_id={chat_id}: {str(e)}")
        return None

async def save_settings(setting_type: str, chat_id: int, settings: Dict, ttl: Optional[int] = 604800) -> bool:
    """
    Сохраняет настройки указанного типа для чата в Redis.

    Args:
        setting_type: Тип настроек (например, 'antispam').
        chat_id: ID чата.
        settings: Словарь настроек.
        ttl: Время жизни ключа в секундах (по умолчанию 7 дней).

    Возвращает:
        bool: True, если настройки сохранены, иначе False.
    """
    try:
        if not await validate_settings(setting_type, settings):
            logger.error(f"Невалидные настройки {setting_type} для chat_id={chat_id}: {settings}")
            return False
        async with redis_client() as redis:
            key = f"settings:{setting_type}:{chat_id}"
            await redis.set(key, json.dumps(settings), ex=ttl)
            await settings_cache.set(f"{setting_type}:{chat_id}", settings, ttl=3600)
            logger.info(f"Настройки {setting_type} сохранены для chat_id={chat_id} с TTL={ttl}s: {settings}")
            return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении настроек {setting_type} для chat_id={chat_id}: {str(e)}")
        return False

async def get_all_settings() -> Dict[int, Dict]:
    """
    Получает все настройки для всех известных чатов.

    Возвращает:
        Dict[int, Dict]: Словарь с настройками для каждого чата.
    """
    try:
        async with redis_client() as redis:
            settings = {}
            known_chats = await get_known_chats()
            setting_types = ["antispam", "tlink"]
            pipeline = redis.pipeline()
            for chat_id in known_chats:
                for setting_type in setting_types:
                    pipeline.get(f"settings:{setting_type}:{chat_id}")
            results = await pipeline.execute()

            index = 0
            for chat_id in known_chats:
                chat_settings = {}
                for setting_type in setting_types:
                    data = results[index]
                    index += 1
                    if data:
                        parsed_settings = json.loads(data)
                        chat_settings[setting_type] = parsed_settings
                        await settings_cache.set(f"{setting_type}:{chat_id}", parsed_settings, ttl=3600)
                if chat_settings:
                    settings[chat_id] = chat_settings
            logger.info(f"Получены настройки для {len(settings)} чатов")
            return settings
    except Exception as e:
        logger.error(f"Ошибка при получении всех настроек: {str(e)}")
        return {}

async def save_all_settings(settings: Dict[int, Dict], ttl: Optional[int] = 604800) -> bool:
    """
    Сохраняет все настройки для всех чатов в Redis.

    Args:
        settings: Словарь с настройками для каждого чата.
        ttl: Время жизни ключей в секундах (по умолчанию 7 дней).

    Возвращает:
        bool: True, если настройки сохранены, иначе False.
    """
    try:
        async with redis_client() as redis:
            pipeline = redis.pipeline()
            for chat_id, chat_settings in settings.items():
                for setting_type, setting_data in chat_settings.items():
                    if not await validate_settings(setting_type, setting_data):
                        logger.error(f"Невалидные настройки {setting_type} для chat_id={chat_id}: {setting_data}")
                        continue
                    key = f"settings:{setting_type}:{chat_id}"
                    pipeline.set(key, json.dumps(setting_data), ex=ttl)
                    await settings_cache.set(f"{setting_type}:{chat_id}", setting_data, ttl=3600)
            await pipeline.execute()
            logger.info(f"Настройки сохранены для {len(settings)} чатов с TTL={ttl}s")
            return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении всех настроек: {str(e)}")
        return False

async def preload_antispam_settings() -> bool:
    """
    Предварительно загружает настройки антиспама для всех известных чатов в Redis.

    Возвращает:
        bool: True, если предзагрузка успешна, иначе False.
    """
    try:
        async with redis_client() as redis:
            known_chats = await get_known_chats()
            default_antispam_settings = {
                "enabled": False,
                "repeated_words_limit": 3,
                "case_sensitive": False,
                "action": "warn",
                "mute_duration": 3600,
                "ban_duration": 86400,
                "warning_threshold": 3,
                "max_messages_per_minute": 10,
                "ignored_words": [],
                "auto_kick_inactive": False,
                "telegram_links": {"enabled": False, "action": "delete", "duration": 0},
                "repeated_words": {"enabled": False, "limit": 3, "action": "warn", "duration": 3600},
                "repeated_messages": {"enabled": False, "limit": 3, "action": "warn", "duration": 1800},
                "flood": {"enabled": False, "limit": 10, "action": "warn", "duration": 3600},
                "external_links": {"enabled": False, "action": "delete", "duration": 0},
                "media_filter": {"enabled": False, "action": "delete", "duration": 0}
            }
            pipeline = redis.pipeline()
            for chat_id in known_chats:
                key = f"settings:antispam:{chat_id}"
                pipeline.get(key)
            results = await pipeline.execute()

            pipeline = redis.pipeline()
            index = 0
            for chat_id in known_chats:
                settings = results[index]
                index += 1
                if not settings:
                    pipeline.set(key, json.dumps(default_antispam_settings), ex=604800)
                    await settings_cache.set(f"antispam:{chat_id}", default_antispam_settings, ttl=3600)
                    logger.info(
                        f"Установлены настройки антиспама по умолчанию для chat_id={chat_id}: {default_antispam_settings}")
                else:
                    parsed_settings = json.loads(settings)
                    await settings_cache.set(f"antispam:{chat_id}", parsed_settings, ttl=3600)
                    logger.debug(f"Настройки антиспама уже существуют для chat_id={chat_id}: {parsed_settings}")
            await pipeline.execute()
            logger.info(f"Предзагрузка настроек антиспама завершена для {len(known_chats)} чатов")
            return True
    except Exception as e:
        logger.error(f"Ошибка при предзагрузке настроек антиспама: {str(e)}")
        return False

async def check_repeated_words(message: Message) -> bool:
    """
    Проверяет сообщение на наличие повторяющихся слов и применяет антиспам-действия.

    Args:
        message: Объект сообщения Telegram.

    Возвращает:
        bool: True, если обнаружено нарушение, иначе False.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text or message.caption or ""

    if not await ensure_user_exists(
            user_id=user_id,
            chat_id=chat_id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
            is_bot=message.from_user.is_bot
    ):
        logger.warning(f"Не удалось проверить или зарегистрировать пользователя {user_id} для chat_id={chat_id}")
        return False

    settings = await get_settings("antispam", chat_id)
    if not settings or not settings.get("enabled", False) or not settings.get("repeated_words", {}).get("enabled",
                                                                                                        False):
        logger.debug(f"Проверка повторяющихся слов отключена для chat_id={chat_id}")
        return False

    words = text.split()
    repeated_words_settings = settings.get("repeated_words", {})
    limit = repeated_words_settings.get("limit", 3)
    if len(words) < limit:
        return False

    ignored_words = settings.get("ignored_words", [])
    repeated_count = 1
    prev_word = None
    for word in words:
        current_word = word.lower() if not settings["case_sensitive"] else word
        if current_word in ignored_words:
            repeated_count = 1
            prev_word = None
            continue
        if prev_word and current_word == prev_word:
            repeated_count += 1
            if repeated_count >= limit:
                logger.info(
                    f"Обнаружено {repeated_count} повторяющихся слов ('{word}') от user_id={user_id} в chat_id={chat_id}")
                return await apply_antispam_action(user_id, chat_id, settings, message, "repeated_words")
        else:
            repeated_count = 1
        prev_word = current_word
    return False

async def check_repeated_messages(message: Message) -> bool:
    """
    Проверяет сообщение на повторение подряд и применяет антиспам-действия.

    Args:
        message: Объект сообщения Telegram.

    Возвращает:
        bool: True, если обнаружено нарушение, иначе False.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text or message.caption or ""

    if not await ensure_user_exists(
            user_id=user_id,
            chat_id=chat_id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
            is_bot=message.from_user.is_bot
    ):
        logger.warning(f"Не удалось проверить или зарегистрировать пользователя {user_id} для chat_id={chat_id}")
        return False

    settings = await get_settings("antispam", chat_id)
    if not settings or not settings.get("enabled", False) or not settings.get("repeated_messages", {}).get("enabled", False):
        logger.debug(f"Проверка повторяющихся сообщений отключена для chat_id={chat_id}")
        return False

    async with redis_client() as redis:
        message_key = f"repeated_messages:{chat_id}:{user_id}"
        message_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        count_key = f"repeated_messages_count:{chat_id}:{user_id}"

        # Получаем текущий счетчик повторений
        current_count = await redis.get(count_key)
        current_count = int(current_count) if current_count else 0

        # Получаем последнее сообщение
        last_message = await redis.get(message_key)

        if last_message and last_message == message_hash:
            current_count += 1
            await redis.set(count_key, current_count, ex=3600)
            logger.debug(f"Повтор сообщения от user_id={user_id} в chat_id={chat_id}, счетчик: {current_count}")

            # Проверка на нарушение
            if current_count >= 3 and current_count < 6:
                settings["repeated_messages"]["action"] = "warn"
                settings["repeated_messages"]["duration"] = 3600
                await message.delete()  # Удаляем сообщение
                logger.info(f"Удалено повторяющееся сообщение от user_id={user_id} в chat_id={chat_id}, счетчик: {current_count}")
                return await apply_antispam_action(user_id, chat_id, settings, message, "repeated_messages")
            elif current_count >= 6:
                settings["repeated_messages"]["action"] = "mute"
                settings["repeated_messages"]["duration"] = 1800  # 30 минут
                await message.delete()  # Удаляем сообщение
                logger.info(f"Удалено повторяющееся сообщение от user_id={user_id} в chat_id={chat_id}, счетчик: {current_count}")
                return await apply_antispam_action(user_id, chat_id, settings, message, "repeated_messages")
        else:
            # Сбрасываем счетчик, если сообщение новое
            await redis.set(message_key, message_hash, ex=3600)
            await redis.set(count_key, 1, ex=3600)
            logger.debug(f"Новое сообщение от user_id={user_id} в chat_id={chat_id}, счетчик сброшен")
        return False

async def apply_antispam_action(user_id: int, chat_id: int, settings: Dict, message: Message,
                                violation_type: str = None) -> bool:
    """
    Применяет антиспам-действие на основе настроек и типа нарушения.

    Args:
        user_id: ID пользователя.
        chat_id: ID чата.
        settings: Словарь настроек антиспама.
        message: Объект сообщения Telegram.
        violation_type: Тип нарушения (например, 'repeated_words', 'flood').

    Возвращает:
        bool: True, если действие успешно применено, иначе False.
    """
    try:
        user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        violation_settings = settings.get(violation_type, settings) if violation_type else settings
        action = violation_settings.get("action", "warn")
        warnings = user.warnings.get(str(chat_id), [])
        warning_count = len(warnings)

        # Проверка, замучен ли пользователь
        is_muted = user.mutes.get(str(chat_id), {}).get("is_muted", False)
        if is_muted and action in ["warn", "mute"]:
            logger.debug(f"Пропуск действия {action} для user_id={user_id} в chat_id={chat_id}: пользователь уже замучен")
            return True  # Не отправляем уведомления, если пользователь уже замучен

        # Проверка кэша уведомлений
        notification_key = f"notify:{chat_id}:{user_id}:{violation_type}"
        if await notification_cache.get(notification_key):
            logger.debug(f"Уведомление для user_id={user_id} в chat_id={chat_id} уже отправлено, пропуск")
            return True

        punishment_record = {
            "reason": f"Нарушение: {violation_type or 'основное правило антиспама'}",
            "issued_by": message.bot.id,
            "issued_at": time.time()
        }

        # Формируем упоминание пользователя
        user_mention = f"@{user.username}" if user.username else user.display_name or f"User {user_id}"

        if action == "delete":
            try:
                await message.delete()
                logger.info(f"Сообщение удалено для user_id={user_id} в chat_id={chat_id} за {punishment_record['reason']}")
                return True
            except Exception as e:
                logger.error(f"Не удалось удалить сообщение для user_id={user_id} в chat_id={chat_id}: {str(e)}")
                return False

        if action == "warn":
            if warning_count < settings["warning_threshold"]:
                success = await add_warning(user_id, chat_id, punishment_record["reason"], message.bot.id)
                if success:
                    await asyncio.sleep(1)  # Задержка для предотвращения лимитов Telegram
                    await message.reply(
                        f"⚠️ Пользователь {user_mention} получил предупреждение за {punishment_record['reason']}.")
                    await notification_cache.set(notification_key, True, ttl=60)
                    logger.info(f"Выдано предупреждение пользователю {user_id} в chat_id={chat_id}")
                    return True
            else:
                action = settings.get("action", "mute")
                punishment_record[
                    "reason"] = f"Превышен порог предупреждений ({settings['warning_threshold']}) за {violation_type or 'основное правило'}"

        if action == "mute":
            duration = violation_settings.get("duration", settings.get("mute_duration", 3600))
            success = await mute_user(user_id, chat_id, duration, punishment_record["reason"], message.bot.id)
            if success:
                await asyncio.sleep(1)  # Задержка для предотвращения лимитов Telegram
                await message.reply(
                    f"🔇 Пользователь {user_mention} замучен на {duration // 60} минут за {punishment_record['reason']}.")
                await notification_cache.set(notification_key, True, ttl=60)
                logger.info(f"Пользователь {user_id} замучен в chat_id={chat_id}")
                return True

        if action == "ban":
            duration = violation_settings.get("duration", settings.get("ban_duration", 86400))
            success = await ban_user(user_id, chat_id, punishment_record["reason"], message.bot.id, duration)
            if success:
                await asyncio.sleep(1)  # Задержка для предотвращения лимитов Telegram
                await message.reply(
                    f"🚫 Пользователь {user_mention} забанен на {duration // 3600} часов за {punishment_record['reason']}.")
                await notification_cache.set(notification_key, True, ttl=60)
                logger.info(f"Пользователь {user_id} забанен в chat_id={chat_id}")
                return True

        return False
    except Exception as e:
        logger.error(f"Ошибка при применении антиспам-действия для user_id={user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def get_antispam_stats(chat_id: int) -> Dict:
    """
    Получает статистику антиспама для указанного чата.

    Args:
        chat_id: ID чата.

    Возвращает:
        Dict: Словарь со статистикой (warnings, mutes, bans, users).
    """
    try:
        db = await get_database()
        stats = {
            "warnings": 0,
            "mutes": 0,
            "bans": 0,
            "users": 0
        }
        async for user in db.users.find({"group_ids": chat_id}):
            stats["users"] += 1
            stats["warnings"] += len(user.get("warnings", {}).get(str(chat_id), []))
            stats["mutes"] += 1 if user.get("mutes", {}).get(str(chat_id), {}).get("is_muted", False) else 0
            stats["bans"] += 1 if user.get("bans", {}).get(str(chat_id), {}).get("is_banned", False) else 0
        logger.info(f"Получена статистика антиспама для chat_id={chat_id}: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Ошибка при получении статистики антиспама для chat_id={chat_id}: {str(e)}")
        return {}

async def kick_inactive_users(chat_id: int, bot: aiogram.Bot, inactivity_days: int = 30) -> int:
    """
    Удаляет неактивных пользователей из чата, если включена настройка auto_kick_inactive.

    Args:
        chat_id: ID чата.
        bot: Экземпляр бота aiogram.
        inactivity_days: Количество дней неактивности для исключения (по умолчанию 30).

    Возвращает:
        int: Количество исключенных пользователей.
    """
    try:
        settings = await get_settings("antispam", chat_id)
        if not settings or not settings.get("auto_kick_inactive", False):
            logger.debug(f"Автокик неактивных пользователей отключен для chat_id={chat_id}")
            return 0

        db = await get_database()
        threshold = time.time() - (inactivity_days * 86400)
        kicked_count = 0
        async for user in db.users.find({"group_ids": chat_id}):
            last_active = user.get("last_active", 0)
            if last_active < threshold:
                try:
                    await bot.ban_chat_member(chat_id, user["user_id"])
                    await kick_user(user["user_id"], chat_id, f"Неактивность более {inactivity_days} дней", bot.id)
                    await db.users.update_one(
                        {"user_id": user["user_id"]},
                        {
                            "$pull": {"group_ids": chat_id},
                            "$set": {
                                f"warnings.{chat_id}": [],
                                f"mutes.{chat_id}": {"is_muted": False, "until": 0.0, "reason": "", "issued_by": 0,
                                                     "issued_at": 0.0},
                                f"bans.{chat_id}": {"is_banned": False, "reason": "", "issued_by": 0, "issued_at": 0.0,
                                                    "until": 0.0}
                            }
                        }
                    )
                    kicked_count += 1
                    logger.info(f"Пользователь {user['user_id']} исключен из chat_id={chat_id} за неактивность")
                except Exception as e:
                    logger.error(f"Ошибка при исключении пользователя {user['user_id']} из chat_id={chat_id}: {str(e)}")
        logger.info(f"Исключено {kicked_count} неактивных пользователей из chat_id={chat_id}")
        return kicked_count
    except Exception as e:
        logger.error(f"Ошибка при исключении неактивных пользователей для chat_id={chat_id}: {str(e)}")
        return 0