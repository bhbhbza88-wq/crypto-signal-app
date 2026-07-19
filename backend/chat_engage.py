"""
Chat Engage — пишет в whitelist-чаты «как человек» только при хорошем плюсе.

  открыли сигнал  → молчим (входы не светим)
  закрыли в плюс  → карточка профита + короткая фраза во все whitelist-чаты
  в минус / мелочь → молчим
  спросили «где берёшь» → мягко сайт + канал

Стиль письма уже «очеловечен» (короткие фразы / AI) — историю чатов
постоянно не копируем.

Env:
  TELEGRAM_API_ID / TELEGRAM_API_HASH
  TELEGRAM_CHAT_WHITELIST
  TELEGRAM_CHAT_SESSION / TELEGRAM_SESSION
  CHAT_ENGAGE_MIN_PNL          — мин. сырой PnL% для поста (default 1.0)
"""

from __future__ import annotations

import asyncio
import os
import random
import re
from io import BytesIO

import database as db

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "").strip()
TELEGRAM_CHAT_SESSION = os.getenv("TELEGRAM_CHAT_SESSION", "").strip()

_DEFAULT_CHAT_WHITELIST = (
    "kriptovaluta_01,bybitrussian,BinanceRussianSpeaking,"
    "cryptoinside_chat,minter_traders_chat,CryptoFLUD,cscalp_crypto"
)
TELEGRAM_CHAT_WHITELIST = (os.getenv("TELEGRAM_CHAT_WHITELIST") or _DEFAULT_CHAT_WHITELIST).strip()

CHANNEL_URL = os.getenv("TELEGRAM_PUBLIC_CHANNEL_URL", "").strip() or "https://t.me/papayaqq"
SITE_URL = "https://nowicki.trade"
MIN_PROFIT_PCT = float(os.getenv("CHAT_ENGAGE_MIN_PNL", "1.0") or "1.0")

from display_polish import polish_pnl  # noqa: E402

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
    if not TELEGRAM_CHAT_WHITELIST:
        return False
    if not TELEGRAM_CHAT_SESSION:
        return True
    return TELEGRAM_CHAT_SESSION == TELEGRAM_SESSION


def is_configured() -> bool:
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH and _session_string() and TELEGRAM_CHAT_WHITELIST)


def needs_own_client() -> bool:
    return is_configured() and not uses_ingest_session()


def _whitelist() -> list[str]:
    return [p.strip().lstrip("@") for p in TELEGRAM_CHAT_WHITELIST.split(",") if p.strip()]


def _coin(symbol: str) -> str:
    return (symbol or "").replace("/USDT", "").replace("USDT", "").upper()


_recent_close: list[str] = []


def _pick_unique(candidates: list[str], recent: list[str], remember: int = 8) -> str:
    pool = [c for c in candidates if c not in recent] or candidates
    choice = random.choice(pool)
    recent.append(choice)
    del recent[:-remember]
    return choice


def _close_win_text(symbol: str, pnl: float) -> str:
    coin = _coin(symbol)
    show = polish_pnl(pnl, decimals=1)
    if show < 0:
        show = abs(show)
    templates = [
        f"{coin} закрыл +{show}%",
        f"вышел с {coin}, плюс ~{show}%",
        f"по {coin} забрал +{show}%",
        f"{coin} отработала +{show}%",
        f"фиксанул {coin} около +{show}%",
        f"норм, {coin} +{show}%",
        f"закрыл ту {coin}, +{show}%",
        f"{coin} в плюс вышла",
        f"забрал по {coin}",
        f"ну вот, {coin} дала +{show}%",
    ]
    return _pick_unique(templates, _recent_close)


async def _line_close(symbol: str, pnl: float) -> str:
    try:
        import chat_style
        show = polish_pnl(pnl, decimals=1)
        if show < 0:
            show = abs(show)
        ai = await chat_style.compose_natural(
            "close_win",
            coin=_coin(symbol),
            pnl_show=str(show),
        )
        if ai:
            return ai
    except Exception as e:
        print(f"[chat_engage] style close: {e}")
    return _close_win_text(symbol, pnl)


def _soft_promo_reply() -> str:
    templates = [
        f"Смотрю сканер на {SITE_URL}, ещё кидают в {CHANNEL_URL}",
        f"Обычно через nowicki — {SITE_URL}, канал {CHANNEL_URL}",
        f"Беру оттуда: {SITE_URL} и тг {CHANNEL_URL}",
        f"Есть сканер {SITE_URL}, плюс канал {CHANNEL_URL}",
        f"Если коротко — {SITE_URL} / {CHANNEL_URL}",
        f"Глянь nowicki.trade и канал {CHANNEL_URL}, оттуда идеи",
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
    """Входы в чаты не пишем — только профит при закрытии."""
    return


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


# Пул монет для практики. Цена входа/выхода теперь берётся с реальной биржи
# (data_layer.fetch_ticker) — диапазоны ниже используются только как fallback,
# если тикер недоступен (нет сети/монета делистнута).
_PRACTICE_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "TON/USDT", "AVAX/USDT", "LINK/USDT",
    "MATIC/USDT", "LTC/USDT", "TRX/USDT", "NEAR/USDT", "DOT/USDT",
]
_PRACTICE_FALLBACK_RANGE = {
    "BTC/USDT": (58000.0, 72000.0), "ETH/USDT": (2400.0, 3600.0),
    "SOL/USDT": (120.0, 200.0), "BNB/USDT": (520.0, 680.0),
    "XRP/USDT": (0.42, 0.75), "ADA/USDT": (0.32, 0.55),
    "DOGE/USDT": (0.10, 0.22), "TON/USDT": (5.5, 8.5),
    "AVAX/USDT": (22.0, 42.0), "LINK/USDT": (11.0, 19.0),
    "MATIC/USDT": (0.45, 0.85), "LTC/USDT": (65.0, 95.0),
    "TRX/USDT": (0.09, 0.16), "NEAR/USDT": (4.0, 8.0), "DOT/USDT": (5.0, 9.0),
}


def _random_practice_params() -> tuple[str, str, float]:
    """Случайные symbol/side/pnl для практики — конкретную цену входа/выхода
    берём позже с реального рынка (нужен свежий тикер, а не рандом по времени)."""
    symbol = random.choice(_PRACTICE_SYMBOLS)
    side = "LONG" if random.random() < 0.8 else "SHORT"
    pnl = round(random.uniform(1.5, 6.5), 2)  # сырой % движения, ROI = pnl × leverage
    return symbol, side, pnl


def _entry_from_real_price(exit_price: float, side: str, pnl_pct: float) -> float:
    """По актуальной цене и заданному % считаем, откуда должен был быть вход."""
    if side.upper() == "LONG":
        return exit_price / (1 + pnl_pct / 100.0)
    return exit_price / (1 - pnl_pct / 100.0)


def fire_practice_profit(
    target: str = "Kupyansk_2",
    symbol: str | None = None,
    side: str | None = None,
    entry: float | None = None,
    pnl: float | None = None,
    exit_price: float | None = None,
) -> tuple[bool, str]:
    """Практика: карточка профита + текст одному контакту/чату (по умолчанию Kupyansk_2).

    Если symbol/side/pnl не переданы — берутся случайно, чтобы карточки не были
    всегда «BTC +39%». Цена входа/выхода тянется с реальной биржи в момент
    отправки (см. _do_practice_profit) — не рандомная, а актуальная рыночная.
    """
    if not is_configured():
        return False, "chat_engage не сконфигурирован"
    if _queue is None or _main_loop is None:
        return False, "воркер ещё не готов (нужен живой telegram_ingest / chat session)"
    target = (target or "").strip().lstrip("@")
    if not target:
        return False, "не указан target"

    r_symbol, r_side, r_pnl = _random_practice_params()
    symbol = symbol or r_symbol
    side = (side or r_side).upper()
    pnl = pnl if pnl is not None else r_pnl

    _enqueue({
        "kind": "practice_profit",
        "target": target,
        "symbol": symbol,
        "side": side,
        "entry": entry,        # None → взять реальную цену и посчитать вход
        "pnl": pnl,
        "exit_price": exit_price,  # None → взять реальную текущую цену
    })
    return True, f"практика профита → @{target}: {symbol} {side} +{pnl:.2f}%"


def _render_card(symbol, side, entry, pnl, exit_price):
    from profit_card import render_profit_card
    return render_profit_card(
        symbol=symbol, side=side, entry=float(entry),
        pnl_pct=float(pnl), exit_price=exit_price,
    )


async def _send_profit(client, target, text: str, photo: bytes | None) -> None:
    entity = await client.get_entity(target)
    if photo:
        bio = BytesIO(photo)
        bio.name = "pnl.png"
        await client.send_file(entity, bio, caption=text, force_document=False)
    else:
        await client.send_message(entity, text)


async def _do_close(client, symbol: str, side: str, result: str, pnl: float,
                    entry=None, exit_price=None) -> None:
    try:
        pnl_f = float(pnl)
    except (TypeError, ValueError):
        return
    if pnl_f < MIN_PROFIT_PCT:
        db.clear_chat_engage_posts(symbol)
        return

    text = await _line_close(symbol, pnl_f)
    photo = None
    if entry is not None:
        try:
            photo = _render_card(symbol, side, entry, pnl_f, exit_price)
        except Exception as e:
            print(f"[chat_engage] profit_card: {e}")

    chats = _whitelist()
    for i, chat in enumerate(chats):
        try:
            if i:
                await asyncio.sleep(random.uniform(4, 14))
            await _send_profit(client, chat, text, photo)
            print(f"[chat_engage] profit → {chat}: {symbol} {pnl_f:+.1f}% | {text!r}")
        except Exception as e:
            print(f"[chat_engage] profit fail {chat}: {e}")
    db.clear_chat_engage_posts(symbol)


async def _resolve_practice_prices(symbol: str, side: str, pnl: float,
                                    entry: float | None, exit_price: float | None) -> tuple[float, float]:
    """Тянем реальную рыночную цену и считаем вход/выход так, чтобы движение
    точно совпадало с pnl% и было привязано к текущей цене монеты (не к рандому)."""
    if entry is not None and exit_price is not None:
        return float(entry), float(exit_price)

    real_last = None
    try:
        import data_layer
        ticker = await asyncio.to_thread(data_layer.fetch_ticker, symbol)
        if ticker and ticker.get("last"):
            real_last = float(ticker["last"])
    except Exception as e:
        print(f"[chat_engage] fetch_ticker {symbol}: {e}")

    if real_last is None:
        lo, hi = _PRACTICE_FALLBACK_RANGE.get(symbol, (1.0, 100.0))
        real_last = random.uniform(lo, hi)
        print(f"[chat_engage] тикер {symbol} недоступен — fallback-цена {real_last}")

    if exit_price is None:
        exit_price = real_last
    if entry is None:
        entry = _entry_from_real_price(exit_price, side, pnl)
    return float(entry), float(exit_price)


async def _do_practice_profit(client, target: str, symbol: str, side: str,
                              pnl: float, entry: float | None = None,
                              exit_price: float | None = None) -> None:
    entry, exit_price = await _resolve_practice_prices(symbol, side, pnl, entry, exit_price)
    text = await _line_close(symbol, float(pnl))
    photo = None
    try:
        photo = _render_card(symbol, side, entry, pnl, exit_price)
    except Exception as e:
        print(f"[chat_engage] practice card: {e}")
    try:
        await _send_profit(client, target, text, photo)
        print(f"[chat_engage] practice → {target}: {symbol} {side} вход {entry} → {exit_price} ({text!r})")
    except Exception as e:
        print(f"[chat_engage] practice fail {target}: {e}")


async def _worker_loop(client):
    while True:
        job = await _queue.get()
        try:
            kind = job.get("kind")
            if kind == "close":
                await _do_close(
                    client, job["symbol"], job["side"],
                    job.get("result", ""), job.get("pnl", 0),
                    entry=job.get("entry"),
                    exit_price=job.get("exit_price"),
                )
            elif kind == "practice_profit":
                await _do_practice_profit(
                    client,
                    job["target"],
                    job["symbol"],
                    job["side"],
                    job["pnl"],
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
        f"только профит ≥{MIN_PROFIT_PCT}%, чаты: {', '.join(_whitelist())}"
    )
    return task


def detach():
    global _queue, _main_loop, _attached
    _attached = False
    _queue = None
    _main_loop = None


async def run():
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
    print(f"[chat_engage] отдельный аккаунт, профит-посты → {', '.join(_whitelist())}")

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
