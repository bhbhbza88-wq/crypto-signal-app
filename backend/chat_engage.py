"""
Chat Engage — user-аккаунт в whitelist-чатах «как человек».

  открыли сигнал  → молчим (входы не светим)
  закрыли в плюс  → карточка/текст профита (со stagger) в whitelist
  в минус / мелочь → молчим
  mention/reply / редкий light-react → живой small talk или crypto-чат
  спросили «где берёшь» → мягко сайт + канал (только тогда ссылки)

Env:
  TELEGRAM_API_ID / TELEGRAM_API_HASH
  TELEGRAM_CHAT_WHITELIST
  TELEGRAM_CHAT_SESSION / TELEGRAM_SESSION
  CHAT_ENGAGE_MIN_PNL
  CHAT_ENGAGE_MAX_REPLIES_PER_CHAT_HOUR (default 3)
  CHAT_ENGAGE_MAX_REPLIES_GLOBAL_HOUR (default 12)
  CHAT_ENGAGE_LIGHT_REACT_PROB (default 0.04)
  CHAT_ENGAGE_MIN_GAP_SEC (default 45)
  CHAT_ENGAGE_QUIET_HOURS (default 1-8, Europe/Warsaw)
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO

import database as db

try:
    from zoneinfo import ZoneInfo
    QUIET_TZ = ZoneInfo(os.getenv("CHAT_ENGAGE_TZ", "Europe/Warsaw") or "Europe/Warsaw")
except Exception:
    QUIET_TZ = timezone(timedelta(hours=2))  # fallback ≈ Warsaw winter

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

MAX_REPLIES_PER_CHAT_HOUR = int(os.getenv("CHAT_ENGAGE_MAX_REPLIES_PER_CHAT_HOUR", "3") or "3")
MAX_REPLIES_GLOBAL_HOUR = int(os.getenv("CHAT_ENGAGE_MAX_REPLIES_GLOBAL_HOUR", "12") or "12")
LIGHT_REACT_PROB = float(os.getenv("CHAT_ENGAGE_LIGHT_REACT_PROB", "0.04") or "0.04")
MIN_GAP_SEC = float(os.getenv("CHAT_ENGAGE_MIN_GAP_SEC", "45") or "45")
QUIET_HOURS_RAW = (os.getenv("CHAT_ENGAGE_QUIET_HOURS", "1-8") or "1-8").strip()

from display_polish import polish_pnl  # noqa: E402

_queue: asyncio.Queue | None = None
_main_loop: asyncio.AbstractEventLoop | None = None
_attached = False
_whitelist_ids: set[int] = set()
_whitelist_usernames: set[str] = set()
_last_reply_mono: float = 0.0
_recent_casual: list[str] = []

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
    """Чаты/юзеры для профит-постов. Телефоны оставляем с '+'."""
    out = []
    for p in TELEGRAM_CHAT_WHITELIST.split(","):
        p = p.strip()
        if not p:
            continue
        if p.startswith("+") or p.isdigit():
            out.append(p if p.startswith("+") else f"+{p}")
        else:
            out.append(p.lstrip("@"))
    return out


async def _resolve_entity(client, target: str):
    """Юзернейм/id — get_entity; телефон — ImportContacts (иначе Telethon не найдёт)."""
    target = (target or "").strip()
    if not target:
        raise ValueError("empty engage target")
    if target.startswith("+") or (target.isdigit() and len(target) >= 10):
        from telethon.tl.functions.contacts import ImportContactsRequest
        from telethon.tl.types import InputPhoneContact
        phone = target if target.startswith("+") else f"+{target}"
        try:
            res = await client(ImportContactsRequest([
                InputPhoneContact(client_id=random.randint(1, 10**9), phone=phone,
                                  first_name="TG", last_name=""),
            ]))
            if res.users:
                return res.users[0]
        except Exception as e:
            print(f"[chat_engage] ImportContacts {phone}: {e}")
        return await client.get_entity(phone)
    return await client.get_entity(target)


def _parse_quiet_hours() -> tuple[int, int] | None:
    raw = QUIET_HOURS_RAW
    if not raw or raw.lower() in ("off", "none", "-"):
        return None
    try:
        a, b = raw.split("-", 1)
        return int(a.strip()), int(b.strip())
    except Exception:
        return (1, 8)


def _in_quiet_hours() -> bool:
    bounds = _parse_quiet_hours()
    if not bounds:
        return False
    start, end = bounds
    hour = datetime.now(QUIET_TZ).hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _hour_ago_iso() -> str:
    return (datetime.now() - timedelta(hours=1)).isoformat()


def _chat_key_from_event(event) -> str:
    chat_id = getattr(event, "chat_id", None)
    if chat_id is not None:
        return str(chat_id)
    return "unknown"


def _rate_allows(chat_key: str) -> bool:
    global _last_reply_mono
    if time.monotonic() - _last_reply_mono < MIN_GAP_SEC:
        return False
    since = _hour_ago_iso()
    per = db.count_chat_engage_events(chat_key=chat_key, kind="reply", since_iso=since)
    if per >= MAX_REPLIES_PER_CHAT_HOUR:
        return False
    glob = db.count_chat_engage_events(chat_key=None, kind="reply", since_iso=since)
    if glob >= MAX_REPLIES_GLOBAL_HOUR:
        return False
    return True


def _mark_replied(chat_key: str) -> None:
    global _last_reply_mono
    _last_reply_mono = time.monotonic()
    db.record_chat_engage_event(chat_key, "reply")


async def _warm_whitelist(client) -> None:
    _whitelist_ids.clear()
    _whitelist_usernames.clear()
    for w in _whitelist():
        try:
            ent = await _resolve_entity(client, w)
            _whitelist_ids.add(int(ent.id))
            uname = getattr(ent, "username", None)
            if uname:
                _whitelist_usernames.add(uname.lower())
        except Exception as e:
            print(f"[chat_engage] warm whitelist {w}: {e}")
            _whitelist_usernames.add(w.lstrip("@").lower())


def _event_in_whitelist(event) -> bool:
    if event.is_private:
        return True
    chat_id = getattr(event, "chat_id", None)
    if chat_id is not None and int(chat_id) in _whitelist_ids:
        return True
    # fallback: username from chat
    chat = getattr(event, "chat", None)
    uname = getattr(chat, "username", None) if chat else None
    if uname and uname.lower() in _whitelist_usernames:
        return True
    return False


def _name_addressed(text: str, me) -> bool:
    if not text or not me:
        return False
    low = text.lower()
    uname = (me.username or "").lower()
    if uname and (f"@{uname}" in low or re.search(rf"\b{re.escape(uname)}\b", low)):
        return True
    first = (me.first_name or "").strip()
    if first and len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", text, re.I):
        return True
    return False


async def _is_reply_to_us(event, me) -> bool:
    if not event.is_reply or not event.reply_to:
        return False
    try:
        replied = await event.get_reply_message()
        return bool(replied and replied.sender_id == me.id)
    except Exception:
        return False


def _light_react_candidate(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 4 or len(t) > 140:
        return False
    if ASK_RE.search(t):
        return False
    low = t.lower()
    if any(x in low for x in ("http", "t.me/", "подпиш", "реклам", "vip", "промокод")):
        return False
    if t.count("\n") > 2:
        return False
    return True


async def _human_delay(text: str) -> float:
    delay = len(text or "") * 0.08 + random.uniform(1.5, 5.0)
    if random.random() < 0.15:
        delay += random.uniform(3.0, 10.0)
    return delay


async def _human_send(
    client,
    entity,
    text: str,
    *,
    photo: bytes | None = None,
    reply_to: int | None = None,
    read_msg_id: int | None = None,
) -> None:
    """Read + typing + delay + send; FloodWait retry."""
    from telethon.errors import FloodWaitError

    try:
        if read_msg_id is not None:
            await client.send_read_acknowledge(entity, max_id=read_msg_id)
    except Exception:
        pass

    delay = await _human_delay(text or "")
    try:
        async with client.action(entity, "typing"):
            await asyncio.sleep(delay)
    except Exception:
        await asyncio.sleep(delay)

    async def _do_send():
        if photo:
            bio = BytesIO(photo)
            bio.name = "pnl.png"
            await client.send_file(
                entity, bio, caption=text or None, force_document=False,
                reply_to=reply_to,
            )
        else:
            await client.send_message(entity, text, reply_to=reply_to)

    try:
        await _do_send()
    except FloodWaitError as e:
        wait = int(getattr(e, "seconds", 5) or 5) + random.uniform(2, 8)
        print(f"[chat_engage] FloodWait {wait:.0f}s")
        await asyncio.sleep(wait)
        await _do_send()


def _coin(symbol: str) -> str:
    return (symbol or "").replace("/USDT", "").replace("USDT", "").upper()


_recent_close: list[str] = []


def _pick_unique(candidates: list[str], recent: list[str], remember: int = 8) -> str:
    pool = [c for c in candidates if c not in recent] or candidates
    choice = random.choice(pool)
    recent.append(choice)
    del recent[:-remember]
    return choice


def _display_pct(pnl_pct: float) -> float:
    """% для текста в чате — леверажный ROE (как реально считает P&L биржа),
    а не сырое движение цены. Иначе подпись типа '+2.1%' выглядит нелепо
    рядом с карточкой, где P&L показан крупной суммой в USDT (+37.24) —
    вроде бы разные цифры, хотя по факту одна и та же сделка."""
    from profit_card import SHARE_LEVERAGE
    show = polish_pnl(pnl_pct, decimals=2)
    return round(show * SHARE_LEVERAGE, 1)


def _close_win_text(symbol: str, pnl: float) -> str:
    coin = _coin(symbol)
    show = _display_pct(pnl)
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
        show = _display_pct(pnl)
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
               entry: float | None = None, exit_price: float | None = None,
               exchange: str | None = None, opened_at: str | None = None) -> None:
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
        "exchange": exchange,     # 'bybit'/'binance' — какой шаблон карточки рисовать
        "opened_at": opened_at,   # для реального «Срок ...» на Bybit-карточке
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


def _random_duration_minutes() -> float:
    """Правдоподобный срок удержания позиции: от пары минут до ~2 суток."""
    return random.uniform(6, 60 * 46)


# Условный размер маржи для перевода % движения в доллары на Bybit-карточке
# (у нас нет реального счёта юзера — берём разумный диапазон позиции).
_ASSUMED_MARGIN_RANGE = (35.0, 260.0)


def _pnl_to_usdt(pnl_pct: float, leverage: int | None = None) -> float:
    from profit_card import SHARE_LEVERAGE
    leverage = leverage or SHARE_LEVERAGE
    show_pnl = polish_pnl(pnl_pct, decimals=2)
    margin = random.uniform(*_ASSUMED_MARGIN_RANGE)
    return round(margin * leverage * show_pnl / 100.0, 2)


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


def _render_card(symbol, side, entry, pnl, exit_price, exchange=None, duration_minutes=None):
    """Шаблон карточки — по бирже, где реально торгуется монета:
    Bybit → скрин из приложения Bybit (с реф-плашкой), иначе — Binance share.
    Так карточка совпадает с площадкой, а не выбирается вслепую."""
    exchange = (exchange or "bybit").lower().strip()
    if exchange == "bybit":
        from profit_card import render_bybit_card
        pnl_usdt = _pnl_to_usdt(float(pnl))
        return render_bybit_card(
            symbol=symbol, side=side, entry=float(entry), exit_price=float(exit_price),
            pnl_usdt=pnl_usdt, duration_minutes=duration_minutes or _random_duration_minutes(),
        )
    from profit_card import render_profit_card
    return render_profit_card(
        symbol=symbol, side=side, entry=float(entry),
        pnl_pct=float(pnl), exit_price=exit_price,
    )


async def _send_profit(client, target, text: str, photo: bytes | None) -> None:
    entity = await _resolve_entity(client, target)
    await _human_send(client, entity, text, photo=photo)


def _duration_from_opened_at(opened_at: str | None) -> float | None:
    """Реальный срок удержания сделки в минутах (для Bybit-карточки), если знаем opened_at."""
    if not opened_at:
        return None
    try:
        delta = datetime.now() - datetime.fromisoformat(opened_at)
        minutes = delta.total_seconds() / 60.0
        return minutes if minutes > 0 else None
    except (ValueError, TypeError):
        return None


async def _do_close(client, symbol: str, side: str, result: str, pnl: float,
                    entry=None, exit_price=None, exchange: str | None = None,
                    opened_at: str | None = None) -> None:
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
            duration_minutes = _duration_from_opened_at(opened_at)
            photo = _render_card(symbol, side, entry, pnl_f, exit_price,
                                  exchange=exchange, duration_minutes=duration_minutes)
        except Exception as e:
            print(f"[chat_engage] profit_card: {e}")

    # Вариативность: иногда только текст, иногда короткая подпись к картинке
    mode = random.random()
    if mode < 0.15:
        photo = None
    elif mode < 0.30 and photo:
        text = random.choice([
            text,
            f"+{_display_pct(pnl_f)}%",
            _coin(symbol),
            "ну вот",
        ])

    chats = _whitelist()
    for i, chat in enumerate(chats):
        try:
            if i:
                await asyncio.sleep(random.uniform(20, 90))
            await _send_profit(client, chat, text, photo)
            db.record_chat_engage_event(chat, "profit")
            print(f"[chat_engage] profit → {chat}: {symbol} {pnl_f:+.1f}% | {text!r}")
        except Exception as e:
            print(f"[chat_engage] profit fail {chat}: {e}")
    db.clear_chat_engage_posts(symbol)


# Диапазон приемлемого профита при реконструкции реальной сделки из истории.
_PRACTICE_PNL_MIN = 1.2
_PRACTICE_PNL_MAX = 7.5
# Не берём вход «только что» (нулевой профит) и держим срок реалистичным
# для сигнала — не старше ~5 дней.
_PRACTICE_MIN_AGE_MIN = 25
_PRACTICE_MAX_AGE_MIN = 5 * 24 * 60


def _pick_real_trade_from_history(candles: list, side: str, exit_price: float, pnl_hint: float):
    """По реальным свечам находим момент, когда цена была подходящей для входа,
    чтобы вход/выход/%/срок были настоящими и сходились между собой.

    Берём САМЫЙ НЕДАВНИЙ момент с приемлемым профитом — это естественный
    короткий срок удержания (как реальная сделка), а не «висела 2 недели».

    Возвращает (entry, pnl, duration_minutes) или None."""
    import time as _time
    now_ms = _time.time() * 1000.0
    candidates = []
    for row in candles or []:
        try:
            ts, _o, _h, _l, close, _v = row[0], row[1], row[2], row[3], row[4], row[5]
        except (IndexError, TypeError):
            continue
        age_min = (now_ms - float(ts)) / 60000.0
        if age_min < _PRACTICE_MIN_AGE_MIN or age_min > _PRACTICE_MAX_AGE_MIN:
            continue
        entry = float(close)
        if entry <= 0:
            continue
        if side == "LONG":
            pnl = (exit_price - entry) / entry * 100.0
        else:
            pnl = (entry - exit_price) / entry * 100.0
        if _PRACTICE_PNL_MIN <= pnl <= _PRACTICE_PNL_MAX:
            candidates.append((entry, pnl, age_min))
    if not candidates:
        return None
    # Взвешенный выбор: приятнее показать больший %, но короткий срок тоже в
    # приоритете (делим на возраст в днях). Итог — и достойный профит, и
    # правдоподобный недлинный срок, и разнообразие между карточками.
    def weight(c):
        _entry, pnl, age_min = c
        age_days = max(0.25, age_min / 1440.0)
        return (pnl ** 1.5) / age_days
    weights = [weight(c) for c in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


async def _resolve_practice_trade(symbol: str, side: str, pnl_hint: float,
                                  entry: float | None, exit_price: float | None
                                  ) -> tuple[float, float, str, float, float | None]:
    """Возвращает (entry, exit, exchange, pnl, duration_minutes).

    Если вход/выход явно не заданы — тянем реальную цену (exit = текущая) и
    восстанавливаем настоящую точку входа из истории: находим, когда цена
    реально была на уровне входа, и берём этот момент как время открытия."""
    exchange = "bybit"
    real_last = None
    if entry is not None and exit_price is not None:
        return float(entry), float(exit_price), exchange, float(pnl_hint), None

    try:
        import data_layer
        _listed, preferred, ticker = await asyncio.to_thread(data_layer.probe_listings, symbol)
        if preferred and ticker and ticker.get("last"):
            real_last = float(ticker["last"])
            exchange = preferred
    except Exception as e:
        print(f"[chat_engage] probe_listings {symbol}: {e}")

    if real_last is None:
        lo, hi = _PRACTICE_FALLBACK_RANGE.get(symbol, (1.0, 100.0))
        real_last = random.uniform(lo, hi)
        print(f"[chat_engage] тикер {symbol} недоступен — fallback-цена {real_last}")

    exit_val = float(exit_price) if exit_price is not None else real_last

    # Реконструкция настоящей сделки: entry + реальный срок из истории.
    duration_minutes = None
    pnl = float(pnl_hint)
    if entry is None:
        try:
            import data_layer
            candles = await asyncio.to_thread(
                data_layer.fetch_ohlcv_raw, symbol, "1h", 720, exchange)
            picked = _pick_real_trade_from_history(candles, side, exit_val, pnl_hint)
            if picked:
                entry, pnl, duration_minutes = picked[0], round(picked[1], 2), picked[2]
                print(f"[chat_engage] реконструкция {symbol}: вход {entry} был "
                      f"{duration_minutes/60:.1f}ч назад, pnl {pnl:.2f}%")
        except Exception as e:
            print(f"[chat_engage] history {symbol}: {e}")
        if entry is None:
            # Fallback: не нашли историческую точку → считаем вход от % (срок рандомный).
            entry = _entry_from_real_price(exit_val, side, pnl)

    return float(entry), float(exit_val), exchange, float(pnl), duration_minutes


async def _do_practice_profit(client, target: str, symbol: str, side: str,
                              pnl: float, entry: float | None = None,
                              exit_price: float | None = None) -> None:
    entry, exit_price, exchange, pnl, duration_minutes = await _resolve_practice_trade(
        symbol, side, pnl, entry, exit_price)
    text = await _line_close(symbol, float(pnl))
    photo = None
    try:
        photo = _render_card(symbol, side, entry, pnl, exit_price,
                             exchange=exchange, duration_minutes=duration_minutes)
    except Exception as e:
        print(f"[chat_engage] practice card: {e}")
    try:
        await _send_profit(client, target, text, photo)
        dur = f"{duration_minutes/60:.1f}ч" if duration_minutes else "рандом"
        print(f"[chat_engage] practice → {target}: {symbol} {side} ({exchange}) "
              f"вход {entry} → {exit_price}, {pnl:.2f}%, срок {dur} ({text!r})")
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
                    exchange=job.get("exchange"),
                    opened_at=job.get("opened_at"),
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


async def _compose_dialogue_reply(intent: str, incoming: str) -> str:
    import chat_style
    kind = "reply_crypto" if intent == "crypto_chat" else "reply_casual"
    try:
        ai = await chat_style.compose_natural(kind, incoming=incoming)
        if ai:
            return _pick_unique([ai], _recent_casual, remember=12)
    except Exception as e:
        print(f"[chat_engage] dialogue compose: {e}")
    return _pick_unique(
        [chat_style.fallback_reply(kind)],
        _recent_casual,
        remember=12,
    )


def _register_ask_handler(client, me):
    """Живой диалог + промо только на ask_source."""
    from telethon import events

    @client.on(events.NewMessage(incoming=True))
    async def on_msg(event):
        try:
            if event.sender_id == me.id:
                return
            if _in_quiet_hours():
                return
            if not _event_in_whitelist(event):
                return

            text = (event.raw_text or "").strip()
            if not text:
                return

            mentioned = bool(getattr(event.message, "mentioned", False))
            reply_to_us = await _is_reply_to_us(event, me)
            named = _name_addressed(text, me)
            direct = event.is_private or mentioned or reply_to_us or named

            light = False
            if not direct:
                if (
                    not event.is_private
                    and _light_react_candidate(text)
                    and random.random() < LIGHT_REACT_PROB
                ):
                    light = True
                else:
                    return

            chat_key = _chat_key_from_event(event)
            if not _rate_allows(chat_key):
                return

            import chat_style
            intent = await chat_style.classify_intent(text, ask_re=ASK_RE)
            if intent == "ignore" and not (direct and ASK_RE.search(text)):
                # прямой mention всё равно можно smalltalk'нуть
                if direct:
                    intent = "smalltalk"
                else:
                    return

            if intent == "ask_source" or (direct and ASK_RE.search(text)):
                reply = _soft_promo_reply()
            elif intent == "crypto_chat":
                reply = await _compose_dialogue_reply("crypto_chat", text)
            else:
                reply = await _compose_dialogue_reply("smalltalk", text)

            entity = await event.get_input_chat()
            await _human_send(
                client,
                entity,
                reply,
                reply_to=event.id if (reply_to_us or mentioned or event.is_private) else None,
                read_msg_id=event.id,
            )
            _mark_replied(chat_key)
            tag = "light" if light else "direct"
            print(f"[chat_engage] reply ({tag}/{intent}) → {chat_key}: {reply!r}")
        except Exception as e:
            print(f"[chat_engage] on_msg: {e}")


async def attach_to_client(client) -> asyncio.Task | None:
    global _queue, _main_loop, _attached
    if not is_configured() or not uses_ingest_session():
        return None
    if _attached:
        return None
    _main_loop = asyncio.get_running_loop()
    _queue = asyncio.Queue()
    me = await client.get_me()
    await _warm_whitelist(client)
    _register_ask_handler(client, me)
    task = asyncio.create_task(_worker_loop(client))
    _attached = True
    print(
        f"[chat_engage] shared с ingest: @{me.username or me.id}, "
        f"профит ≥{MIN_PROFIT_PCT}%, диалог+лимиты, чаты: {', '.join(_whitelist())}"
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
    print(f"[chat_engage] отдельный аккаунт, профит+диалог → {', '.join(_whitelist())}")

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
            await _warm_whitelist(client)
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
