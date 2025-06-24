#
# kumi_pulse/bot/bot.py
#
import os
import sys
import importlib
import asyncio
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from loguru import logger
from contextlib import asynccontextmanager

# === ПОДГОТОВКА ПУТЕЙ ===
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
logger.debug(f"Project root added to sys.path: {project_root}")
logger.debug(f"Current sys.path: {sys.path}")

# === ИМПОРТ БАЗЫ ДАННЫХ ===
backend_path = os.path.join(project_root, 'backend', 'database.py')
if not os.path.exists(backend_path):
    logger.error(f"File {backend_path} does not exist")
    raise FileNotFoundError(f"File {backend_path} does not exist")
else:
    logger.debug(f"File {backend_path} found")

try:
    from backend.database import init_db
    logger.debug("Successfully imported backend.database")
except ModuleNotFoundError as e:
    logger.error(f"Failed to import backend.database: {e}")
    raise

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ===
load_dotenv(dotenv_path=os.path.join(project_root, 'config', '.env'))

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logger.add("app.log", rotation="10 MB", level="DEBUG", format="{time} {level} {message}")

# === ИНИЦИАЛИЗАЦИЯ БОТА ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in environment variables")
    raise ValueError("BOT_TOKEN not found in environment variables")

bot = Bot(token=BOT_TOKEN)

# === РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ===
def register_handlers(dp: Dispatcher) -> None:
    print("🔥 register_handlers() is called")
    handlers_dir = os.path.join(os.path.dirname(__file__), 'handlers')
    logger.debug(f"[HANDLERS] Looking in: {handlers_dir}")

    if not os.path.exists(handlers_dir):
        logger.error(f"[HANDLERS] Directory not found: {handlers_dir}")
        return

    for filename in os.listdir(handlers_dir):
        logger.debug(f"[HANDLERS] Found file: {filename}")
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            full_module = f"bot.handlers.{module_name}"
            logger.debug(f"[HANDLERS] Attempting import: {full_module}")
            try:
                module = importlib.import_module(full_module)
                if hasattr(module, 'register_handlers'):
                    module.register_handlers(dp)
                    logger.info(f"[HANDLERS] Registered: {module_name}")
                else:
                    logger.warning(f"[HANDLERS] No register_handlers() in {module_name}")
            except Exception as e:
                logger.error(f"[HANDLERS] Failed to import {module_name}: {e}")

# === ЖИЗНЕННЫЙ ЦИКЛ ===
@asynccontextmanager
async def lifespan(dispatcher: Dispatcher):
    print("🚀 LIFESPAN STARTED")
    logger.info("🌀 Starting bot initialization...")
    try:
        await init_db()
        register_handlers(dispatcher)
        logger.info("✅ Bot initialized successfully")
        yield
    except Exception as e:
        logger.error(f"💥 Initialization error: {e}")
        raise
    finally:
        logger.info("🛑 Bot shutting down...")
        await bot.session.close()

# === ИНИЦИАЛИЗАЦИЯ DISPATCHER ===
dp = Dispatcher(lifespan=lifespan)

# === ЗАПУСК ===
async def main() -> None:
    try:
        logger.info("🚦 Starting polling...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        raise
    finally:
        logger.info("🛑 Polling stopped")

if __name__ == "__main__":
    asyncio.run(main())
