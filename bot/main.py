# Путь файла: bot/main.py

import os
import sys
import asyncio
import signal
import platform
from aiogram import Bot, Dispatcher
from aiogram import __version__ as aiogram_version
from dotenv import load_dotenv
from loguru import logger
from contextlib import asynccontextmanager
from aiogram.exceptions import TelegramAPIError

# Проверка версии Python
MIN_PYTHON_VERSION = (3, 8)
current_python_version = sys.version_info[:2]
if current_python_version < MIN_PYTHON_VERSION:
    logger.error(f"Требуется Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+, установлена версия {current_python_version[0]}.{current_python_version[1]}")
    sys.exit(1)
logger.debug(f"Python version: {platform.python_version()}")

# Настройка логирования
logger.remove()
logger.add(
    os.path.join(os.path.dirname(__file__), '..', 'app.log'),
    level="DEBUG",
    rotation="10 MB",
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

# Диагностика: вывод sys.path для проверки
logger.debug(f"Initial sys.path: {sys.path}")

# Добавляем корневую директорию проекта в sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
logger.debug(f"Updated sys.path: {sys.path}")

# Импорты
try:
    logger.debug("Importing MongoClient and handlers...")
    from bot.modules.no_sql.user_db import init_user_collection, init_moderation_logs_collection, get_known_chats
    from bot.modules.no_sql.redis_client import redis_client
    from bot.handlers import start, admin, common, moderation, antispam
    from bot.handlers.common import register_all_chat_members
    logger.debug("Imports successful")
except ImportError as e:
    logger.error(f"Import error: {e}")
    sys.exit(1)

# Проверка версии aiogram
logger.debug(f"Checking aiogram version: {aiogram_version}")
if aiogram_version != "3.20.0.post0":
    raise ImportError(f"Требуется aiogram версии 3.20.0.post0, установлена версия {aiogram_version}")
logger.debug("aiogram version check passed")

# Загрузка переменных окружения из .env
logger.debug("Loading environment variables from .env...")
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'config', '.env'))

API_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
if not API_TOKEN:
    logger.error("BOT_TOKEN не найден в переменных окружения!")
    sys.exit(1)
if not MONGO_URI:
    logger.error("MONGO_URI не найден в переменных окружения!")
    sys.exit(1)
logger.debug(f"BOT_TOKEN loaded successfully: {API_TOKEN[:10]}...")
logger.debug(f"MONGO_URI loaded: {MONGO_URI}")

# Инициализация бота и диспетчера
logger.debug("Initializing Bot and Dispatcher...")
try:
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()
    logger.debug("Bot and Dispatcher initialized successfully")
except Exception as e:
    logger.error(f"Error initializing Bot or Dispatcher: {e}")
    sys.exit(1)

# Регистрируем маршрутизаторы
try:
    logger.debug("Registering routers...")
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(moderation.router)
    dp.include_router(common.router)
    dp.include_router(antispam.router)  # Антиспам регистрируется последним
    logger.info("Routers registered successfully: start, admin, moderation, common, antispam")
except AttributeError as e:
    logger.error(f"Ошибка при регистрации маршрутизаторов: {e}")
    sys.exit(1)

@asynccontextmanager
async def lifespan():
    logger.info("Инициализация бота...")
    try:
        # Инициализация MongoDB
        logger.debug("Starting MongoClient initialization...")
        await init_user_collection()
        await init_moderation_logs_collection()
        logger.info("MongoDB collections initialized: users, moderation_logs")
        # Проверка работы бота
        logger.debug("Checking bot availability with get_me...")
        bot_info = await bot.get_me()
        logger.info(f"Bot is active: {bot_info.username}")

        # Регистрация всех участников известных чатов
        logger.debug("Starting auto-registration of chat members...")
        known_chats = await get_known_chats()
        logger.info(f"Found {len(known_chats)} known chats: {known_chats}")
        for chat_id in known_chats:
            try:
                await register_all_chat_members(chat_id, bot)
                logger.info(f"Зарегистрированы участники для chat_id={chat_id}")
            except TelegramAPIError as e:
                logger.error(f"Ошибка при регистрации участников для chat_id={chat_id}: {str(e)}")
                logger.warning(f"Пропущена регистрация для chat_id={chat_id}. Используйте /force_register_all для ручной регистрации.")
            except Exception as e:
                logger.error(f"Неизвестная ошибка при регистрации участников для chat_id={chat_id}: {str(e)}")
                logger.warning(f"Пропущена регистрация для chat_id={chat_id}. Проверьте конфигурацию.")
        logger.info("Auto-registration of chat members completed")
        yield
    except Exception as e:
        logger.error(f"Ошибка при инициализации: {e}")
        raise
    finally:
        logger.info("Завершение работы бота...")
        await bot.session.close()
        logger.debug("Bot session closed")
        logger.info("Все соединения закрыты")

async def main():
    async with lifespan():
        try:
            logger.info("Запуск поллинга бота...")
            await dp.start_polling(bot, polling_timeout=30)
            logger.info("Поллинг завершён")
        except Exception as e:
            logger.error(f"Ошибка во время поллинга: {e}")
            raise

def handle_shutdown(loop):
    """Обработка сигнала завершения"""
    logger.debug("Received shutdown signal, stopping tasks...")
    tasks = [task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    loop.stop()
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()
    logger.info("Бот корректно остановлен")

if __name__ == "__main__":
    logger.debug("Creating new event loop...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Регистрация обработчиков сигналов
    logger.debug("Registering signal handlers...")
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown, loop)

    try:
        logger.debug("Starting asyncio.run(main())")
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)
    finally:
        handle_shutdown(loop)