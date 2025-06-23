#
# backend/database.py
#
import os
from pathlib import Path
from typing import AsyncGenerator, Optional
from datetime import datetime, timedelta, timezone
import json
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.future import select
from sqlalchemy import (
    Column, BigInteger, Integer, Boolean, DateTime, JSON, ForeignKey, String, Text, Enum
)
from dotenv import load_dotenv
from loguru import logger
import contextlib

# Путь к файлу .env
env_path = Path(__file__).resolve().parent.parent / "config" / ".env"

# Загружаем переменные окружения из .env
load_dotenv(dotenv_path=env_path)

# Настройки подключения к MariaDB из переменных окружения
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "kumi_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Zaqwerdx21")
DB_NAME = os.getenv("DB_NAME", "kumi_db")
REDIS_URL = os.getenv("REDIS_URL", None)  # None, если Redis недоступен
# Токен Telegram-бота берется из переменной TOKEN в .env (см. bot/handlers.py)

# Формируем URL подключения для асинхронного SQLAlchemy
DATABASE_URL = f"mysql+asyncmy://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

# URL для синхронных операций (например, Alembic)
SYNC_DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

# Создаем базовый класс для моделей
Base = declarative_base()

# Модели для Telegram-бота
class User(Base):
    __tablename__ = 'users'
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(50))
    first_name = Column(String(100))
    last_name = Column(String(100))
    is_bot_owner = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Server(Base):
    __tablename__ = 'servers'
    server_id = Column(BigInteger, primary_key=True)
    server_name = Column(String(100))
    purpose = Column(Enum('COMMUNITY', 'BUSINESS', 'CHANNEL', 'OTHER'), default='COMMUNITY')
    language_code = Column(Enum('en', 'ru'), default='en')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class PremiumUser(Base):
    __tablename__ = 'premium_users'
    premium_id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'))
    is_premium = Column(Boolean, default=False)
    privileges = Column(JSON)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Localization(Base):
    __tablename__ = 'localizations'
    localization_id = Column(Integer, primary_key=True)
    resource_key = Column(String(100), nullable=False)
    language_code = Column(Enum('en', 'ru'), nullable=False)
    translation = Column(Text, nullable=False)
    context = Column(Enum('COMMAND', 'MENU', 'MESSAGE', 'GUIDE', 'POST'), default='MESSAGE')

class Story(Base):
    __tablename__ = 'stories'
    story_id = Column(BigInteger, primary_key=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    media_id = Column(Integer, ForeignKey('media_files.media_id'))
    content = Column(JSON)
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime)

class CommandUsage(Base):
    __tablename__ = 'command_usage'
    usage_id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    command_name = Column(String(50), nullable=False)
    used_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    limit_per_user = Column(Integer, default=10)
    limit_window = Column(Integer, default=60)

class ServerAdmin(Base):
    __tablename__ = 'server_admins'
    admin_id = Column(Integer, primary_key=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    permissions = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Создаем асинхронный движок
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Логирование SQL-запросов (включите True для отладки)
    pool_size=5,  # Размер пула соединений
    max_overflow=10,  # Максимальное количество дополнительных соединений
)

# Создаем фабрику сессий
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def init_db():
    """Инициализация базы данных (создание таблиц, если нужно)."""
    try:
        async with engine.begin() as conn:
            # Для создания таблиц (используйте с Alembic в продакшене)
            # await conn.run_sync(Base.metadata.create_all)
            logger.info("База данных успешно инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Генератор асинхронных сессий для FastAPI Dependency Injection."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Ошибка сессии базы данных: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()

@contextlib.asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Контекстный менеджер для aiogram."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Ошибка сессии базы данных: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()

# Утилиты для Telegram-бота
async def get_or_create_user(
    session: AsyncSession, user_id: int, username: str = None,
    first_name: str = None, last_name: str = None, is_bot_owner: bool = False
) -> User:
    """Получить или создать пользователя."""
    try:
        result = await session.execute(select(User).filter_by(user_id=user_id))
        user = result.scalars().first()
        if not user:
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_bot_owner=is_bot_owner
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
        if not server:
            server = Server(
                server_id=server_id,
                server_name=server_name,
                purpose=purpose,
                language_code=language_code
            )
            session.add(server)
            await session.commit()
            logger.info(f"Создан сервер: {server_id}")
        return server
    except Exception as e:
        logger.error(f"Ошибка в get_or_create_server для server_id {server_id}: {e}")
        raise

async def check_premium_status(session: AsyncSession, user_id: int, server_id: int) -> Optional[PremiumUser]:
    """Проверить Premium-статус с кэшированием в Redis, если доступен."""
    try:
        if REDIS_URL:
            try:
                async with redis.from_url(REDIS_URL) as redis_client:
                    cache_key = f"premium_{user_id}_{server_id}"
                    cached = await redis_client.get(cache_key)
                    if cached:
                        data = json.loads(cached)
                        if data.get("is_premium"):
                            logger.info(f"Кэш найден для Premium-пользователя {user_id} на сервере {server_id}")
                            return PremiumUser(**data)
            except Exception as redis_error:
                logger.warning(f"Redis недоступен: {redis_error}. Используется прямой запрос к базе.")

        result = await session.execute(
            select(PremiumUser).filter_by(user_id=user_id, server_id=server_id)
        )
        premium = result.scalars().first()
        if premium and premium.is_premium and REDIS_URL:
            try:
                async with redis.from_url(REDIS_URL) as redis_client:
                    await redis_client.set(cache_key, json.dumps({
                        "premium_id": premium.premium_id,
                        "user_id": premium.user_id,
                        "server_id": premium.server_id,
                        "is_premium": premium.is_premium,
                        "privileges": premium.privileges,
                        "updated_at": premium.updated_at.isoformat()
                    }), ex=3600)
                    logger.info(f"Пользователь {user_id} имеет Premium на сервере {server_id}")
            except Exception as redis_error:
                logger.warning(f"Не удалось сохранить в Redis: {redis_error}")
        return premium
    except Exception as e:
        logger.error(f"Ошибка в check_premium_status для user_id {user_id}, server_id {server_id}: {e}")
        raise

async def get_translation(session: AsyncSession, resource_key: str, language_code: str) -> Optional[str]:
    """Получить перевод с кэшированием в Redis, если доступен."""
    try:
        if REDIS_URL:
            try:
                async with redis.from_url(REDIS_URL) as redis_client:
                    cache_key = f"translation_{resource_key}_{language_code}"
                    cached = await redis_client.get(cache_key)
                    if cached:
                        logger.info(f"Кэш найден для перевода {resource_key} на {language_code}")
                        return cached.decode('utf-8')
            except Exception as redis_error:
                logger.warning(f"Redis недоступен: {redis_error}. Используется прямой запрос к базе.")

        result = await session.execute(
            select(Localization).filter_by(resource_key=resource_key, language_code=language_code)
        )
        localization = result.scalars().first()
        translation = localization.translation if localization else None
        if translation and REDIS_URL:
            try:
                async with redis.from_url(REDIS_URL) as redis_client:
                    await redis_client.set(cache_key, translation, ex=3600)
            except Exception as redis_error:
                logger.warning(f"Не удалось сохранить в Redis: {redis_error}")
        return translation
    except Exception as e:
        logger.error(f"Ошибка в get_translation для ключа {resource_key}, языка {language_code}: {e}")
        raise

async def create_story(
    session: AsyncSession, story_id: int, server_id: int, user_id: int,
    content: dict, expires_at: datetime, media_id: int = None
) -> Story:
    """Создать Telegram Story."""
    try:
        story = Story(
            story_id=story_id,
            server_id=server_id,
            user_id=user_id,
            media_id=media_id,
            content=content,
            expires_at=expires_at
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
    """Зарегистрировать использование команды и проверить лимит."""
    try:
        usage = CommandUsage(
            user_id=user_id,
            server_id=server_id,
            command_name=command_name
        )
        session.add(usage)

        result = await session.execute(
            select(CommandUsage).filter_by(
                user_id=user_id, server_id=server_id, command_name=command_name
            ).where(CommandUsage.used_at >= datetime.now(timezone.utc) - timedelta(seconds=60))
        )
        usages = result.scalars().all()
        limit_per_user = usages[0].limit_per_user if usages else 10
        if len(usages) >= limit_per_user:
            logger.warning(f"Превышен лимит команд для пользователя {user_id} на сервере {server_id}: {command_name}")
            return False

        await session.commit()
        logger.info(f"Зарегистрировано использование команды: {command_name} пользователем {user_id} на сервере {server_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка в register_command_usage для user_id {user_id}, команды {command_name}: {e}")
        raise

async def check_admin_status(session: AsyncSession, user_id: int, server_id: int) -> Optional[ServerAdmin]:
    """Проверить, является ли пользователь администратором сервера."""
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