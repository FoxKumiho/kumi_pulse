# kumi_pulse/bot/handlers/chat_member_handler.py

from aiogram import Router, Bot, types
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER

router = Router()

