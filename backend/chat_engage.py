"""
Chat Engage — пишет в whitelist-чаты «как человек» по реальным сделкам NOWICKI.

  открыли сигнал  → «здарова, вот монету нашёл, зашёл…»
  закрыли в плюс  → в тех же чатах «отработала, +X%»
  в минус         → молчим
  спросили «где берёшь» → мягко сайт + канал

Env:
  TELEGRAM_API_ID / TELEGRAM_API_HASH
  TELEGRAM_CHAT_WHITELIST              — username чатов через запятую (обязательно)
  TELEGRAM_CHAT_SESSION                — опционально, второй аккаунт
  TELEGRAM_SESSION                     — fallback, если CHAT_SESSION пустой

Режим shared (один аккаунт с ingest): не поднимаем второй Telethon-клиент —
ingest вызывает attach_to_client(client). Иначе AuthKeyDuplicatedError.
Отдельный аккаунт: TELEGRAM_CHAT_SESSION ≠ TELEGRAM_SESSION → run() сам.
"""

from __future__ import annotations

import asyncio
import os
import random
import re

import database as db

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "").strip()
TELEGRAM_CHAT_SESSION = os.getenv("TELEGRAM_CHAT_SESSION", "").strip()
TELEGRAM_CHAT_WHITELIST = os.getenv("TELEGRAM_CHAT_WHITELIST", "").strip()

CHANNEL_URL = "https://telegram.me/chlebchik"
SITE_URL = "https://nowicki.trade"
PNL_SHOW_MULT = 1.12

_queue: asyncio.Queue | None = None
_main_loop: asyncio.AbstractEventLoop | None = None
_attached = False

ASK_RE = re.compile(
    r"(где\s+(бер|наход|смотр|берёшь|берешь|нашел|нашёл)|"
    r"какой\s+(сайт|канал|бот)|"
    r"скинь\s+(ссыл|канал|сайт)|"
    r"откуда\s+(сигнал|монет)|"
    r"how\s+do\s+you\s+find|"
    r"what('?s|\s+is)\s+your\s+(channel|site))",
    re.IGNORECASE,
)


def _session_string() -> str:
    return TELEGRAM_CHAT_SESSION or TELEGRAM_SESSION


def uses_ingest_session() -> bool:
    """True = пишем тем же аккаунтом, что и ingest — отдельный клиент нельзя."""
    if not TELEGRAM_CHAT_WHITELIST:
        return False
    if not TELEGRAM_CHAT_SESSION:
        return True
    return TELEGRAM_CHAT_SESSION == TELEGRAM_SESSION


def is_configured() -> bool:
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH and _session_string() and TELEGRAM_CHAT_WHITELIST)


def needs_own_client() -> bool:
    """Отдельный run() только если есть свой CHAT_SESSION, отличный от ingest."""
    return is_configured() and not uses_ingest_session()


def _whitelist() -> list[str]:
    return [p.strip().lstrip("@") for p in TELEGRAM_CHAT_WHITELIST.split(",") if p.strip()]


def _coin(symbol: str) -> str:
    return (symbol or "").replace("/USDT", "").replace("USDT", "").upper()


def _fmt_entry(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 100:
        return f"{n:.2f}"
    if n >= 1:
        return f"{n:.4f}"
    return f"{n:.6f}".rstrip("0").rstrip(".")


def _open_text(symbol: str, side: str, entry) -> str:
    coin = _coin(symbol)
    side_ru = "лонг" if side == "LONG" else "шорт"
    templates = [
        f"Взял {side_ru} по {coin} от {_fmt_entry(entry)}, че думаете?",
        f"Зашёл в {side_ru} по {coin} около {_fmt_entry(entry)}. Как вам сетап?",
        f"Пробую {side_ru} {coin} от {_fmt_entry(entry)}, стоп короткий",
        f"По {coin} взял {side_ru} с {_fmt_entry(entry)}, посмотрим",
        f"Зашёл {coin} {side_ru} от {_fmt_entry(entry)}. Кто тоже смотрит?",
        f"Взял такой {side_ru} по {coin}, вход {_fmt_entry(entry)}",
    ]
    return random.choice(templates)


def _close_win_text(symbol: str, pnl: float) -> str:
    coin = _coin(symbol)
    show = round(pnl * PNL_SHOW_MULT, 1)
    templates = [
        f"По {coin} закрыл, примерно +{show}%",
        f"{coin} закрыл в плюс, около +{show}%",
        f"По {coin} зафиксировал, вышло ~+{show}%",
        f"Закрыл {coin}, +{show}% примерно. Норм зашло",
        f"По той сделке {coin} вышли около +{show}%",
    ]
    return random.choice(templates)


def _soft_promo_reply() -> str:
    templates = [
        f"Смотрю сканер на {SITE_URL}, ещё кидают в {CHANNEL_URL}",
        f"Обычно через nowicki — {SITE_URL}, канал {CHANNEL_URL}",
        f"Беру оттуда: {SITE_URL} и тг {CHANNEL_URL}",
    ]
    return random.choice(templates)


def _enqueue(job: dict) -> None:
    if _queue is None or _main_loop is None:
        print("[chat_engage] воркер ещё не готов — пост пропущен")
        return
    try:
        _main_loop.call_soon_threadsafe(_queue.put_nowait, job)
    except Exception as e:
        print(f"[chat_engage] enqueue: {e}")


def fire_open(symbol: str, side: str, entry) -> None:
    if not is_configured():
        return
    _enqueue({"kind": "open", "symbol": symbol, "side": side, "entry": entry})


def fire_close(symbol: str, side: str, result: str, pnl: float,
               entry: float | None = None, exit_price: float | None = None) -> None:
    if not is_configured():
        return
    _enqueue({
        "kind": "close",
        "symbol": symbol,
        "side": side,
        "result": result,
        "pnl": pnl,
        "entry": entry,
        "exit_price": exit_price,
    })


async def _do_open(client, symbol: str, side: str, entry) -> None:
    text = _open_text(symbol, side, entry)
    for i, chat in enumerate(_whitelist()):
        try:
            if i:
                await asyncio.sleep(random.uniform(4, 12))
            entity = await client.get_entity(chat)
            msg = await client.send_message(entity, text)
            db.save_chat_engage_post(symbol, int(entity.id), int(msg.id), str(chat))
            print(f"[chat_engage] open → {chat}: {symbol} {side}")
        except Exception as e:
            print(f"[chat_engage] не смог написать в {chat}: {e}")


async def _do_close(client, symbol: str, side: str, result: str, pnl: float,
                    entry=None, exit_price=None) -> None:
    if pnl is None or float(pnl) <= 0:
        db.clear_chat_engage_posts(symbol)
        return
    posts = db.list_chat_engage_posts(symbol)
    if not posts:
        return
    text = _close_win_text(symbol, float(pnl))
    photo = None
    if entry is not None:
        try:
            from profit_card import render_profit_card
            photo = render_profit_card(
                symbol=symbol, side=side, entry=float(entry),
                pnl_pct=float(pnl), exit_price=exit_price,
            )
        except Exception as e:
            print(f"[chat_engage] profit_card: {e}")

    for i, row in enumerate(posts):
        try:
            if i:
                await asyncio.sleep(random.uniform(3, 9))
            target = row.get("chat_ref") or row["chat_id"]
            reply_to = row.get("msg_id")
            if photo:
                from io import BytesIO
                await client.send_file(
                    target,
                    BytesIO(photo),
                    caption=text,
                    reply_to=reply_to,
                    force_document=False,
                )
            else:
                await client.send_message(target, text, reply_to=reply_to)
            print(f"[chat_engage] close+ → {target}: {symbol} {float(pnl):+.1f}%")
        except Exception as e:
            print(f"[chat_engage] close fail {row}: {e}")
    db.clear_chat_engage_posts(symbol)


async def _worker_loop(client):
    while True:
        job = await _queue.get()
        try:
            if job["kind"] == "open":
                await _do_open(client, job["symbol"], job["side"], job["entry"])
            elif job["kind"] == "close":
                await _do_close(
                    client, job["symbol"], job["side"],
                    job.get("result", ""), job.get("pnl", 0),
                    entry=job.get("entry"),
                    exit_price=job.get("exit_price"),
                )
        except Exception as e:
            print(f"[chat_engage] job error: {e}")
        finally:
            _queue.task_done()


def _register_ask_handler(client, me):
    from telethon import events

    @client.on(events.NewMessage(incoming=True))
    async def on_msg(event):
        text = event.raw_text or ""
        if not ASK_RE.search(text):
            return
        if event.sender_id == me.id:
            return
        if not event.is_private:
            mentioned = bool(getattr(event.message, "mentioned", False))
            is_reply_to_us = False
            if event.is_reply and event.reply_to:
                try:
                    replied = await event.get_reply_message()
                    is_reply_to_us = replied and replied.sender_id == me.id
                except Exception:
                    pass
            if not (mentioned or is_reply_to_us):
                return
        await asyncio.sleep(random.uniform(2, 6))
        await event.respond(_soft_promo_reply())


async def attach_to_client(client) -> asyncio.Task | None:
    """Подцепить очередь к уже запущенному ingest-клиенту (один аккаунт)."""
    global _queue, _main_loop, _attached
    if not is_configured() or not uses_ingest_session():
        return None
    if _attached:
        return None
    _main_loop = asyncio.get_running_loop()
    _queue = asyncio.Queue()
    me = await client.get_me()
    _register_ask_handler(client, me)
    task = asyncio.create_task(_worker_loop(client))
    _attached = True
    print(
        f"[chat_engage] shared с ingest: @{me.username or me.id}, "
        f"чаты: {', '.join(_whitelist())}"
    )
    return task


def detach():
    """Сброс при disconnect ingest — следующий _run_once снова attach."""
    global _queue, _main_loop, _attached
    _attached = False
    _queue = None
    _main_loop = None


async def run():
    """Отдельный аккаунт (TELEGRAM_CHAT_SESSION свой)."""
    global _queue, _main_loop
    if not needs_own_client():
        if is_configured() and uses_ingest_session():
            print("[chat_engage] режим shared — ждём attach от telegram_ingest")
        else:
            print("[chat_engage] не сконфигурирован (нужен WHITELIST) — пропуск")
        return

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    _main_loop = asyncio.get_running_loop()
    _queue = asyncio.Queue()
    print(f"[chat_engage] отдельный аккаунт, чаты: {', '.join(_whitelist())}")

    while True:
        client = None
        worker_task = None
        try:
            client = TelegramClient(
                StringSession(TELEGRAM_CHAT_SESSION),
                int(TELEGRAM_API_ID),
                TELEGRAM_API_HASH,
            )
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("TELEGRAM_CHAT_SESSION не авторизована")
            me = await client.get_me()
            print(f"[chat_engage] online as {me.first_name} (@{me.username or me.id})")
            _register_ask_handler(client, me)
            worker_task = asyncio.create_task(_worker_loop(client))
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            if client:
                await client.disconnect()
            raise
        except Exception as e:
            print(f"[chat_engage] упал: {e}, рестарт через 20с")
        finally:
            if worker_task:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        await asyncio.sleep(20)
