"""
Premium Aggregator Feed — слушает публичные Telegram-каналы через Telethon и
извлекает из сообщений явные сделки (символ/сторона/вход/стоп/TP1) через
OpenAI. Работает только если сконфигурирован через env — иначе no-op, чтобы
обычный запуск (dev или прод без настроенного парсера) не ломался.

White-Label: пользователь видит только внутренний технический алиас потока
("Aggregated Stream: Alpha" и т.п. из TELEGRAM_SOURCE_CHANNELS), а не реальное
имя/username Telegram-канала — это единая система дистрибуции наших сигналов,
и внутреннее устройство её источников — коммерческая тайна. Честность при
этом не нарушается: reasons прямым текстом говорит "автоматический импорт из
внешнего потока", а не выдаёт агрегированный сигнал за продукт нашего
собственного AI/аналитики. source_url НЕ сохраняется и никуда не выводится —
трафик на сторонние каналы не уводим. TP2/TP3 в сообщениях канала почти
никогда не называются тремя уровнями — достраиваем их от TP1 тем же шагом,
что entry->TP1 (наша собственная trailing-механика, не выдаём это за слова
канала — ни в reasons, ни где-либо ещё).
"""

import os
import re
import json
import base64
import asyncio

import httpx

import database as db
import data_layer
import tracker
import telegram_bot
from signal_ingest import normalize_symbol, open_signal

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")
# "username1:Display Name 1,username2:Display Name 2"
TELEGRAM_SOURCE_CHANNELS = os.getenv("TELEGRAM_SOURCE_CHANNELS", "")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
AI_MODEL = "llama-3.3-70b-versatile"

SOURCE_TYPE = "telegram_aggregate"
AGG_MAX_OPEN = 8  # с 7 источниками лимит 5 слишком рано режет поток

# Отбор лучших сетапов: чем выше вес — тем охотнее берём канал.
# Foxtrot шумный → ниже; VIP/качество → выше.
CHANNEL_WEIGHTS = {
    "Aggregated Stream: Alpha": 1.15,
    "Aggregated Stream: Beta": 1.10,
    "Aggregated Stream: Gamma": 1.15,
    "Aggregated Stream: Delta": 1.08,
    "Aggregated Stream: Echo": 1.00,
    "Aggregated Stream: Foxtrot": 0.82,
    "Aggregated Stream: Golf": 1.05,
}
MIN_QUALITY_SCORE = 58          # ниже — не открываем
MIN_RR = 1.15                   # TP1 / риск
MIN_RISK_PCT = 0.004            # стоп ближе 0.4% — шум
MAX_RISK_PCT = 0.09             # стоп шире 9% — мусор
MAX_ENTRY_SLIP_PCT = 0.025      # цена ушла >2.5% от entry — поздно
MAX_PER_CHANNEL_DAY = 4         # чтобы один канал не забил слоты

_channel_day_counts: dict[str, tuple[str, int]] = {}  # alias -> (YYYY-MM-DD, count)

EXTRACTOR_SYSTEM_PROMPT = (
    "Ты извлекаешь параметры торгового сигнала из сообщения крипто-канала. "
    "Верни ТОЛЬКО JSON без пояснений: "
    '{"is_signal": bool, "symbol": string, "side": "LONG"|"SHORT", '
    '"entry": number, "stop": number, "tp1": number, "tp2": number|null, "tp3": number|null}. '
    "is_signal=false, если в сообщении нет конкретной сделки с явной ценой входа "
    "и стоп-лоссом (реклама, комментарий, разбор без чисел, объявление без "
    "риск-менеджмента). Не придумывай entry/stop/tp1, если они не названы в "
    "тексте прямо — в этом случае is_signal=false.\n"
    "tp2/tp3 верни ТОЛЬКО если канал сам явно назвал эти уровни отдельными "
    "числами в этом же сообщении. Если названа только одна цель (TP1) — "
    "верни tp2=null, tp3=null. Никогда не вычисляй/не досчитывай tp2/tp3 сам.\n"
    "Отдельно проверь: это НОВЫЙ вход или апдейт по уже открытой позиции? "
    "is_signal=false для любого сообщения о состоянии уже существующей сделки, "
    "даже если в нём снова названы те же цифры — например: 'держим позицию', "
    "'SL в безубыток', 'TP1 взят, двигаем стоп', 'напоминаю о сделке', "
    "'сделка ещё актуальна', благодарности/итоги по закрытой сделке. "
    "is_signal=true только для сообщения, которое звучит как самостоятельный "
    "новый призыв к действию прямо сейчас (открыть позицию), а не комментарий "
    "к ранее опубликованному сетапу.\n"
    "symbol верни как тикер к USDT, например BTCUSDT."
)


def _parse_channel_config(raw: str) -> dict:
    """'username1:alias1,username2:alias2' -> {username: alias}.
    Alias — единственное, что видит пользователь (имя трейдера, reasons). Если
    алиас не задан явно в конфиге, генерируем нейтральный технический ярлык
    по номеру канала в списке — реальный username канала не должен утечь
    в БД или на фронт ни при каких обстоятельствах."""
    channels = {}
    n = 0
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        n += 1
        username, _, alias = part.partition(":")
        username = username.strip().lstrip("@")
        channels[username] = (alias.strip() or f"Сторонний агрегированный поток данных (Провайдер #{n})")
    return channels


async def _extract_signal(text: str) -> dict | None:
    if not GROQ_API_KEY or not text.strip():
        return None
    payload = {
        "model": AI_MODEL,
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": text[:2000]},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
        parsed = json.loads(data["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"[telegram_ingest] Ошибка извлечения сигнала: {e}")
        return None

    if not parsed.get("is_signal"):
        return None
    if any(parsed.get(k) is None for k in ("symbol", "side", "entry", "stop", "tp1")):
        return None
    return parsed


async def _extract_signal_from_image(image_bytes: bytes, caption: str = "") -> dict | None:
    """Некоторые каналы публикуют сигнал как скриншот/баннер (цены нарисованы
    на картинке) без подписи или с почти пустой подписью — такие посты раньше
    вообще не попадали в анализ, потому что _extract_signal читает только
    текст. Тот же промпт и та же схема ответа, просто по картинке вместо
    текста (llama-3.2-90b-vision-preview умеет читать изображения)."""
    if not GROQ_API_KEY or not image_bytes:
        return None
    b64 = base64.b64encode(image_bytes).decode()
    user_content = [
        {"type": "text", "text": caption[:500] if caption.strip() else "Извлеки параметры сигнала со скриншота."},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ]
    payload = {
        "model": "llama-3.2-90b-vision-preview",
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
        parsed = json.loads(data["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"[telegram_ingest] Ошибка извлечения сигнала с картинки: {e}")
        return None

    if not parsed.get("is_signal"):
        return None
    if any(parsed.get(k) is None for k in ("symbol", "side", "entry", "stop", "tp1")):
        return None
    return parsed


def _derive_tp_ladder(side: str, entry: float, tp1: float) -> tuple[float, float]:
    """Канал почти никогда не называет TP2/TP3 отдельно — достраиваем их от TP1
    тем же шагом, что entry->TP1. Это наша механика частичного закрытия,
    а не слова канала — никогда не подписываем это как исходящее от источника."""
    step = tp1 - entry if side == 'LONG' else entry - tp1
    sign = 1 if side == 'LONG' else -1
    return tp1 + sign * step, tp1 + sign * 2 * step


def _channel_day_count(display_name: str) -> int:
    from datetime import date
    today = date.today().isoformat()
    day, count = _channel_day_counts.get(display_name, (today, 0))
    return 0 if day != today else count


def _channel_day_ok(display_name: str) -> bool:
    """Лимит сигналов с одного потока за сутки — иначе шумный канал съест квоту."""
    return _channel_day_count(display_name) < MAX_PER_CHANNEL_DAY


def _channel_day_bump(display_name: str) -> None:
    from datetime import date
    today = date.today().isoformat()
    day, count = _channel_day_counts.get(display_name, (today, 0))
    if day != today:
        count = 0
    _channel_day_counts[display_name] = (today, count + 1)


def _score_setup(side: str, entry: float, stop: float, tp1: float,
                 last_price: float | None, display_name: str) -> tuple[float | None, str]:
    """Оценка качества сетапа. (None, reason) = отклонить; (score, detail) = ок."""
    if entry <= 0 or stop <= 0 or tp1 <= 0:
        return None, "bad_prices"

    if side == "LONG":
        if not (stop < entry < tp1):
            return None, "bad_long_geometry"
        risk = (entry - stop) / entry
        reward = (tp1 - entry) / entry
    else:
        if not (stop > entry > tp1):
            return None, "bad_short_geometry"
        risk = (stop - entry) / entry
        reward = (entry - tp1) / entry

    if risk < MIN_RISK_PCT:
        return None, f"stop_too_tight ({risk*100:.2f}%)"
    if risk > MAX_RISK_PCT:
        return None, f"stop_too_wide ({risk*100:.2f}%)"

    rr = reward / risk if risk > 0 else 0
    if rr < MIN_RR:
        return None, f"rr_low ({rr:.2f})"

    slip = 0.0
    if last_price and last_price > 0:
        slip = abs(last_price - entry) / entry
        if slip > MAX_ENTRY_SLIP_PCT:
            return None, f"entry_stale (slip {slip*100:.1f}%)"

    # База + R:R + «золотая» зона риска + близость к рынку
    score = 38.0
    score += min(32.0, rr * 12.0)                          # rr 1.5→18, 2.5→30
    risk_pct = risk * 100
    if 1.0 <= risk_pct <= 4.0:
        score += 16
    elif 0.6 <= risk_pct <= 6.0:
        score += 8
    if slip < 0.008:
        score += 12
    elif slip < 0.015:
        score += 6

    weight = CHANNEL_WEIGHTS.get(display_name, 1.0)
    score = round(score * weight, 1)

    if score < MIN_QUALITY_SCORE:
        return None, f"score_low ({score}<{MIN_QUALITY_SCORE}, rr={rr:.2f})"

    detail = f"score={score} rr={rr:.2f} risk={risk_pct:.1f}% slip={slip*100:.1f}%"
    return score, detail


def _count_open_aggregated() -> int:
    trades = db.load_trades()
    if not trades:
        return 0
    traders_by_id = {t["id"]: t for t in db.list_traders(only_active=False)}
    return sum(
        1 for trade in trades.values()
        if (trader := traders_by_id.get(trade.get("trader_id")))
        and trader.get("source_type") == SOURCE_TYPE
    )


CLOSE_KEYWORDS_RE = re.compile(
    r'\b(закры\w*|вышл\w*|зафиксировал\w*|фикс\w*|profit\s?taken|stopped\s?out|'
    r'close[ds]?|closing|exit(ed)?)\b',
    re.IGNORECASE,
)

CLOSE_SYSTEM_PROMPT = (
    "Тебе дают тикер уже открытой позиции и текст сообщения из крипто-канала. "
    "Определи: объявляет ли это сообщение о закрытии/выходе именно из ЭТОЙ позиции "
    "(канал сам вручную закрыл/вышел) — а не апдейт по стопу/цели без закрытия, "
    "не разговор про другую монету, не общий комментарий. "
    'Верни ТОЛЬКО JSON: {"is_close": bool, "reason": "profit"|"loss"|"manual"|"unknown"}.'
)


async def _extract_close_signal(text: str, symbol_base: str) -> dict | None:
    if not GROQ_API_KEY or not text.strip():
        return None
    payload = {
        "model": AI_MODEL,
        "max_tokens": 100,
        "messages": [
            {"role": "system", "content": CLOSE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Тикер открытой позиции: {symbol_base}\n\nСообщение канала:\n{text[:1500]}"},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
        parsed = json.loads(data["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"[telegram_ingest] Ошибка проверки закрытия: {e}")
        return None
    if not parsed.get("is_close"):
        return None
    return parsed


async def _try_close_from_channel(display_name: str, text: str):
    """Канал сам объявляет о закрытии позиции (ручной выход) — без этого наш
    трекер продолжал бы вести сделку по своей логике (TP/SL/таймаут), хотя
    источник сигнала её уже закрыл на своей стороне. Дёшево: сначала смотрим,
    есть ли для ЭТОГО канала вообще открытая позиция и упоминается ли её тикер
    в тексте, и только тогда идём в OpenAI за подтверждением — не на каждое
    сообщение подряд."""
    if not text.strip() or not CLOSE_KEYWORDS_RE.search(text):
        return

    trader_id = db.get_or_create_source_trader(
        display_name, source_url=None, source_type=SOURCE_TYPE,
        bio="Автоматический импорт из внешнего потока данных (Premium Aggregator Feed)",
    )
    open_trades = db.load_trades()
    candidates = [(symbol, trade) for symbol, trade in open_trades.items()
                  if trade.get('trader_id') == trader_id]
    if not candidates:
        return

    for symbol, trade in candidates:
        base = symbol.split('/')[0]
        if not re.search(rf'\b{re.escape(base)}\b', text, re.IGNORECASE):
            continue

        parsed = await _extract_close_signal(text, base)
        if not parsed:
            continue

        ticker = await asyncio.to_thread(
            data_layer.fetch_ticker, symbol, trade.get('exchange') or 'bybit')
        if not ticker or ticker.get('last') is None:
            print(f"[telegram_ingest] {display_name}: не удалось получить цену для закрытия {symbol}")
            continue

        price = ticker['last']
        pnl = tracker.pnl_pct(trade['signal'], trade['entry'], price)
        reason = parsed.get('reason', 'unknown')
        db.add_event(symbol, 'channel_closed',
                     f"{display_name} сообщил о закрытии позиции ({reason}), PnL {pnl:+.1f}%")
        db.add_to_history(symbol, trade['signal'], trade['entry'], 'channel_closed', pnl, trade.get('trader_id'))
        db.remove_trade(symbol)
        print(f"[telegram_ingest] {symbol} закрыт по сигналу канала {display_name} ({reason}, {pnl:+.1f}%)")
        try:
            await telegram_bot.notify_signal_closed(
                {"symbol": symbol, "signal": trade['signal'],
                 "entry": trade['entry'], "exit": price},
                'channel_closed', pnl)
        except Exception as e:
            print(f"[telegram_ingest] Ошибка публикации закрытия в TG-канал: {e}")
        try:
            import chat_engage
            chat_engage.fire_close(
                symbol, trade['signal'], 'channel_closed', pnl,
                entry=trade['entry'], exit_price=price,
                exchange=trade.get('exchange'), opened_at=trade.get('opened_at'),
            )
        except Exception as e:
            print(f"[telegram_ingest] chat_engage close: {e}")


async def _handle_message(display_name: str, msg):
    """`msg` — Telethon Message или NewMessage.Event (оба дают .raw_text,
    .photo, .download_media). Сначала пробуем текст/подпись; если текста нет
    или он ничего не дал, а в сообщении есть фото — читаем сигнал с картинки
    (скриншоты/баннеры с ценами без подписи иначе никогда бы не попали
    в обработку вообще)."""
    text = (msg.raw_text or "").strip() if hasattr(msg, "raw_text") else ""
    parsed = await _extract_signal(text) if text else None

    if not parsed and getattr(msg, "photo", None):
        try:
            image_bytes = await msg.download_media(file=bytes)
        except Exception as e:
            print(f"[telegram_ingest] {display_name}: не удалось скачать картинку — {e}")
            image_bytes = None
        if image_bytes:
            parsed = await _extract_signal_from_image(image_bytes, text)

    if not parsed:
        await _try_close_from_channel(display_name, text)
        return

    side = str(parsed["side"]).upper().strip()
    if side not in ('LONG', 'SHORT'):
        return

    symbol = normalize_symbol(str(parsed["symbol"]))
    listed, exchange_id, ticker = await asyncio.to_thread(data_layer.probe_listings, symbol)
    if not exchange_id or not ticker:
        print(f"[telegram_ingest] {display_name}: символ {symbol} не торгуется на Bybit/Binance, пропуск")
        return

    listed_csv = ','.join(listed)
    print(f"[telegram_ingest] {display_name}: {symbol} via {exchange_id} (listed: {listed_csv})")

    last = ticker.get("last")
    entry, stop, tp1 = float(parsed["entry"]), float(parsed["stop"]), float(parsed["tp1"])
    quality, qdetail = _score_setup(side, entry, stop, tp1, last, display_name)
    if quality is None:
        print(f"[telegram_ingest] {display_name}: {symbol} отклонён — {qdetail}")
        return

    if not _channel_day_ok(display_name):
        print(f"[telegram_ingest] {display_name}: дневной лимит ({MAX_PER_CHANNEL_DAY}), пропуск {symbol}")
        return

    if _count_open_aggregated() >= AGG_MAX_OPEN:
        print(f"[telegram_ingest] Лимит агрегатора ({AGG_MAX_OPEN}) достигнут, пропуск {symbol} от {display_name}")
        return

    tp2, tp3 = _derive_tp_ladder(side, entry, tp1)

    trader_id = db.get_or_create_source_trader(
        display_name, source_url=None, source_type=SOURCE_TYPE,
        bio="Автоматический импорт из внешнего потока данных (Premium Aggregator Feed)",
    )

    opened_symbol, err = open_signal(
        symbol, side, entry, stop, tp1, tp2, tp3,
        trader_id=trader_id, regime=SOURCE_TYPE,
        reasons=[
            f"Автоимпорт из потока: {display_name}",
            f"Quality filter: {qdetail}",
            f"Листинг: {data_layer.listings_label(listed)}",
        ],
        score=quality,
        exchange=exchange_id,
        listed_on=listed_csv,
    )
    if err:
        print(f"[telegram_ingest] {display_name}: {symbol} пропущен ({err})")
        return

    _channel_day_bump(display_name)
    db.add_event(opened_symbol, "telegram_aggregate_signal",
                 f"{display_name}: {side} {opened_symbol} @ {entry} ({qdetail}, {listed_csv})")
    print(f"[telegram_ingest] Открыт сигнал {opened_symbol} от {display_name} ({qdetail}, via {exchange_id})")

    # Публикуем в наш собственный TG-канал тем же путём, что ручные сигналы
    # админа и TradingView-вебхук (telegram_bot.notify_manual_signal) — источник
    # честно указан как display_name (внутренний алиас), а не реальный канал.
    try:
        await telegram_bot.notify_manual_signal({
            "symbol": opened_symbol, "signal": side,
            "entry": entry, "stop": stop,
            "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "exchange": exchange_id,
            "listed_on": listed_csv,
        }, display_name)
    except Exception as e:
        print(f"[telegram_ingest] Ошибка публикации в TG-канал: {e}")

    try:
        import chat_engage
        chat_engage.fire_open(opened_symbol, side, entry)
    except Exception as e:
        print(f"[telegram_ingest] chat_engage open: {e}")


def is_configured() -> bool:
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION and TELEGRAM_SOURCE_CHANNELS)


BACKFILL_INTERVAL_SEC = 180


async def _backfill_loop(client, channels: dict, last_ids: dict):
    """events.NewMessage — чисто реактивный листенер: если соединение с Telegram
    оборвётся хоть на секунды (сетевой блип, реконнект Telethon), сообщение,
    опубликованное в этот момент, не долетит вообще без следа в логах — сам код
    даже не узнает о его существовании. Реальный кейс: пост в binancekillers_vips
    в 14:13 с чистым LONG-сигналом (entry/stop/TP всё было явно) не оставил ни
    единой строки в логах — ни успеха, ни ошибки, ни пропуска по бирже, что
    возможно только если событие вообще не сработало.
    Догоняем каждые BACKFILL_INTERVAL_SEC: перечитываем историю каждого канала
    после последнего виденного message id. Безопасно дублировать с live-хендлером —
    open_signal() отбрасывает 'already_open' по символу, а не по id сообщения."""
    while True:
        await asyncio.sleep(BACKFILL_INTERVAL_SEC)
        for username, display_name in channels.items():
            try:
                min_id = last_ids.get(username, 0)
                messages = await client.get_messages(username, min_id=min_id, limit=50)
                for msg in reversed(messages):
                    if msg.id > last_ids.get(username, 0):
                        last_ids[username] = msg.id
                    try:
                        await _handle_message(display_name, msg)
                    except Exception as e:
                        print(f"[telegram_ingest] Ошибка догоняющей обработки сообщения из {display_name}: {e}")
            except Exception as e:
                print(f"[telegram_ingest] Ошибка догоняющего опроса {display_name}: {e}")


STARTUP_LOOKBACK = 40  # при старте перечитаем хвост канала — иначе посты за downtime теряются


async def _run_once():
    """Один цикл: connect → listen → disconnect. Вызывающий run() перезапускает при обрыве."""
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    channels = _parse_channel_config(TELEGRAM_SOURCE_CHANNELS)
    client = TelegramClient(StringSession(TELEGRAM_SESSION), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)

    @client.on(events.NewMessage(chats=list(channels.keys())))
    async def _on_message(event):
        chat = await event.get_chat()
        username = (getattr(chat, "username", "") or "").lstrip("@")
        display_name = channels.get(username, "Сторонний агрегированный поток данных (Провайдер)")
        try:
            await _handle_message(display_name, event)
        except Exception as e:
            print(f"[telegram_ingest] Ошибка обработки сообщения из {display_name}: {e}")

    await client.start()

    engage_task = None
    try:
        import chat_engage
        if chat_engage.is_configured() and chat_engage.uses_ingest_session():
            engage_task = await chat_engage.attach_to_client(client)
    except Exception as e:
        print(f"[telegram_ingest] chat_engage attach: {e}")

    last_ids = {}
    for username, display_name in channels.items():
        try:
            # Хвост канала: догоняем то, что пропустили пока процесс/Telethon были мёртвы.
            # Раньше ставили last_id = latest и теряли все посты за downtime навсегда.
            recent = await client.get_messages(username, limit=STARTUP_LOOKBACK)
            if not recent:
                last_ids[username] = 0
                continue
            last_ids[username] = min(m.id for m in recent) - 1
            for msg in reversed(list(recent)):
                if msg.id > last_ids.get(username, 0):
                    last_ids[username] = msg.id
                try:
                    await _handle_message(display_name, msg)
                except Exception as e:
                    print(f"[telegram_ingest] Ошибка стартового догона {display_name}: {e}")
            print(f"[telegram_ingest] Стартовый догон {display_name}: {len(recent)} сообщений")
        except Exception as e:
            print(f"[telegram_ingest] Не удалось прочитать {display_name}: {e}")
            last_ids[username] = 0

    backfill_task = asyncio.create_task(_backfill_loop(client, channels, last_ids))
    print(f"[telegram_ingest] Запущен, слушаю каналы: {', '.join(channels.values())}")
    try:
        await client.run_until_disconnected()
    finally:
        backfill_task.cancel()
        try:
            await backfill_task
        except asyncio.CancelledError:
            pass
        if engage_task:
            engage_task.cancel()
            try:
                await engage_task
            except asyncio.CancelledError:
                pass
        try:
            import chat_engage
            chat_engage.detach()
        except Exception:
            pass
        print("[telegram_ingest] Соединение с Telegram оборвалось")


async def run():
    """Держим ingest живым: после disconnect/crash ждём и поднимаем снова."""
    if not is_configured():
        print("[telegram_ingest] Не сконфигурирован (нужны TELEGRAM_API_ID/HASH/SESSION/SOURCE_CHANNELS) — пропуск запуска")
        return

    delay = 5
    while True:
        try:
            await _run_once()
            delay = 5
        except Exception as e:
            print(f"[telegram_ingest] Упал: {e}")
        print(f"[telegram_ingest] Переподключение через {delay}с…")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 120)
