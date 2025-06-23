
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from backend.database import (
    Base, User, Server, PremiumUser, Localization, Story, CommandUsage, ServerAdmin,
    init_db, get_or_create_user, get_or_create_server, check_premium_status,
    get_translation, create_story, register_command_usage, check_admin_status
)
from loguru import logger
import pytest_asyncio

# Настройка временной базы данных SQLite в памяти
DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(DATABASE_URL, echo=False)
TestAsyncSessionFactory = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False
)

# Настройка loguru для вывода логов
logger.add("test.log", rotation="10 MB", level="INFO")

@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Создаем event loop для асинхронных тестов."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Инициализация базы данных SQLite в памяти."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def session():
    """Фикстура для создания сессии. Использует TestAsyncSessionFactory для SQLite."""
    async with TestAsyncSessionFactory() as session:
        yield session
        await session.rollback()

@pytest.mark.asyncio
async def test_init_db():
    """Тест инициализации базы данных."""
    with patch("backend.database.engine", test_engine):
        await init_db()
    with open("test.log") as f:
        assert "База данных успешно инициализирована" in f.read()

@pytest.mark.asyncio
async def test_get_or_create_user(session: AsyncSession):
    """Тест создания и получения пользователя."""
    user = await get_or_create_user(
        session, user_id=123456789, username="testuser", first_name="Test", last_name="User"
    )
    assert user.user_id == 123456789
    assert user.username == "testuser"
    assert user.first_name == "Test"
    assert user.created_at is not None

    # Проверяем повторное получение
    same_user = await get_or_create_user(session, user_id=123456789)
    assert same_user.user_id == user.user_id
    with open("test.log") as f:
        assert "Создан пользователь: 123456789" in f.read()

@pytest.mark.asyncio
async def test_get_or_create_server(session: AsyncSession):
    """Тест создания и получения сервера."""
    server = await get_or_create_server(
        session, server_id=-100123456789, server_name="Test Server", language_code="ru"
    )
    assert server.server_id == -100123456789
    assert server.server_name == "Test Server"
    assert server.language_code == "ru"
    assert server.created_at is not None

    # Проверяем повторное получение
    same_server = await get_or_create_server(session, server_id=-100123456789)
    assert same_server.server_id == server.server_id
    with open("test.log") as f:
        assert "Создан сервер: -100123456789" in f.read()

@pytest.mark.asyncio
async def test_check_premium_status_no_redis(session: AsyncSession):
    """Тест проверки Premium-статуса без Redis."""
    user = await get_or_create_user(session, user_id=123456789)
    server = await get_or_create_server(session, server_id=-100123456789)
    premium = PremiumUser(
        user_id=user.user_id,
        server_id=server.server_id,
        is_premium=True,
        privileges={"feature": "premium_access"},
        updated_at=datetime.now(timezone.utc)
    )
    session.add(premium)
    await session.commit()

    with patch("backend.database.REDIS_URL", None):
        result = await check_premium_status(session, user_id=123456789, server_id=-100123456789)
        assert result.is_premium is True
        assert result.privileges == {"feature": "premium_access"}

@pytest.mark.asyncio
async def test_check_premium_status_with_redis(session: AsyncSession):
    """Тест проверки Premium-статуса с мокированным Redis."""
    user = await get_or_create_user(session, user_id=123456789)
    server = await get_or_create_server(session, server_id=-100123456789)
    premium = PremiumUser(
        user_id=user.user_id,
        server_id=server.server_id,
        is_premium=True,
        privileges={"feature": "premium_access"},
        updated_at=datetime.now(timezone.utc)
    )
    session.add(premium)
    await session.commit()

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set = AsyncMock()
    with patch("backend.database.redis.from_url", return_value=mock_redis):
        with patch("backend.database.REDIS_URL", "redis://localhost:6379"):
            result = await check_premium_status(session, user_id=123456789, server_id=-100123456789)
            assert result.is_premium is True
            assert mock_redis.set.called
            with open("test.log") as f:
                assert "Пользователь 123456789 имеет Premium на сервере -100123456789" in f.read()

@pytest.mark.asyncio
async def test_get_translation_no_redis(session: AsyncSession):
    """Тест получения перевода без Redis."""
    localization = Localization(
        resource_key="greeting",
        language_code="ru",
        translation="Добро пожаловать!",
        context="COMMAND"
    )
    session.add(localization)
    await session.commit()

    with patch("backend.database.REDIS_URL", None):
        translation = await get_translation(session, resource_key="greeting", language_code="ru")
        assert translation == "Добро пожаловать!"

@pytest.mark.asyncio
async def test_get_translation_with_redis(session: AsyncSession):
    """Тест получения перевода с мокированным Redis."""
    localization = Localization(
        resource_key="greeting",
        language_code="ru",
        translation="Добро пожаловать!",
        context="COMMAND"
    )
    session.add(localization)
    await session.commit()

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set = AsyncMock()
    with patch("backend.database.redis.from_url", return_value=mock_redis):
        with patch("backend.database.REDIS_URL", "redis://localhost:6379"):
            translation = await get_translation(session, resource_key="greeting", language_code="ru")
            assert translation == "Добро пожаловать!"
            assert mock_redis.set.called
            with open("test.log") as f:
                assert "Кэш найден для перевода greeting на ru" not in f.read()  # Проверяем, что кэш не использовался

@pytest.mark.asyncio
async def test_create_story(session: AsyncSession):
    """Тест создания истории."""
    user = await get_or_create_user(session, user_id=123456789)
    server = await get_or_create_server(session, server_id=-100123456789)
    story = await create_story(
        session,
        story_id=123456,
        server_id=server.server_id,
        user_id=user.user_id,
        content={"en": "Test story", "ru": "Тестовая история"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert story.story_id == 123456
    assert story.content == {"en": "Test story", "ru": "Тестовая история"}
    with open("test.log") as f:
        assert "Создана история 123456 для пользователя 123456789 на сервере -100123456789" in f.read()

@pytest.mark.asyncio
async def test_register_command_usage(session: AsyncSession):
    """Тест регистрации использования команды."""
    user = await get_or_create_user(session, user_id=123456789)
    server = await get_or_create_server(session, server_id=-100123456789)
    result = await register_command_usage(session, user_id=user.user_id, server_id=server.server_id, command_name="start")
    assert result is True
    with open("test.log") as f:
        assert "Зарегистрировано использование команды: start пользователем 123456789 на сервере -100123456789" in f.read()

@pytest.mark.asyncio
async def test_check_admin_status(session: AsyncSession):
    """Тест проверки статуса администратора."""
    user = await get_or_create_user(session, user_id=123456789)
    server = await get_or_create_server(session, server_id=-100123456789)
    admin = ServerAdmin(
        user_id=user.user_id,
        server_id=server.server_id,
        permissions={"can_ban": True},
        created_at=datetime.now(timezone.utc)
    )
    session.add(admin)
    await session.commit()

    result = await check_admin_status(session, user_id=user.user_id, server_id=server.server_id)
    assert result is not None
    assert result.permissions == {"can_ban": True}
    with open("test.log") as f:
        assert "Пользователь 123456789 является администратором на сервере -100123456789" in f.read()
