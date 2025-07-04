from bot import *

PM_START_TEX = {
    "ru": (
        "Здравствуйте, {}.\n"
        "Надеюсь, у вас всё хорошо.\n"
        "Пожалуйста, подождите немного, *{}*."
    ),
    "en": (
        "Hello, {}.\n"
        "I hope you're doing well.\n"
        "Please wait a moment, *{}*."
    )
}

PM_START_TEXE = {
    "ru": """
*Добро пожаловать* {} 👋  
Я — {}, профессиональный помощник по управлению Telegram-группами.

Моя цель — облегчить вашу административную работу, автоматизировать задачи и обеспечить надёжность в управлении сообществом.

➻ Нажмите *Help*, чтобы ознакомиться с моими функциями и начать эффективную работу.
""",
    "en": """
*Welcome* {} 👋  
I’m {}, a professional assistant for managing Telegram groups.

My purpose is to simplify your administrative tasks, automate routines, and provide reliability in community management.

➻ Click *Help* to explore my features and start working efficiently.
"""
}

HELP_STRINGS = {
    "en": f"""
» *{BOT_NAME}* — click the button below to view a detailed description of each available command.
""",
    "ru": f"""
» *{BOT_NAME}* — нажмите на кнопку ниже, чтобы получить подробное описание доступных команд.
"""
}
