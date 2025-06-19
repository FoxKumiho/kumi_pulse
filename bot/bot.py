import asyncio
import importlib
import logging
import sys
import traceback

from os import getenv
from pathlib import Path

from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from handlers.echo import router as echo_router


env_path = Path(__file__).resolve().parent.parent / "config" / ".env"

# Загрузить переменные окружения из файла .env
load_dotenv(dotenv_path=env_path)

TOKEN = getenv("TOKEN")

# Проверяем, что токен загрузился
if not TOKEN:
    raise ValueError("Не найден токен")

# Все обработчики должны быть прикреплены к маршрутизатору (или Dispatcher)
dp = Dispatcher()

@dp.message()
async def catch_any_message(message: Message):
    if message.chat.type in ("channel", "supergroup"):
        print(f"Сообщение из канала/супергруппы '{message.chat.title}' с ID: {message.chat.id}")


@dp.message(Command(commands=['get_channel_id']))
async def get_channel_id_handler(message: Message, bot: Bot):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Пожалуйста, укажи username или ID канала, например: /get_channel_id @mychannel")
        return

    channel_arg = args[1]

    try:
        # Если аргумент - число (ID)
        try:
            channel_id = int(channel_arg)
            chat = await bot.get_chat(channel_id)
        except ValueError:
            # Иначе считаем username (обязательно с @)
            if not channel_arg.startswith("@"):
                await message.answer("Username должен начинаться с @")
                return
            chat = await bot.get_chat(channel_arg)

        await message.answer(f"ID канала {channel_arg}:\n`{chat.id}`", parse_mode="Markdown")
    except Exception:
        error_text = traceback.format_exc()
        logging.error(f"Ошибка при получении ID канала для аргумента '{channel_arg}':\n{error_text}")
        await message.answer("Произошла ошибка при получении ID канала. Проверьте правильность username или доступность канала.")


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Этот обработчик получает сообщения с `/start` командой
    """
    await message.answer(f"Привет, {html.bold(message.from_user.full_name)}!")

def load_routers(dp: Dispatcher, handlers_folder: str = "handlers"):
    handlers_path = Path(__file__).parent / handlers_folder

    for file in handlers_path.glob("*.py"):
        if file.name == "__init__.py":
            continue

        module_name = f"{handlers_folder}.{file.stem}"
        module = importlib.import_module(module_name)

        router = getattr(module, "router", None)
        if router:
            dp.include_router(router)
            print(f"Router from {module_name} loaded.")


async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    load_routers(dp)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())