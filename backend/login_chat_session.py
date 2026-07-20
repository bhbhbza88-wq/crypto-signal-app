"""
Интерактивный логин TELEGRAM_CHAT_SESSION в два шага (для агента + юзера).

  python login_chat_session.py send     — шлёт код на телефон
  python login_chat_session.py confirm <CODE> [2FA_PASSWORD]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

STATE = Path(__file__).with_name("_chat_login_state.json")
PHONE = os.getenv("CHAT_LOGIN_PHONE", "").strip()
API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()


def _save(data: dict) -> None:
    STATE.write_text(json.dumps(data), encoding="utf-8")


def _load() -> dict:
    if not STATE.exists():
        raise SystemExit("Сначала: python login_chat_session.py send")
    return json.loads(STATE.read_text(encoding="utf-8"))


async def send_code() -> None:
    if not PHONE:
        raise SystemExit("CHAT_LOGIN_PHONE не задан (env)")
    if not API_ID or not API_HASH:
        raise SystemExit("TELEGRAM_API_ID / TELEGRAM_API_HASH не заданы (env)")
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    result = await client.send_code_request(PHONE)
    session = client.session.save()
    _save({
        "phone": PHONE,
        "phone_code_hash": result.phone_code_hash,
        "session": session,
    })
    await client.disconnect()
    print(f"OK: код отправлен на {PHONE}")
    print("Пришли код из Telegram / SMS — продолжим confirm.")


async def confirm(code: str, password: str | None = None) -> None:
    st = _load()
    client = TelegramClient(StringSession(st["session"]), API_ID, API_HASH)
    await client.connect()
    try:
        await client.sign_in(st["phone"], code.strip(), phone_code_hash=st["phone_code_hash"])
    except SessionPasswordNeededError:
        if not password:
            await client.disconnect()
            raise SystemExit("Нужен 2FA пароль: python login_chat_session.py confirm <CODE> <2FA_PASSWORD>")
        await client.sign_in(password=password)
    if not await client.is_user_authorized():
        await client.disconnect()
        raise SystemExit("Не авторизован")
    session_string = client.session.save()
    me = await client.get_me()
    out = Path(__file__).with_name("_chat_session_out.txt")
    out.write_text(session_string, encoding="utf-8")
    meta = {
        "id": me.id,
        "username": me.username,
        "first_name": me.first_name,
        "phone": me.phone,
        "session_file": str(out),
    }
    print("OK_AUTH", json.dumps(meta, ensure_ascii=False))
    await client.disconnect()
    try:
        STATE.unlink()
    except OSError:
        pass


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: send | confirm <code> [2fa]")
    cmd = sys.argv[1]
    if cmd == "send":
        await send_code()
    elif cmd == "confirm":
        if len(sys.argv) < 3:
            raise SystemExit("usage: confirm <code> [2fa]")
        pwd = sys.argv[3] if len(sys.argv) > 3 else None
        await confirm(sys.argv[2], pwd)
    else:
        raise SystemExit("unknown command")


if __name__ == "__main__":
    asyncio.run(main())
