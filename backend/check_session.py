"""
Разовый локальный скрипт для проверки, что TELEGRAM_SESSION активна.

Ничего не отправляет и не публикует — только подключается и спрашивает
Telegram "авторизован ли этот аккаунт". Запускать вручную:

    cd backend
    python check_session.py

Возьмёт TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION из переменных
окружения, если они там есть, иначе спросит в терминале (ничего не хранит и
никуда, кроме Telegram API, не передаёт).
"""

import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = os.getenv("TELEGRAM_API_ID") or input("TELEGRAM_API_ID: ").strip()
API_HASH = os.getenv("TELEGRAM_API_HASH") or input("TELEGRAM_API_HASH: ").strip()
SESSION = os.getenv("TELEGRAM_SESSION") or input("TELEGRAM_SESSION: ").strip()

async def main():
    async with TelegramClient(StringSession(SESSION), int(API_ID), API_HASH) as client:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"\n✅ Сессия активна. Аккаунт: {me.first_name} (id={me.id}, @{me.username})")
        else:
            print("\n❌ Сессия НЕ авторизована — нужно заново сгенерировать через generate_session.py")

import asyncio
asyncio.run(main())
