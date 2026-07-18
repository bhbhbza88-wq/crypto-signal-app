"""
Логин ВТОРОГО Telegram-аккаунта — для постов в крипто-чатах (chat engage).

Не путать с generate_session.py (тот — ingest / @flogin23).
Этот аккаунт только пишет в whitelist-группы; бан не убьёт импорт сигналов.

Запуск (локально, интерактивно):
    cd backend
    python generate_chat_session.py

Спросит TELEGRAM_API_ID / HASH (можно из env), телефон, код, 2FA.
В конце выведет TELEGRAM_CHAT_SESSION — вставь на Railway.
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

    print("\nВходи аккаунтом ДЛЯ ЧАТОВ (не тот, что слушает VIP-каналы).\n")
    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        await client.start()
        if not await client.is_user_authorized():
            raise SystemExit("Сессия не авторизована — вход не завершён")
        session_string = client.session.save()
        me = await client.get_me()
        print(f"\nАккаунт чатов: {me.first_name} (@{me.username or '—'}, id={me.id})")
        print("\n=== TELEGRAM_CHAT_SESSION (Railway / .env) ===")
        print(session_string)
        print("=== Никому не отдавай — полный доступ к аккаунту ===")
        print("\nДальше на Railway:")
        print('  TELEGRAM_CHAT_SESSION=<строка выше>')
        print('  TELEGRAM_CHAT_WHITELIST=username_chata1,username_chata2')
        print("Аккаунт должен быть участником этих чатов.")


if __name__ == "__main__":
    asyncio.run(main())
