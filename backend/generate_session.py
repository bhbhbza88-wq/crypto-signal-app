"""
Разовый локальный скрипт для получения TELEGRAM_SESSION (StringSession).

Запускать ТОЛЬКО на своей машине, вручную, один раз:
    cd backend
    pip install telethon
    python generate_session.py

Скрипт спросит номер телефона, код подтверждения (и пароль 2FA, если включён)
прямо в терминале — Telethon делает это сам, скрипт их не хранит и никуда не
передаёт. В конце выведет строку StringSession — её нужно скопировать в
TELEGRAM_SESSION в .env / секреты деплоя (Railway) и никому не показывать:
это полный доступ к аккаунту, как пароль.
"""

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    api_id = (os.getenv("TELEGRAM_API_ID") or input("TELEGRAM_API_ID: ")).strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or input("TELEGRAM_API_HASH: ")).strip()
    if not api_id or not api_hash:
        raise SystemExit("Нужны TELEGRAM_API_ID и TELEGRAM_API_HASH")

    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        await client.start()
        if not await client.is_user_authorized():
            raise SystemExit("Сессия не авторизована — вход не завершён")
        session_string = client.session.save()
        me = await client.get_me()
        print(f"\nАккаунт: {me.first_name} (@{me.username or '—'}, id={me.id})")
        print("\n=== TELEGRAM_SESSION (скопируйте в .env / секреты деплоя) ===")
        print(session_string)
        print("=== Никому не передавайте эту строку — это доступ к аккаунту ===")


if __name__ == "__main__":
    asyncio.run(main())
