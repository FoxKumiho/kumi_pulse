#
# backend/database.py
#
import os
import json
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.future import select
from datetime import datetime, timezone
from typing import Optional, Dict
from loguru import logger
from dotenv import load_dotenv
from backend.models import (
    Base, User, Server, PremiumUser, Localization, MediaFile, Story, CommandUsage, ServerAdmin
)

# Загрузка переменных окружения
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', '.env'))

# Настройка логгера
logger.add("app.log", rotation="10 MB", level="INFO")

# Конфигурация базы данных
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '3306')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'kumi_pulse')
REDIS_URL = os.getenv('REDIS_URL')

DATABASE_URL = f"mysql+asyncmy://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session

async def init_db():
    """Инициализация базы данных."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("База данных успешно инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise

async def get_or_create_user(
    session: AsyncSession, user_id: int, username: str = None,
    first_name: str = None, last_name: str = None, is_bot_owner: bool = False
) -> User:
    """Получить или создать пользователя."""
    try:
        result = await session.execute(select(User).filter_by(user_id=user_id))
        user = result.scalars().first()
        if user:
            return user
        user = User(
            user_id=user_id, username=username, first_name=first_name,
            last_name=last_name, is_bot_owner=is_bot_owner
        )
        session.add(user)
        await session.commit()
        logger.info(f"Создан пользователь: {user_id}")
        return user
    except Exception as e:
        logger.error(f"Ошибка в get_or_create_user для user_id {user_id}: {e}")
        raise

async def get_or_create_server(
    session: AsyncSession, server_id: int, server_name: str = None,
    purpose: str = 'COMMUNITY', language_code: str = 'en'
) -> Server:
    """Получить или создать сервер (группу/канал)."""
    try:
        result = await session.execute(select(Server).filter_by(server_id=server_id))
        server = result.scalars().first()
        if server:
            return server
        server = Server(
            server_id=server_id, server_name=server_name,
            purpose=purpose, language_code=language_code
        )
        session.add(server)
        await session.commit()
        logger.info(f"Создан сервер: {server_id}")
        return server
    except Exception as e:
        logger.error(f"Ошибка в get_or_create_server для server_id {server_id}: {e}")
        raise

async def check_premium_status(
    session: AsyncSession, user_id: int, server_id: int
) -> PremiumUser:
    """Проверить статус Premium-пользователя."""
    try:
        if REDIS_URL:
            r = redis.from_url(REDIS_URL)
            cache_key = f"premium:{user_id}:{server_id}"
            cached = await r.get(cache_key)
            if cached:
                logger.info(f"Кэш найден для premium статуса: {user_id}:{server_id}")
                return PremiumUser(**json.loads(cached))
        result = await session.execute(
            select(PremiumUser).filter_by(user_id=user_id, server_id=server_id)
        )
        premium = result.scalars().first()
        if not premium:
            premium = PremiumUser(user_id=user_id, server_id=server_id, is_premium=False)
        if REDIS_URL:
            premium_data = {
                "user_id": premium.user_id,
                "server_id": premium.server_id,
                "is_premium": premium.is_premium,
                "privileges": premium.privileges,
                "updated_at": premium.updated_at.isoformat() if premium.updated_at else None
            }
            await r.set(cache_key, json.dumps(premium_data), ex=3600)
            await r.close()
        logger.info(f"Пользователь {user_id} имеет Premium на сервере {server_id}: {premium.is_premium}")
        return premium
    except Exception as e:
        logger.error(f"Ошибка в check_premium_status для user_id {user_id}, server_id {server_id}: {e}")
        raise

async def get_translation(
    session: AsyncSession, resource_key: str, language_code: str
) -> str:
    """Получить перевод для указанного ключа и языка."""
    try:
        if REDIS_URL:
            r = redis.from_url(REDIS_URL)
            cache_key = f"translation:{resource_key}:{language_code}"
            cached = await r.get(cache_key)
            if cached:
                logger.info(f"Кэш найден для перевода {resource_key} на {language_code}")
                return cached.decode()
        result = await session.execute(
            select(Localization).filter_by(resource_key=resource_key, language_code=language_code)
        )
        localization = result.scalars().first()
        translation = localization.translation if localization else resource_key
        if REDIS_URL:
            await r.set(cache_key, translation, ex=3600)
            await r.close()
        return translation
    except Exception as e:
        logger.error(f"Ошибка в get_translation для {resource_key}, {language_code}: {e}")
        raise

async def create_story(
    session: AsyncSession, story_id: int, server_id: int, user_id: int,
    content: Dict[str, str], expires_at: datetime, media_id: Optional[int] = None
) -> Story:
    """Создать новую историю."""
    try:
        story = Story(
            story_id=story_id, server_id=server_id, user_id=user_id,
            content=content, expires_at=expires_at, media_id=media_id
        )
        session.add(story)
        await session.commit()
        logger.info(f"Создана история {story_id} для пользователя {user_id} на сервере {server_id}")
        return story
    except Exception as e:
        logger.error(f"Ошибка в create_story для story_id {story_id}: {e}")
        raise

async def register_command_usage(
    session: AsyncSession, user_id: int, server_id: int, command_name: str
) -> bool:
    """Зарегистрировать использование команды."""
    try:
        usage = CommandUsage(
            user_id=user_id,
            server_id=server_id,
            command_name=command_name,
            used_at=datetime.now(timezone.utc)
        )
        session.add(usage)
        await session.commit()
        logger.info(f"Зарегистрировано использование команды: {command_name} пользователем {user_id} на сервере {server_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка в register_command_usage для {command_name}, user_id {user_id}, server_id {server_id}: {e}")
        raise

async def check_admin_status(
    session: AsyncSession, user_id: int, server_id: int
) -> Optional[ServerAdmin]:
    """Проверить статус администратора."""
    try:
        result = await session.execute(
            select(ServerAdmin).filter_by(user_id=user_id, server_id=server_id)
        )
        admin = result.scalars().first()
        if admin:
            logger.info(f"Пользователь {user_id} является администратором на сервере {server_id}")
        return admin
    except Exception as e:
        logger.error(f"Ошибка в check_admin_status для user_id {user_id}, server_id {server_id}: {e}")
        raise