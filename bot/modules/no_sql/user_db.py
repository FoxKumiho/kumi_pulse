# Путь файла: bot/modules/no_sql/user_db.py

import time
import os
from pathlib import Path
from typing import Dict, Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from bson import ObjectId
from loguru import logger
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
import aiogram
from aiocache import cached

# Проверка версии aiogram
assert aiogram.__version__ == "3.20.0.post0", f"Expected aiogram version 3.20.0.post0, but found {aiogram.__version__}"

# Настройка loguru
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
LOG_FILE = BASE_DIR / "app.log"
os.makedirs(BASE_DIR, exist_ok=True)  # Создаём директорию, если она отсутствует
try:
    logger.add(
        LOG_FILE,
        format="{time} {level} {message}",
        level="INFO",
        rotation="10 MB",
        retention="7 days"
    )
    logger.info(f"Логирование настроено для файла: {LOG_FILE}")
except PermissionError as e:
    logger.error(f"Ошибка прав доступа при настройке логирования в {LOG_FILE}: {str(e)}")
    raise
except Exception as e:
    logger.error(f"Ошибка при настройке логирования: {str(e)}")
    raise

# Загружаем переменные из .env файла
ENV_FILE = BASE_DIR / "config" / ".env"
if not ENV_FILE.exists():
    logger.error(f"Файл {ENV_FILE} не найден. Убедитесь, что он существует в папке config/")
    raise FileNotFoundError(f"Файл {ENV_FILE} не найден. Убедитесь, что он существует в папке config/")
load_dotenv(dotenv_path=ENV_FILE)

# Получаем OWNER_BOT_ID из .env
try:
    OWNER_BOT_ID = int(os.getenv("OWNER_BOT_ID", 0))
    if OWNER_BOT_ID <= 0:
        logger.error("OWNER_BOT_ID не указан или недействителен в .env файле")
        raise ValueError("OWNER_BOT_ID не указан или недействителен в .env файле")
except ValueError as e:
    logger.error(f"Ошибка при загрузке OWNER_BOT_ID: {str(e)}")
    raise

# Допустимые действия модерации
VALID_MODERATION_ACTIONS = {"warn", "ban", "mute", "unban", "unmute", "kick", "clear_warnings", "delete"}

# Словарь для сопоставления уровней ролей с их названиями
ROLE_NAMES = {
    0: "Пользователь",
    1: "Младший модератор",
    2: "Старший модератор",
    3: "Младший админ",
    4: "Старший админ",
    5: "Заместитель",
    6: "Владелец сервера",
    7: "Владелец бота"
}

async def get_user_collection() -> AsyncIOMotorCollection:
    """Возвращает коллекцию users из базы данных."""
    from .mongo_client import get_database
    db = await get_database()
    return db["users"]

async def get_chat_collection() -> AsyncIOMotorCollection:
    """Возвращает коллекцию chats из базы данных."""
    from .mongo_client import get_database
    db = await get_database()
    return db["chats"]

async def get_moderation_logs_collection() -> AsyncIOMotorCollection:
    """Возвращает коллекцию moderation_logs из базы данных."""
    from .mongo_client import get_database
    db = await get_database()
    return db["moderation_logs"]

class User:
    """Класс для представления пользователя."""
    def __init__(self, user_id: int, username: str = None, display_name: str = None,
                 group_ids: list = None, channel_ids: list = None, server_owner_chat_ids: list = None,
                 is_premium: bool = False, created_at: float = None, last_active: float = None,
                 minutes_active: int = 0, is_banned: bool = False, warnings: dict = None,
                 role_level: int = 0, is_bot: bool = False, id: str = None,
                 activity_count: Dict[str, int] = None, bans: dict = None, mutes: dict = None):
        self.id = id
        self.user_id = user_id
        self.username = username
        self.display_name = display_name
        self.group_ids = group_ids or []
        self.channel_ids = channel_ids or []
        self.server_owner_chat_ids = server_owner_chat_ids or []
        self.is_premium = is_premium
        self.created_at = created_at or time.time()
        self.last_active = last_active or time.time()
        self.minutes_active = minutes_active
        self.is_banned = is_banned  # Устаревшее поле, сохранено для обратной совместимости
        self.warnings = warnings or {}
        self.role_level = role_level
        self.is_bot = is_bot
        self.activity_count = activity_count or {}
        self.bans = bans or {}
        self.mutes = mutes or {}

    def to_dict(self) -> Dict:
        """Преобразует объект User в словарь для сохранения в MongoDB."""
        return {
            "id": ObjectId(self.id) if self.id else ObjectId(),
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "group_ids": self.group_ids,
            "channel_ids": self.channel_ids,
            "server_owner_chat_ids": self.server_owner_chat_ids,
            "is_premium": self.is_premium,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "minutes_active": self.minutes_active,
            "is_banned": self.is_banned,
            "warnings": {str(k): v for k, v in self.warnings.items()},
            "role_level": self.role_level,
            "is_bot": self.is_bot,
            "activity_count": {str(k): v for k, v in self.activity_count.items()},
            "bans": {str(k): v for k, v in self.bans.items()},
            "mutes": {str(k): v for k, v in self.mutes.items()}
        }

    @staticmethod
    def from_dict(data: Dict) -> 'User':
        """Создает объект User из словаря MongoDB."""
        return User(
            id=str(data.get("id")),
            user_id=data["user_id"],
            username=data.get("username"),
            display_name=data.get("display_name"),
            group_ids=data.get("group_ids", []),
            channel_ids=data.get("channel_ids", []),
            server_owner_chat_ids=data.get("server_owner_chat_ids", []),
            is_premium=data.get("is_premium", False),
            created_at=data.get("created_at"),
            last_active=data.get("last_active"),
            minutes_active=data.get("minutes_active", 0),
            is_banned=data.get("is_banned", False),
            warnings=data.get("warnings", {}),
            role_level=data.get("role_level", 0),
            is_bot=data.get("is_bot", False),
            activity_count=data.get("activity_count", {}),
            bans=data.get("bans", {}),
            mutes=data.get("mutes", {})
        )

    def get_role_for_chat(self, chat_id: int) -> str:
        """Возвращает название роли для указанного чата."""
        if self.user_id == OWNER_BOT_ID:
            return ROLE_NAMES[7]
        if chat_id in self.server_owner_chat_ids:
            return ROLE_NAMES[6]
        return ROLE_NAMES.get(self.role_level, "Неизвестная роль")

    def get_activity_count(self, chat_id: int) -> int:
        """Возвращает счетчик активности для указанного чата."""
        return self.activity_count.get(str(chat_id), 0)

    def is_banned_in_chat(self, chat_id: int) -> bool:
        """Проверяет, забанен ли пользователь в указанном чате."""
        ban_info = self.bans.get(str(chat_id), {})
        if ban_info.get("is_banned", False):
            until = ban_info.get("until", 0.0)
            if until == 0.0 or until > time.time():
                return True
            # Срок бана истек
            self.bans[str(chat_id)] = {
                "is_banned": False, "reason": "", "issued_by": 0, "issued_at": 0.0, "until": 0.0
            }
        return False

    def is_muted_in_chat(self, chat_id: int) -> bool:
        """Проверяет, замучен ли пользователь в указанном чате."""
        mute_info = self.mutes.get(str(chat_id), {})
        if mute_info.get("is_muted", False):
            until = mute_info.get("until", 0.0)
            if until > time.time():
                return True
            # Срок мута истек
            self.mutes[str(chat_id)] = {
                "is_muted": False, "until": 0.0, "reason": "", "issued_by": 0, "issued_at": 0.0
            }
        return False

async def ensure_user_exists(
    user_id: int,
    chat_id: int,
    username: Optional[str] = None,
    display_name: Optional[str] = None,
    is_bot: bool = False
) -> User:
    """Гарантирует существование пользователя в базе данных, создавая или обновляя запись."""
    if not isinstance(user_id, int) or user_id <= 0:
        logger.error(f"Недействительный user_id: {user_id}")
        raise ValueError("user_id должен быть положительным целым числом")
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")

    try:
        # Проверяем, существует ли пользователь
        user = await get_user(user_id, create_if_not_exists=False, chat_id=chat_id)
        # Обновляем данные пользователя
        updates = {
            "username": username,
            "display_name": display_name,
            "is_bot": is_bot,
            "last_active": time.time()
        }
        if chat_id not in user.group_ids:
            updates["group_ids"] = user.group_ids + [chat_id]
        if user_id == OWNER_BOT_ID and user.role_level != 7:
            updates["role_level"] = 7
        await update_user(user_id, updates)
        logger.info(f"Обновлен пользователь user_id={user_id} для chat_id={chat_id}")
        return await get_user(user_id, chat_id=chat_id)
    except ValueError:
        # Пользователь не найден, создаем нового
        role_level = 7 if user_id == OWNER_BOT_ID else 0
        user = User(
            user_id=user_id,
            username=username,
            display_name=display_name,
            group_ids=[chat_id],
            is_bot=is_bot,
            role_level=role_level
        )
        logger.info(f"Создается новый пользователь user_id={user_id} для chat_id={chat_id}")
        return await create_user(user, chat_id=chat_id)
    except Exception as e:
        logger.error(f"Ошибка при создании/обновлении пользователя user_id={user_id} в chat_id={chat_id}: {str(e)}")
        raise

async def init_moderation_logs_collection():
    """Инициализирует коллекцию moderation_logs с индексами по chat_id и issued_at."""
    collection = await get_moderation_logs_collection()
    try:
        await collection.create_index([("chat_id", 1), ("issued_at", -1)])
        logger.info("Индекс для moderation_logs (chat_id, issued_at) создан или уже существует")
    except Exception as e:
        logger.error(f"Ошибка при инициализации коллекции moderation_logs: {e}")
        raise

async def init_user_collection():
    """Инициализирует коллекцию users с индексом и выполняет миграцию данных."""
    collection = await get_user_collection()
    try:
        await collection.create_index("user_id", unique=True)
        logger.info("Индекс для user_id создан или уже существует")

        # Миграция данных: исправление некорректных типов и инициализация полей
        async for user in collection.find({}):
            updates = {}
            if not isinstance(user.get("warnings"), dict):
                updates["warnings"] = {}
            if not isinstance(user.get("bans"), dict):
                updates["bans"] = {}
            if not isinstance(user.get("mutes"), dict):
                updates["mutes"] = {}
            if not isinstance(user.get("activity_count"), dict):
                updates["activity_count"] = {}
            if user.get("user_id") == OWNER_BOT_ID and user.get("role_level", 0) != 7:
                updates["role_level"] = 7
            known_chats = await get_known_chats()
            for chat_id in known_chats:
                chat_id_str = str(chat_id)
                if chat_id_str not in user.get("activity_count", {}):
                    updates[f"activity_count.{chat_id_str}"] = 0
                if chat_id_str not in user.get("warnings", {}):
                    updates[f"warnings.{chat_id_str}"] = []
                if chat_id_str not in user.get("bans", {}):
                    updates[f"bans.{chat_id_str}"] = {
                        "is_banned": False, "reason": "", "issued_by": 0, "issued_at": 0.0, "until": 0.0
                    }
                if chat_id_str not in user.get("mutes", {}):
                    updates[f"mutes.{chat_id_str}"] = {
                        "is_muted": False, "until": 0.0, "reason": "", "issued_by": 0, "issued_at": 0.0
                    }
            if updates:
                await collection.update_one(
                    {"user_id": user["user_id"]},
                    {"$set": updates}
                )
                logger.info(f"Миграция данных для user_id={user['user_id']}: исправлены поля {list(updates.keys())}")
    except Exception as e:
        logger.error(f"Ошибка при инициализации коллекции пользователей: {e}")
        raise

async def initialize_user_fields(user: User, chat_id: Optional[int] = None) -> User:
    """Инициализирует поля пользователя для всех известных чатов."""
    known_chats = await get_known_chats()
    if chat_id and chat_id not in known_chats:
        known_chats.append(chat_id)
    for known_chat_id in known_chats:
        chat_id_str = str(known_chat_id)
        if chat_id_str not in user.activity_count:
            user.activity_count[chat_id_str] = 0
        if chat_id_str not in user.warnings:
            user.warnings[chat_id_str] = []
        if chat_id_str not in user.bans:
            user.bans[chat_id_str] = {"is_banned": False, "reason": "", "issued_by": 0, "issued_at": 0.0, "until": 0.0}
        if chat_id_str not in user.mutes:
            user.mutes[chat_id_str] = {"is_muted": False, "until": 0.0, "reason": "", "issued_by": 0, "issued_at": 0.0}
    return user

async def create_user(user: User, chat_id: Optional[int] = None) -> User:
    """Создает нового пользователя в базе данных или обновляет существующего."""
    if not isinstance(user.user_id, int) or user.user_id <= 0:
        logger.error(f"Недействительный user_id: {user.user_id}")
        raise ValueError("user_id должен быть положительным целым числом")

    if user.role_level not in ROLE_NAMES:
        logger.error(f"Недействительный role_level: {user.role_level}")
        raise ValueError(f"role_level должен быть одним из: {list(ROLE_NAMES.keys())}")

    if user.user_id == OWNER_BOT_ID:
        user.role_level = 7
        logger.info(f"Пользователь {user.user_id} определен как владелец бота, присвоен role_level: 7")

    user = await initialize_user_fields(user, chat_id)
    collection = await get_user_collection()
    try:
        result = await collection.insert_one(user.to_dict())
        user.id = str(result.inserted_id)
        logger.info(f"Создан пользователь: {user.user_id}, роль: {user.get_role_for_chat(chat_id)}, id: {user.id}, chat_id={chat_id}")
        return user
    except DuplicateKeyError:
        updates = {
            "username": user.username,
            "display_name": user.display_name,
            "is_bot": user.is_bot,
            "last_active": time.time()
        }
        if user.user_id == OWNER_BOT_ID:
            updates["role_level"] = 7
        if chat_id and chat_id not in user.group_ids:
            updates["group_ids"] = user.group_ids + [chat_id]
        await update_user(user.user_id, updates)
        logger.info(f"Обновлен пользователь: {user.user_id}, роль: {ROLE_NAMES.get(updates.get('role_level', 0), 'Неизвестная роль')}, chat_id={chat_id}")
        return await get_user(user.user_id, create_if_not_exists=False, chat_id=chat_id)

async def get_user(user_id: int, create_if_not_exists: bool = False, chat_id: Optional[int] = None) -> User:
    """Получает информацию о пользователе по user_id или создает нового, если указано."""
    if not isinstance(user_id, int) or user_id <= 0:
        logger.error(f"Недействительный user_id: {user_id}")
        raise ValueError("user_id должен быть положительным целым числом")

    collection = await get_user_collection()
    user_data = await collection.find_one({"user_id": user_id})
    if user_data:
        updates = {"last_active": time.time()}
        if not isinstance(user_data.get("warnings"), dict):
            updates["warnings"] = {}
        if not isinstance(user_data.get("bans"), dict):
            updates["bans"] = {}
        if not isinstance(user_data.get("mutes"), dict):
            updates["mutes"] = {}
        if not isinstance(user_data.get("activity_count"), dict):
            updates["activity_count"] = {}
        if user_id == OWNER_BOT_ID and user_data.get("role_level", 0) != 7:
            updates["role_level"] = 7
        if chat_id and chat_id not in user_data.get("group_ids", []):
            updates["group_ids"] = user_data.get("group_ids", []) + [chat_id]
        user = User.from_dict(dict(user_data))
        user = await initialize_user_fields(user, chat_id)
        if updates:
            await collection.update_one({"user_id": user_id}, {"$set": updates})
            user_data = await collection.find_one({"user_id": user_id})
            user = User.from_dict(dict(user_data))
        logger.info(f"Найден пользователь: {user_id}, роль: {user.get_role_for_chat(chat_id)}, chat_id={chat_id}")
        if user.is_banned_in_chat(chat_id) or user.is_muted_in_chat(chat_id):
            await update_user(user_id, {
                "bans": user.bans,
                "mutes": user.mutes
            })
        return user

    if create_if_not_exists:
        role_level = 7 if user_id == OWNER_BOT_ID else 0
        user = User(
            user_id=user_id,
            role_level=role_level,
            group_ids=[chat_id] if chat_id else []
        )
        return await create_user(user, chat_id=chat_id)

    logger.debug(f"Пользователь не найден: {user_id}")
    raise ValueError(f"Пользователь с user_id {user_id} не найден")

async def get_users_by_chat_id(chat_id: int) -> List[User]:
    """Получает список пользователей, связанных с указанным chat_id."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    collection = await get_user_collection()
    cursor = collection.find({
        "$or": [
            {"group_ids": chat_id},
            {"server_owner_chat_ids": chat_id}
        ]
    })
    users = [User.from_dict(dict(user_data)) async for user_data in cursor]
    for user in users:
        if user.is_banned_in_chat(chat_id) or user.is_muted_in_chat(chat_id):
            await update_user(user.user_id, {
                "bans": user.bans,
                "mutes": user.mutes
            })
    logger.info(f"Найдено {len(users)} пользователей для chat_id={chat_id}")
    return users

@cached(ttl=3600)
async def get_all_user_ids() -> List[int]:
    """Получает список всех user_id из коллекции users."""
    collection = await get_user_collection()
    cursor = collection.find({}, {"user_id": 1})
    user_ids = [doc["user_id"] async for doc in cursor]
    logger.info(f"Найдено {len(user_ids)} user_id в базе данных")
    return user_ids

async def update_user(user_id: int, updates: Dict) -> bool:
    """Обновляет информацию о пользователе."""
    if "role_level" in updates and updates["role_level"] not in ROLE_NAMES:
        logger.error(f"Недействительный role_level в updates: {updates['role_level']}")
        raise ValueError(f"role_level должен быть одним из: {list(ROLE_NAMES.keys())}")

    collection = await get_user_collection()
    update_doc = {"$set": {"last_active": time.time()}}
    for key, value in updates.items():
        if key == "group_ids" or key == "server_owner_chat_ids":
            update_doc["$addToSet"] = update_doc.get("$addToSet", {})
            update_doc["$addToSet"][key] = {"$each": value}
        elif key.startswith(("activity_count.", "warnings.", "bans.", "mutes.")):
            update_doc["$set"] = update_doc.get("$set", {})
            update_doc["$set"][key] = value
        elif key in ("warnings", "bans", "mutes", "activity_count"):
            update_doc["$set"][key] = {str(k): v for k, v in value.items()}
        else:
            update_doc["$set"][key] = value

    try:
        result = await collection.update_one({"user_id": user_id}, update_doc)
        if result.modified_count > 0:
            logger.info(f"Обновлен пользователь: {user_id}, обновления: {update_doc}")
            return True
        logger.debug(f"Не удалось обновить пользователя: {user_id}, возможно, данные не изменились")
        return False
    except Exception as e:
        logger.error(f"Ошибка при обновлении пользователя {user_id}: {str(e)}")
        return False

async def increment_activity_count(user_id: int, chat_id: int) -> bool:
    """Инкрементирует счетчик активности пользователя в указанном чате."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_user_collection()
        user = await collection.find_one({"user_id": user_id})
        if not user:
            logger.error(f"Пользователь {user_id} не найден для увеличения активности в chat_id={chat_id}")
            return False
        if user.get("is_bot", False):
            logger.debug(f"Пропущено увеличение активности для бота: user_id={user_id}, chat_id={chat_id}")
            return False
        result = await collection.update_one(
            {"user_id": user_id},
            {
                "$inc": {f"activity_count.{chat_id}": 1},
                "$set": {"last_active": time.time()}
            }
        )
        if result.modified_count > 0:
            updated_user = await get_user(user_id, chat_id=chat_id)
            logger.info(f"Счетчик активности увеличен для user_id={user_id} в chat_id={chat_id}, новый счет: {updated_user.get_activity_count(chat_id)}")
            return True
        logger.warning(f"Не удалось увеличить счетчик активности для user_id={user_id} в chat_id={chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при увеличении счетчика активности для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        return False

async def reset_activity_count(user_id: int, chat_id: int) -> bool:
    """Сбрасывает счетчик активности пользователя в указанном чате."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_user_collection()
        result = await collection.update_one(
            {"user_id": user_id},
            {
                "$set": {f"activity_count.{chat_id}": 0, "last_active": time.time()}
            }
        )
        if result.modified_count > 0:
            logger.info(f"Счетчик активности сброшен для user_id={user_id} в chat_id={chat_id}")
            return True
        logger.warning(f"Не удалось сбросить счетчик активности для user_id={user_id} в chat_id={chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при сбросе счетчика активности для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        return False

async def add_warning(user_id: int, chat_id: int, reason: str, issued_by: int) -> bool:
    """Добавляет предупреждение пользователю в указанном чате."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_user_collection()
        user = await collection.find_one({"user_id": user_id})
        if not user:
            logger.error(f"Пользователь {user_id} не найден для добавления предупреждения в chat_id={chat_id}")
            return False
        warning = {
            "reason": reason,
            "issued_by": issued_by,
            "issued_at": time.time()
        }
        result = await collection.update_one(
            {"user_id": user_id},
            {
                "$push": {f"warnings.{chat_id}": warning},
                "$set": {"last_active": time.time()}
            }
        )
        if result.modified_count > 0:
            await log_moderation_action(user_id, chat_id, "warn", reason, issued_by)
            logger.info(f"Добавлено предупреждение пользователю {user_id} в chat_id={chat_id}, причина: {reason}, выдано: {issued_by}")
            return True
        logger.warning(f"Не удалось добавить предупреждение пользователю {user_id} в chat_id={chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при добавлении предупреждения пользователю {user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def clear_warnings(user_id: int, chat_id: int, issued_by: int) -> bool:
    """Очищает предупреждения пользователя в указанном чате."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_user_collection()
        user = await collection.find_one({"user_id": user_id})
        if not user:
            logger.error(f"Пользователь {user_id} не найден для очистки предупреждений в chat_id={chat_id}")
            return False
        result = await collection.update_one(
            {"user_id": user_id},
            {
                "$set": {f"warnings.{chat_id}": [], "last_active": time.time()}
            }
        )
        if result.modified_count > 0:
            await log_moderation_action(user_id, chat_id, "clear_warnings", "Предупреждения очищены", issued_by)
            logger.info(f"Предупреждения очищены для пользователя {user_id} в chat_id={chat_id}, выдано: {issued_by}")
            return True
        logger.warning(f"Не удалось очистить предупреждения для пользователя {user_id} в chat_id={chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при очистке предупреждений для пользователя {user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def ban_user(user_id: int, chat_id: int, reason: str, issued_by: int, duration: float = None) -> bool:
    """Банит пользователя в указанном чате."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_user_collection()
        user = await collection.find_one({"user_id": user_id})
        if not user:
            logger.error(f"Пользователь {user_id} не найден для бана в chat_id={chat_id}")
            return False
        ban_info = {
            "is_banned": True,
            "reason": reason,
            "issued_by": issued_by,
            "issued_at": time.time(),
            "until": time.time() + duration if duration else 0.0
        }
        result = await collection.update_one(
            {"user_id": user_id},
            {
                "$set": {f"bans.{chat_id}": ban_info, "last_active": time.time()}
            }
        )
        if result.modified_count > 0:
            await log_moderation_action(user_id, chat_id, "ban", reason, issued_by, duration=duration, until_date=ban_info["until"])
            logger.info(f"Пользователь {user_id} забанен в chat_id={chat_id}, причина: {reason}, выдано: {issued_by}")
            return True
        logger.warning(f"Не удалось забанить пользователя {user_id} в chat_id={chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при бане пользователя {user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def unban_user(user_id: int, chat_id: int, issued_by: int) -> bool:
    """Разбанивает пользователя в указанном чате."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_user_collection()
        user = await collection.find_one({"user_id": user_id})
        if not user:
            logger.error(f"Пользователь {user_id} не найден для разбана в chat_id={chat_id}")
            return False
        ban_info = {
            "is_banned": False,
            "reason": "",
            "issued_by": 0,
            "issued_at": 0.0,
            "until": 0.0
        }
        result = await collection.update_one(
            {"user_id": user_id},
            {
                "$set": {f"bans.{chat_id}": ban_info, "last_active": time.time()}
            }
        )
        if result.modified_count > 0:
            await log_moderation_action(user_id, chat_id, "unban", "Бан снят", issued_by)
            logger.info(f"Пользователь {user_id} разбанен в chat_id={chat_id}")
            return True
        logger.warning(f"Не удалось разбанить пользователя {user_id} в chat_id={chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при разбане пользователя {user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def mute_user(user_id: int, chat_id: int, duration: float, reason: str, issued_by: int) -> bool:
    """Мутит пользователя в указанном чате на заданное время."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_user_collection()
        user = await collection.find_one({"user_id": user_id})
        if not user:
            logger.error(f"Пользователь {user_id} не найден для мута в chat_id={chat_id}")
            return False
        mute_info = {
            "is_muted": True,
            "until": time.time() + duration,
            "reason": reason,
            "issued_by": issued_by,
            "issued_at": time.time()
        }
        result = await collection.update_one(
            {"user_id": user_id},
            {
                "$set": {f"mutes.{chat_id}": mute_info, "last_active": time.time()}
            }
        )
        if result.modified_count > 0:
            await log_moderation_action(user_id, chat_id, "mute", reason, issued_by, duration=duration, until_date=mute_info["until"])
            logger.info(f"Пользователь {user_id} замучен в chat_id={chat_id} до {mute_info['until']}, причина: {reason}, выдано: {issued_by}")
            return True
        logger.warning(f"Не удалось замутить пользователя {user_id} в chat_id={chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при муте пользователя {user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def unmute_user(user_id: int, chat_id: int, issued_by: int) -> bool:
    """Снимает мут с пользователя в указанном чате."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_user_collection()
        user = await collection.find_one({"user_id": user_id})
        if not user:
            logger.error(f"Пользователь {user_id} не найден для снятия мута в chat_id={chat_id}")
            return False
        mute_info = {
            "is_muted": False,
            "until": 0.0,
            "reason": "",
            "issued_by": 0,
            "issued_at": 0.0
        }
        result = await collection.update_one(
            {"user_id": user_id},
            {
                "$set": {f"mutes.{chat_id}": mute_info, "last_active": time.time()}
            }
        )
        if result.modified_count > 0:
            await log_moderation_action(user_id, chat_id, "unmute", "Мут снят", issued_by)
            logger.info(f"Мут снят с пользователя {user_id} в chat_id={chat_id}")
            return True
        logger.warning(f"Не удалось снять мут с пользователя {user_id} в chat_id={chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при снятии мута с пользователя {user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def kick_user(user_id: int, chat_id: int, reason: str, issued_by: int) -> bool:
    """Логирует исключение пользователя из указанного чата."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        await log_moderation_action(user_id, chat_id, "kick", reason, issued_by)
        logger.info(f"Пользователь {user_id} исключен из chat_id={chat_id}, причина: {reason}, выдано: {issued_by}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при логировании исключения пользователя {user_id} в chat_id={chat_id}: {str(e)}")
        return False

async def log_moderation_action(user_id: int, chat_id: int, action: str, reason: str, issued_by: int, duration: float = None, until_date: float = None) -> bool:
    """Логирует действие модерации в коллекцию moderation_logs."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    if action not in VALID_MODERATION_ACTIONS:
        logger.error(f"Недействительное действие модерации: {action}")
        raise ValueError(f"Действие модерации должно быть одним из: {VALID_MODERATION_ACTIONS}")
    try:
        collection = await get_moderation_logs_collection()
        log_entry = {
            "user_id": user_id,
            "chat_id": chat_id,
            "action": action,
            "reason": reason,
            "issued_by": issued_by,
            "issued_at": time.time(),
            "duration": duration,
            "until_date": until_date
        }
        result = await collection.insert_one(log_entry)
        logger.info(f"Лог модерации создан для user_id={user_id}, chat_id={chat_id}, action={action}, id={result.inserted_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при логировании действия {action} для user_id={user_id}, chat_id={chat_id}: {str(e)}")
        return False

async def get_moderation_logs(chat_id: int, limit: int = 10) -> List[Dict]:
    """Получает последние логи модерации для указанного чата."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        collection = await get_moderation_logs_collection()
        cursor = collection.find({"chat_id": chat_id}).sort("issued_at", -1).limit(limit)
        logs = [log async for log in cursor]
        logger.info(f"Получено {len(logs)} логов модерации для chat_id={chat_id}")
        return logs
    except Exception as e:
        logger.error(f"Ошибка при получении логов модерации для chat_id={chat_id}: {str(e)}")
        return []

async def set_server_owner(user_id: int, chat_id: int) -> bool:
    """Назначает пользователя владельцем сервера для указанного чата."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    collection = await get_user_collection()
    user = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
    if user.user_id == OWNER_BOT_ID:
        logger.warning(f"Нельзя назначить владельца бота {user_id} владельцем сервера")
        return False
    result = await collection.update_one(
        {"user_id": user_id},
        {
            "$addToSet": {"server_owner_chat_ids": chat_id, "group_ids": chat_id},
            "$set": {"last_active": time.time()}
        }
    )
    if result.modified_count > 0 or chat_id in user.server_owner_chat_ids:
        logger.info(f"Пользователь {user_id} назначен владельцем сервера для chat_id={chat_id}")
        return True
    logger.warning(f"Не удалось назначить пользователя {user_id} владельцем сервера для chat_id={chat_id}")
    return False

async def remove_server_owner(user_id: int, chat_id: int) -> bool:
    """Удаляет роль владельца сервера для указанного чата."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    collection = await get_user_collection()
    user = await get_user(user_id, create_if_not_exists=False)
    if not user:
        logger.warning(f"Пользователь {user_id} не найден для удаления роли владельца сервера в chat_id={chat_id}")
        return False
    if user.user_id == OWNER_BOT_ID:
        logger.warning(f"Нельзя удалить роль владельца сервера у владельца бота: {user_id}")
        return False
    result = await collection.update_one(
        {"user_id": user_id},
        {
            "$pull": {"server_owner_chat_ids": chat_id},
            "$set": {"last_active": time.time(), "role_level": 0}
        }
    )
    if result.modified_count > 0:
        logger.info(f"Роль владельца сервера удалена для пользователя {user_id} в chat_id={chat_id}")
        return True
    logger.warning(f"Не удалось удалить роль владельца сервера для пользователя {user_id} в chat_id={chat_id}")
    return False

async def register_chat_member(user_id: int, username: str, display_name: str, chat_id: int, is_bot: bool = False) -> User:
    """Регистрирует участника чата в базе данных или обновляет его данные."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    try:
        user = await get_user(user_id, create_if_not_exists=False, chat_id=chat_id)
        updates = {
            "username": username,
            "display_name": display_name,
            "is_bot": is_bot,
            "group_ids": user.group_ids + [chat_id] if chat_id not in user.group_ids else user.group_ids
        }
        await update_user(user_id, updates)
        logger.info(f"Обновлен пользователь {user_id} для chat_id={chat_id}, is_bot={is_bot}")
        return await get_user(user_id, chat_id=chat_id)
    except ValueError:
        role_level = 7 if user_id == OWNER_BOT_ID else 0
        user = User(
            user_id=user_id,
            username=username,
            display_name=display_name,
            group_ids=[chat_id],
            role_level=role_level,
            is_bot=is_bot
        )
        return await create_user(user, chat_id=chat_id)

async def delete_user(user_id: int) -> bool:
    """Удаляет пользователя из базы данных."""
    try:
        collection = await get_user_collection()
        result = await collection.delete_one({"user_id": user_id})
        if result.deleted_count > 0:
            logger.info(f"Удален пользователь: {user_id}")
            return True
        logger.warning(f"Пользователь не найден для удаления: {user_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя {user_id}: {str(e)}")
        return False

async def save_chat(chat_id: int, chat_title: str = None) -> bool:
    """Сохраняет chat_id в коллекцию chats."""
    if not isinstance(chat_id, int) or chat_id >= 0:
        logger.error(f"Недействительный chat_id: {chat_id}")
        raise ValueError("chat_id должен быть отрицательным целым числом")
    collection = await get_chat_collection()
    try:
        result = await collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_title": chat_title, "last_updated": time.time()}},
            upsert=True
        )
        if result.modified_count > 0 or result.upserted_id:
            logger.info(f"Сохранен чат: chat_id={chat_id}, chat_title={chat_title}")
            await collection.database.users.update_many(
                {},
                {
                    "$set": {
                        f"activity_count.{chat_id}": 0,
                        f"warnings.{chat_id}": [],
                        f"bans.{chat_id}": {"is_banned": False, "reason": "", "issued_by": 0, "issued_at": 0.0, "until": 0.0},
                        f"mutes.{chat_id}": {"is_muted": False, "until": 0.0, "reason": "", "issued_by": 0, "issued_at": 0.0}
                    }
                }
            )
            logger.info(f"Инициализированы данные для всех пользователей в chat_id={chat_id}")
            return True
        logger.debug(f"Чат уже существует: chat_id={chat_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении чата chat_id={chat_id}: {str(e)}")
        return False

@cached(ttl=3600)
async def get_known_chats() -> List[int]:
    """Получает список известных chat_id из коллекции chats."""
    try:
        collection = await get_chat_collection()
        cursor = collection.find({})
        chats = [doc["chat_id"] async for doc in cursor]
        logger.info(f"Найдено {len(chats)} известных чатов: {chats}")
        return chats
    except Exception as e:
        logger.error(f"Ошибка при получении списка чатов: {str(e)}")
        return []


