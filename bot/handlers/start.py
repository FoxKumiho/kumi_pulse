#
# kumi_pulse/bot/handlers/start.py
#
print("✅ start.py загружен")
import os
import sys
from aiogram import Dispatcher, types
from aiogram.filters import Command
from loguru import logger

# Добавляем корень проекта в sys.path для корректного импорта
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)
logger.debug(f"Project root added to sys.path in start.py: {project_root}")

# Отладка: проверяем наличие backend/database.py
backend_path = os.path.join(project_root, 'backend', 'database.py')
if not os.path.exists(backend_path):
    logger.error(f"File {backend_path} does not exist")
    raise FileNotFoundError(f"File {backend_path} does not exist")
else:
    logger.debug(f"File {backend_path} found")

try:
    from backend.database import get_or_create_user, get_translation, get_session
    logger.debug("Successfully imported backend.database in start.py")
except ModuleNotFoundError as e:
    logger.error(f"Failed to import backend.database in start.py: {e}")
    raise

# Настройка логгера
logger.add("app.log", rotation="10 MB", level="INFO", format="{time} {level} {message}")

async def start_command(message: types.Message) -> None:
    """Обработчик команды /start."""
    try:
        logger.debug(f"Received /start command from user {message.from_user.id}")
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        language_code = message.from_user.language_code or "en"
        logger.debug(f"User details: user_id={user_id}, username={username}, language_code={language_code}")

        # Получаем или создаем пользователя в базе данных
        async with get_session() as session:
            logger.debug(f"Creating or fetching user {user_id}")
            user = await get_or_create_user(
                session,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            logger.debug(f"User {user_id} fetched or created: {user.username}")
            # Получаем локализованное приветственное сообщение
            logger.debug(f"Fetching translation for greeting in {language_code}")
            greeting = await get_translation(
                session,
                resource_key="greeting",
                language_code=language_code
            )
            logger.debug(f"Translation fetched: {greeting}")

        # Отправляем приветственное сообщение
        await message.answer(greeting)
        logger.info(f"User {user_id} executed /start command, greeted in {language_code}")

    except Exception as e:
        logger.error(f"Error handling /start command for user {user_id}: {e}")
        await message.answer("An error occurred. Please try again poppy")

def register_handlers(dp: Dispatcher) -> None:
    """Регистрация обработчиков для команды /start."""
    logger.warning("!!! REGISTER_HANDLER START.PY WORKS !!!")
    try:
        logger.debug("Registering start command handler")
        dp.message.register(start_command, Command(commands=["start"]))
        logger.info("Start command handler registered successfully")
    except Exception as e:
        logger.error(f"Failed to register start command handler: {e}")