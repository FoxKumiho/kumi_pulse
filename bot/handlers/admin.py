from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
import logging

from os import getenv
from dotenv import load_dotenv
from pathlib import Path

# Загрузка .env
env_path = Path(__file__).resolve().parent.parent / "config" / ".env"
load_dotenv(dotenv_path=env_path)

router = Router()

# Загружаем ID владельца (обязательно как int)
OWNER_ID = int(getenv("OWNER_ID", 0))



ADMINS = {OWNER_ID}  # Начальный админ — владелец

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

@router.message(Command(commands=["admin"]))
async def admin_command_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("У тебя нет прав администратора.")
        return

    await message.answer(
        "Привет, админ! Доступные команды:\n"
        "/addadmin &lt;user_id&gt;\n"
        "/deladmin &lt;user_id&gt;"
    )

@router.message(Command(commands=["addadmin"]))
async def add_admin_handler(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("Только владелец бота может назначать админов.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Пример: /addadmin 123456789", parse_mode=None)
        return

    user_id = int(args[1])
    if user_id in ADMINS:
        await message.answer("Этот пользователь уже админ.")
    else:
        ADMINS.add(user_id)
        await message.answer(f"Назначен админ с ID {user_id}.")


@router.message(Command(commands=["deladmin"]))
async def del_admin_handler(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("Только владелец бота может снимать админов.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Пример: /deladmin 123456789")
        return

    user_id = int(args[1])
    if user_id == OWNER_ID:
        await message.answer("Нельзя снять владельца.")
        return

    if user_id not in ADMINS:
        await message.answer("Этот пользователь не админ.")
    else:
        ADMINS.remove(user_id)
        await message.answer(f"Снят с админов ID {user_id}.")

