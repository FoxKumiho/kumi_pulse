"""
/handlers/echo.py
"""

from aiogram import Router
from aiogram.types import Message


router = Router()
"""
@router.message()
async def echo_handler(message: Message):
    # Отправляем обратно тот же текст, что пришёл
    await message.answer(message.text)
"""