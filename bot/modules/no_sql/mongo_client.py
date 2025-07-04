# Путь файла: bot/modules/no_sql/mongo_client.py

import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Формируем абсолютный путь к .env файлу
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # Корень проекта (kumi_pulse/)
ENV_FILE = BASE_DIR / "config" / ".env"

# Проверяем существование .env файла
if not ENV_FILE.exists():
    raise FileNotFoundError(f"Файл {ENV_FILE} не найден. Убедитесь, что он существует в папке config/")

# Загружаем переменные из .env файла
load_dotenv(dotenv_path=ENV_FILE)

# Настройка клиента MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")

# Проверка наличия необходимой переменной
if not MONGODB_URI:
    raise ValueError("MONGODB_URI не указан в .env файле")

# Инициализация клиента MongoDB
client = AsyncIOMotorClient(MONGODB_URI)
# Имя базы данных извлекается из URI, поэтому явно указывать не нужно
db = client.get_database()  # Автоматически берет базу из URI (kumi_pulse)

async def get_database():
    """Возвращает объект базы данных для использования в других модулях."""
    return db

async def close_mongo_connection():
    """Закрывает соединение с MongoDB."""
    client.close()