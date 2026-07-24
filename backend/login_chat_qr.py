"""
QR-логин для TELEGRAM_CHAT_SESSION.

  python login_chat_qr.py

Открой Telegram → Settings → Devices → Link Desktop Device → отсканируй QR.
Если включена 2FA — положи пароль в _chat_qr_2fa.txt и скрипт подхватит.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

HERE = Path(__file__).resolve().parent
QR_PNG = HERE / "_chat_qr.png"
STATUS = HERE / "_chat_qr_status.json"
OUT = HERE / "_chat_session_out.txt"
PWD_FILE = HERE / "_chat_qr_2fa.txt"

API_ID = int(os.getenv("TELEGRAM_API_ID", "36092551"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d1767f1576ae2a5f4bd5e4c5e6882b05").strip()


def _status(data: dict) -> None:
    data = {**data, "ts": int(time.time())}
    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False), flush=True)


def _save_qr(url: str) -> None:
    img = qrcode.make(url)
    img.save(QR_PNG)
    print(f"QR saved: {QR_PNG}", flush=True)
    # ASCII для терминала
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


async def _wait_2fa(client: TelegramClient) -> None:
    _status({"state": "need_2fa", "hint": f"Сохрани пароль 2FA в {PWD_FILE.name}"})
    for _ in range(180):  # ~3 мин
        if PWD_FILE.exists():
            pwd = PWD_FILE.read_text(encoding="utf-8").strip()
            if pwd:
                await client.sign_in(password=pwd)
                try:
                    PWD_FILE.unlink()
                except OSError:
                    pass
                return
        await asyncio.sleep(1)
    raise SystemExit("2FA timeout — пароль не получен")


async def main() -> None:
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    _status({"state": "waiting_scan", "file": str(QR_PNG)})

    qr_login = await client.qr_login()
    _save_qr(qr_login.url)

    # До 5 минут: при истечении токена обновляем QR
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            await qr_login.wait(timeout=30)
            break
        except asyncio.TimeoutError:
            # токен мог протухнуть — обновим
            try:
                await qr_login.recreate()
                _save_qr(qr_login.url)
                _status({"state": "waiting_scan", "file": str(QR_PNG), "refreshed": True})
            except Exception as e:
                _status({"state": "error", "error": f"recreate: {e}"})
                await client.disconnect()
                raise SystemExit(1)
        except SessionPasswordNeededError:
            await _wait_2fa(client)
            break

    if not await client.is_user_authorized():
        _status({"state": "failed", "error": "not authorized after QR"})
        await client.disconnect()
        raise SystemExit(1)

    me = await client.get_me()
    session_string = client.session.save()
    OUT.write_text(session_string, encoding="utf-8")
    meta = {
        "state": "ok",
        "id": me.id,
        "username": me.username,
        "first_name": me.first_name,
        "phone": me.phone,
        "session_file": str(OUT),
    }
    _status(meta)
    print(
        f"\nOK: +{me.phone} @{(me.username or '-')} id={me.id}\n"
        f"Сессия сохранена в {OUT.name}\n"
        f"Дальше: положи содержимое в Railway TELEGRAM_CHAT_SESSION\n",
        flush=True,
    )
    await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _status({"state": "cancelled"})
        sys.exit(130)
