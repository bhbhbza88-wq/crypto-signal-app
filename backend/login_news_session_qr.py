"""
QR-логин TELEGRAM_NEWS_SESSION (отдельный аккаунт для ретрансляции новостей).

  python login_news_session_qr.py start   — QR в _news_qr.png, ждёт скана
  python login_news_session_qr.py wait    — продолжить ожидание (если start оборвался)
  python login_news_session_qr.py 2fa <PASSWORD> — если после скана нужен 2FA

Не использовать эту сессию параллельно локально и на Railway.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

STATE = Path(__file__).with_name("_news_qr_state.json")
QR_PNG = Path(__file__).with_name("_news_qr.png")
OUT = Path(__file__).with_name("_news_session_out.txt")

API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()


def _save(data: dict) -> None:
    STATE.write_text(json.dumps(data), encoding="utf-8")


def _load() -> dict:
    if not STATE.exists():
        raise SystemExit("Сначала: python login_news_session_qr.py start")
    return json.loads(STATE.read_text(encoding="utf-8"))


def _write_qr(url: str) -> None:
    img = qrcode.make(url)
    img.save(QR_PNG)
    print(f"QR_PNG {QR_PNG}", flush=True)
    print(f"QR_URL {url}", flush=True)


async def _finish(client: TelegramClient) -> None:
    if not await client.is_user_authorized():
        raise SystemExit("Не авторизован")
    session_string = client.session.save()
    OUT.write_text(session_string, encoding="utf-8")
    me = await client.get_me()
    meta = {
        "id": me.id,
        "username": me.username,
        "first_name": me.first_name,
        "phone": me.phone,
        "session_file": str(OUT),
    }
    print("OK_AUTH", json.dumps(meta, ensure_ascii=False))
    await client.disconnect()
    try:
        STATE.unlink()
    except OSError:
        pass


async def start_and_wait(timeout_total: float = 420.0) -> None:
    if not API_ID or not API_HASH:
        raise SystemExit("TELEGRAM_API_ID / TELEGRAM_API_HASH не заданы")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    qr = await client.qr_login()
    _write_qr(qr.url)
    _save({"session": client.session.save()})
    print("Scan QR in Telegram: Settings -> Devices -> Link Desktop Device", flush=True)
    print("File: _news_qr.png — waiting…", flush=True)

    deadline = asyncio.get_event_loop().time() + timeout_total
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            await client.disconnect()
            raise SystemExit("TIMEOUT: QR не отсканирован за отведённое время — запусти start снова")
        try:
            await asyncio.wait_for(qr.wait(), timeout=min(25.0, remaining))
            break
        except asyncio.TimeoutError:
            # QR токен короткоживущий — пересоздаём
            try:
                await qr.recreate()
                _write_qr(qr.url)
                _save({"session": client.session.save()})
                print("QR refreshed — scan fresh _news_qr.png", flush=True)
            except Exception as e:
                print(f"QR recreate: {e}", flush=True)
                await client.disconnect()
                raise SystemExit(f"Не удалось обновить QR: {e}")
        except SessionPasswordNeededError:
            _save({"session": client.session.save(), "need_2fa": True})
            await client.disconnect()
            raise SystemExit("NEED_2FA: python login_news_session_qr.py 2fa <PASSWORD>")

    try:
        await _finish(client)
    except SessionPasswordNeededError:
        _save({"session": client.session.save(), "need_2fa": True})
        await client.disconnect()
        raise SystemExit("NEED_2FA: python login_news_session_qr.py 2fa <PASSWORD>")


async def confirm_2fa(password: str) -> None:
    st = _load()
    client = TelegramClient(StringSession(st["session"]), API_ID, API_HASH)
    await client.connect()
    await client.sign_in(password=password)
    await _finish(client)


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: start | 2fa <password>")
    cmd = sys.argv[1]
    if cmd == "start":
        await start_and_wait()
    elif cmd == "2fa":
        if len(sys.argv) < 3:
            raise SystemExit("usage: 2fa <password>")
        await confirm_2fa(sys.argv[2])
    else:
        raise SystemExit("unknown command")


if __name__ == "__main__":
    asyncio.run(main())
