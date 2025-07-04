# Путь файла: bot/handlers/start.py

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from bot.modules.no_sql.user_db import User, get_user, set_server_owner, OWNER_BOT_ID, ROLE_NAMES
from bot.handlers.common import register_all_chat_members
from loguru import logger
import time
from typing import Optional
import aiogram

# Используем aiogram версии 3.20.0.post0
assert aiogram.__version__ == "3.20.0.post0", f"Expected aiogram version 3.20.0.post0, but found {aiogram.__version__}"

# Отладочный лог для проверки импорта ROLE_NAMES
try:
    logger.info(f"ROLE_NAMES успешно импортирован: {ROLE_NAMES}")
except NameError as e:
    logger.error(f"Ошибка импорта ROLE_NAMES: {str(e)}")
    raise

# Инициализация маршрутизатора
router = Router()

# Время запуска бота
START_TIME = time.time()

# Константы для сообщений
WELCOME_MESSAGE = (
    "🌟 **Добро пожаловать!** 🌟\n"
    "👋 Привет, {name}!\n"
    "🎭 **Твоя роль**: {role}\n"
    "⏰ **Бот работает**: {uptime}\n"
    "{args_text}\n"
    "ℹ️ Используй **/help**, чтобы узнать доступные команды.\n"
    "⚠️ Если роль неверна или не все участники зарегистрированы, попробуй **/start test_owner** или **/force_register_all**."
)
HELP_MESSAGE = (
    "📚 **Список команд** 📚\n"
    "👋 **/start** — Запустить бота и зарегистрироваться (для всех)\n"
    "ℹ️ **/help** — Показать это сообщение (для всех)\n"
    "💎 **/premium** — Проверить статус Premium (для всех, реализация ожидается)\n"
    "🛠️ **/admin** — Команды для модераторов и администраторов (для модераторов, реализация ожидается)\n"
    "⚠️ **/warn <user_id | @username | имя> [причина]** — Выдать предупреждение (Младший модератор)\n"
    "🧹 **/clear_warnings <user_id | @username | имя>** — Очистить предупреждения (Старший модератор)\n"
    "🗑️ **/clear <количество> | reply** — Удалить сообщения (Младший модератор)\n"
    "🔇 **/mute <user_id | @username | имя> <длительность_в_минутах> [причина]** — Замутить пользователя (Старший модератор)\n"
    "🔊 **/unmute <user_id | @username | имя>** — Снять мут (Старший модератор)\n"
    "🚫 **/ban <user_id | @username | имя> [длительность_в_минутах] [причина]** — Забанить пользователя (Младший админ)\n"
    "✅ **/unban <user_id | @username | имя>** — Разбанить пользователя (Старший админ)\n"
    "👢 **/kick <user_id | @username | имя> [причина]** — Исключить пользователя (Младший админ)\n"
    "📊 **/user_status <user_id | @username | имя>** — Показать статус пользователя (Младший админ)\n"
    "📜 **/mod_logs** — Показать последние действия модерации (Старший модератор)\n"
    "❓ **/help_moderation** — Список модераторских команд (Младший модератор)\n"
    "📋 **/register_all** — Зарегистрировать администраторов чата (Владелец сервера)\n"
    "📋 **/force_register_all** — Зарегистрировать всех участников чата (Владелец сервера)\n"
    "\n🎭 **Твоя роль**: {role}"
)
ERROR_MESSAGE = (
    "🚫 Произошла ошибка! Попробуй позже или обратись в поддержку."
)
PERMISSION_ERROR_MESSAGE = (
    "⚠️ Не удалось зарегистрировать всех участников чата.\n"
    "🔐 Убедись, что бот имеет права администратора с доступом к списку участников.\n"
    "📋 Попробуй команду **/force_register_all**."
)

def get_readable_time(seconds: int) -> str:
    """
    Преобразует секунды в читаемый формат времени (дни, часы, минуты, секунды).

    Args:
        seconds: Количество секунд

    Returns:
        Строка в формате, например, "1d:2h:30m:15s"
    """
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        ping_time += time_list.pop() + ", "

    time_list.reverse()
    ping_time += ":".join(time_list)

    return ping_time

@router.message(Command(commands=["start"]))
async def start_handler(message: Message) -> None:
    """
    Обработчик команды /start. Регистрирует пользователя, проверяет его роль и
    пытается зарегистрировать всех участников в групповом чате.

    Args:
        message: Объект сообщения от aiogram
    """
    user_id: int = message.from_user.id
    chat_id: int = message.chat.id
    args: Optional[str] = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None

    try:
        # Получаем или создаем пользователя
        user: User = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        uptime: str = get_readable_time(int(time.time() - START_TIME))

        # Проверяем владельца чата через Telegram API
        if message.chat.type in ["group", "supergroup"]:
            try:
                chat_admins = await message.bot.get_chat_administrators(chat_id)
                for admin in chat_admins:
                    if admin.user.id == user_id and admin.status == "creator":
                        if chat_id not in user.server_owner_chat_ids:
                            await set_server_owner(user_id, chat_id)
                            user = await get_user(user_id, create_if_not_exists=False, chat_id=chat_id)
                            logger.info(f"Пользователь {user_id} определен как владелец чата {chat_id} через API")

                # Регистрируем всех участников чата
                await register_all_chat_members(chat_id, message.bot)
                logger.info(f"Успешная регистрация участников для chat_id={chat_id}")
            except TelegramBadRequest as e:
                logger.warning(f"Не удалось зарегистрировать участников чата {chat_id}: {str(e)}")
                if user.role_level >= 6:
                    await message.answer(PERMISSION_ERROR_MESSAGE)

        # Тестовая роль владельца сервера
        if args == "test_owner" and user.role_level < 6:
            await set_server_owner(user_id, chat_id)
            user = await get_user(user_id, create_if_not_exists=False, chat_id=chat_id)
            logger.info(f"Установлена тестовая роль Владелец сервера для user_id={user_id}, chat_id={chat_id}")

        # Формируем ответ
        args_text: str = f"📦 **Аргументы**: {args}\n" if args else ""
        text: str = WELCOME_MESSAGE.format(
            name=user.display_name or message.from_user.full_name,
            role=user.get_role_for_chat(chat_id),
            uptime=uptime,
            args_text=args_text
        )
        await message.answer(text)
        logger.info(f"Команда /start обработана: user_id={user_id}, chat_id={chat_id}, роль={user.get_role_for_chat(chat_id)}")
    except Exception as e:
        logger.error(f"Ошибка в /start: user_id={user_id}, chat_id={chat_id}, ошибка={str(e)}")
        await message.answer(ERROR_MESSAGE)

@router.message(Command(commands=["help"]))
async def help_handler(message: Message) -> None:
    """
    Обработчик команды /help. Отправляет список доступных команд.

    Args:
        message: Объект сообщения от aiogram
    """
    user_id: int = message.from_user.id
    chat_id: int = message.chat.id
    try:
        user: User = await get_user(user_id, create_if_not_exists=True, chat_id=chat_id)
        logger.debug(f"Форматирование HELP_MESSAGE для user_id={user_id}, chat_id={chat_id}")
        text: str = HELP_MESSAGE.format(
            name=user.display_name or message.from_user.full_name,
            role=user.get_role_for_chat(chat_id)
        )
        await message.answer(text)
        logger.info(f"Команда /help обработана: user_id={user_id}, chat_id={chat_id}, роль={user.get_role_for_chat(chat_id)}")
    except Exception as e:
        logger.error(f"Ошибка в /help: user_id={user_id}, chat_id={chat_id}, ошибка={str(e)}")
        await message.answer(ERROR_MESSAGE)