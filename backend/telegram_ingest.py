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
import asyncio
from datetime import datetime, timedelta

import ai_client
import database as db
import data_layer
import tracker
import telegram_bot
from signal_ingest import normalize_symbol, open_signal
from channel_parsers import parse_signal_text

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")
# "username1:Display Name 1,username2:Display Name 2"
TELEGRAM_SOURCE_CHANNELS = os.getenv("TELEGRAM_SOURCE_CHANNELS", "")

GROQ_API_KEY = ai_client.api_key()  # legacy alias
AI_MODEL = ai_client.MODEL_INGEST
AI_VISION_MODEL = ai_client.MODEL_VISION

SOURCE_TYPE = "telegram_aggregate"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or str(default))
    except (TypeError, ValueError):
        return default


def _env_slip_pct(name: str, default_pct: float = 2.5) -> float:
    """Env в процентах (2.5 = 2.5%) → доля (0.025) для сравнения с ценой."""
    raw = os.getenv(name, str(default_pct))
    try:
        pct = float(raw or default_pct)
    except (TypeError, ValueError):
        pct = default_pct
    # Если уже задали долю (< 0.5), не делим ещё раз
    if pct < 0.5:
        return pct
    return pct / 100.0


AGG_MAX_OPEN = _env_int("INGEST_AGG_MAX_OPEN", 8)  # с 7 источниками лимит 5 слишком рано режет поток

# Health: алерт, если канал молчит дольше N минут (при живом ingest)
INGEST_SILENCE_MINUTES = int(os.getenv("INGEST_SILENCE_MINUTES", "120") or "120")
INGEST_HEALTH_CHECK_SEC = int(os.getenv("INGEST_HEALTH_CHECK_SEC", "300") or "300")
_last_silence_alert_at: dict[str, float] = {}

# Предфильтр: не звать Haiku на мемы/флуд (см. channel_backtest.looks_like_signal)
_SIGNAL_KEYWORDS_RE = re.compile(
    r'\b(LONG|SHORT|BUY|SELL|ВХОД|ENTRY|ЛОНГ|ШОРТ|TP\d?|SL|STOP|СТОП|TARGET|ЦЕЛЬ|TAKE.?PROFIT|STOP.?LOSS)\b',
    re.IGNORECASE,
)
_TICKER_RE = re.compile(r'\$?\b[A-Z]{2,10}\s?/?\s?USDT\b|#[A-Z]{2,10}\b')
_PRICE_RE = re.compile(r'\d{1,3}[.,]\d{1,8}|\d{3,}')


def looks_like_signal(text: str) -> bool:
    """Локально: похоже на сигнал? False → без API-вызова."""
    if not text or not text.strip():
        return False
    return bool(
        _SIGNAL_KEYWORDS_RE.search(text)
        or _TICKER_RE.search(text)
        or _PRICE_RE.search(text)
    )

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
MIN_QUALITY_SCORE = _env_int("INGEST_MIN_QUALITY_SCORE", 58)  # ниже — не открываем
MIN_RR = 1.15                   # TP1 / риск
MIN_RISK_PCT = 0.004            # стоп ближе 0.4% — шум
MAX_RISK_PCT = 0.09             # стоп шире 9% — мусор
MAX_ENTRY_SLIP_PCT = _env_slip_pct("INGEST_MAX_ENTRY_SLIP_PCT", 2.5)  # цена ушла >N% от entry — поздно
MAX_PER_CHANNEL_DAY = _env_int("INGEST_MAX_PER_CHANNEL_DAY", 4)  # чтобы один канал не забил слоты

EXTRACTOR_SYSTEM_PROMPT = (
    "Ты извлекаешь параметры НОВОГО торгового сигнала из сообщения крипто-канала. "
    "Верни ТОЛЬКО JSON без пояснений: "
    '{"is_signal": bool, "symbol": string, "side": "LONG"|"SHORT", '
    '"entry": number, "stop": number, "tp1": number, "tp2": number|null, "tp3": number|null}.\n'
    "\n"
    "Сторона (side): LONG/SHORT, также BUY/SELL, лонг/шорт, покупка/продажа, "
    "лонгнем/шортнем, набор/разгрузка в явном торговом контексте. "
    "Если сторона неоднозначна — is_signal=false.\n"
    "\n"
    "Символ: тикер к USDT, например BTCUSDT, ETHUSDT. Убери # $ / пробелы; "
    "BTC, BTC/USDT, $BTC → BTCUSDT. Не путай тикер с числом цены.\n"
    "\n"
    "Entry / stop / tp1 — только из этого сообщения, не выдумывай:\n"
    "- Явные цены: Entry/Вход/ENTRY, SL/Stop/Стоп, TP/Target/Цель/Take Profit.\n"
    "- Зона входа («вход 1.20–1.25», «entry 0.04-0.042»): возьми СЕРЕДИНУ диапазона.\n"
    "- Стоп в процентах («SL -2%», «стоп 1.5%»): посчитай от entry "
    "(LONG: entry*(1-pct/100), SHORT: entry*(1+pct/100)).\n"
    "- Несколько TP: tp1 = первая цель; tp2/tp3 только если канал ЯВНО назвал "
    "отдельные числа. Одну цель → tp2=null, tp3=null. Не досчитывай лестницу сам.\n"
    "- Если нет явного entry ИЛИ явного stop (числом или %) — is_signal=false. "
    "Не подставляй «текущую цену» и не угадывай стоп.\n"
    "\n"
    "is_signal=false для: рекламы, мемов, разборов без цифр, идей «смотрим», "
    "апдейтов уже открытой сделки («держим», «SL в б/у», «TP1 взят», "
    "«двигаем стоп», «сделка ещё актуальна», «напоминаю»), итогов/благодарностей "
    "по закрытой сделке, закрытий без нового входа.\n"
    "is_signal=true только если это самостоятельный новый призыв открыть позицию сейчас "
    "с конкретным символом, стороной, входом и стопом.\n"
    "\n"
    "Числа: точка как десятичный разделитель; «1,234» в EU-формате цены — 1.234 "
    "если это цена альткоина, не тысячи."
)

CLOSE_SYSTEM_PROMPT = (
    "Тебе дают тикер уже открытой позиции и текст сообщения из крипто-канала. "
    "Определи: объявляет ли сообщение о ЗАКРЫТИИ/ВЫХОДЕ именно из ЭТОЙ позиции "
    "(канал сам закрыл, зафиксировал, вышел, stopped out, close/exit по этой монете).\n"
    "is_close=false если: только апдейт стопа/цели без выхода, разговор про другую монету, "
    "общий комментарий, новый вход, «держим», «ждём TP», частичный фиксат без полного закрытия "
    "если явно сказано что позиция ещё открыта.\n"
    "reason: profit — закрыли в плюс / take profit; loss — стоп / минус; "
    "manual — закрыли вручную без явного PnL; unknown — закрытие без ясной причины.\n"
    'Верни ТОЛЬКО JSON: {"is_close": bool, "reason": "profit"|"loss"|"manual"|"unknown"}.'
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
    if not text.strip():
        return None
    if not looks_like_signal(text):
        return None

    # 1) Regex-парсеры — дёшево и стабильно для известных форматов
    regex_hit = parse_signal_text(text)
    if regex_hit:
        print(f"[telegram_ingest] regex parse: {regex_hit.get('symbol')} {regex_hit.get('side')}")
        return regex_hit

    # 2) AI fallback (MODEL_INGEST)
    if not ai_client.fast_configured():
        return None
    try:
        parsed = await ai_client.ingest_json_completion(
            system=EXTRACTOR_SYSTEM_PROMPT,
            user_text=text[:3000],
            max_tokens=260,
        )
    except Exception as e:
        print(f"[telegram_ingest] Ошибка извлечения сигнала: {e}")
        raise  # пусть caller поставит в retry queue

    if not parsed.get("is_signal"):
        return None
    if any(parsed.get(k) is None for k in ("symbol", "side", "entry", "stop", "tp1")):
        return None
    parsed["parser"] = "ai"
    return parsed


async def _extract_signal_from_image(image_bytes: bytes, caption: str = "") -> dict | None:
    """Скрин/баннер с ценами — vision включён по умолчанию (INGEST_VISION)."""
    if not ai_client.INGEST_VISION:
        return None
    if not ai_client.fast_configured() or not image_bytes:
        return None
    # Подпись явно «не сигнал» и длинная — не тратим vision.
    # Фото без текста / короткий caption — всегда пробуем.
    if caption.strip() and not looks_like_signal(caption) and len(caption) > 80:
        return None
    vision_system = (
        EXTRACTOR_SYSTEM_PROMPT
        + "\n\nКартинка — скрин сигнала, баннер канала или график с подписями Entry/SL/TP. "
        "Прочитай тикер, сторону и уровни с изображения (и подписи, если есть). "
        "Если на фото нет конкретной сделки с ценами — is_signal=false."
    )
    try:
        parsed = await ai_client.vision_json_completion(
            system=vision_system,
            image_bytes=image_bytes,
            caption=caption,
            max_tokens=260,
        )
    except Exception as e:
        print(f"[telegram_ingest] Ошибка извлечения сигнала с картинки: {e}")
        return None

    if not parsed.get("is_signal"):
        return None
    if any(parsed.get(k) is None for k in ("symbol", "side", "entry", "stop", "tp1")):
        return None
    parsed["parser"] = "vision"
    return parsed


def _message_has_image(msg) -> bool:
    """Фото или картинка-документ (каналы часто шлют баннер как file)."""
    if getattr(msg, "photo", None):
        return True
    doc = getattr(msg, "document", None)
    if not doc:
        return False
    mime = (getattr(doc, "mime_type", None) or "").lower()
    if mime.startswith("image/"):
        return True
    for attr in getattr(doc, "attributes", None) or []:
        if type(attr).__name__ == "DocumentAttributeImageSize":
            return True
    return False


def _derive_tp_ladder(side: str, entry: float, tp1: float) -> tuple[float, float]:
    """Мягкие TP2/TP3 только для отображения на графике.
    Для aggregated exit_mode=tp1_trail — tracker НЕ закрывает по ним."""
    step = tp1 - entry if side == 'LONG' else entry - tp1
    sign = 1 if side == 'LONG' else -1
    return tp1 + sign * step, tp1 + sign * 2 * step


def _channel_day_ok(display_name: str) -> bool:
    """Лимит сигналов с одного потока за сутки — иначе шумный канал съест квоту."""
    return db.channel_day_count(display_name) < MAX_PER_CHANNEL_DAY


def _channel_day_bump(display_name: str) -> None:
    db.channel_day_bump(display_name)


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


async def _extract_close_signal(text: str, symbol_base: str) -> dict | None:
    if not ai_client.fast_configured() or not text.strip():
        return None
    try:
        parsed = await ai_client.ingest_json_completion(
            system=CLOSE_SYSTEM_PROMPT,
            user_text=f"Тикер открытой позиции: {symbol_base}\n\nСообщение канала:\n{text[:3000]}",
            max_tokens=120,
        )
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


async def _handle_message(display_name: str, msg, channel_username: str | None = None):
    """`msg` — Telethon Message или NewMessage.Event.
    Предфильтр → regex → AI ingest JSON; vision только при INGEST_VISION=1."""
    channel = (channel_username or display_name).lstrip("@")
    msg_id = getattr(msg, "id", None)
    text = (msg.raw_text or "").strip() if hasattr(msg, "raw_text") else ""

    db.touch_ingest_health(channel, alias=display_name, message=True)

    if msg_id is not None and db.is_message_processed(channel, msg_id):
        db.clear_ingest_retry(channel, msg_id)
        return

    parsed = None
    ai_failed = False
    try:
        parsed = await _extract_signal(text) if text else None
    except Exception as e:
        ai_failed = True
        db.touch_ingest_health(channel, alias=display_name, error=str(e)[:200])
        if msg_id is not None:
            db.enqueue_ingest_retry(
                channel=channel,
                channel_alias=display_name,
                message_id=msg_id,
                text=text[:2000],
                reason=f"ai_error:{e}",
            )
            print(f"[telegram_ingest] {display_name}: AI fail → retry queue msg={msg_id}")
        return

    if (
        not parsed
        and not ai_failed
        and ai_client.INGEST_VISION
        and _message_has_image(msg)
        and (not text or looks_like_signal(text) or len(text) < 80)
    ):
        try:
            image_bytes = await msg.download_media(file=bytes)
        except Exception as e:
            print(f"[telegram_ingest] {display_name}: не удалось скачать картинку — {e}")
            image_bytes = None
        if image_bytes:
            try:
                parsed = await _extract_signal_from_image(image_bytes, text)
                if parsed:
                    print(f"[telegram_ingest] {display_name}: vision parse {parsed.get('symbol')} {parsed.get('side')}")
            except Exception as e:
                if msg_id is not None:
                    db.enqueue_ingest_retry(
                        channel=channel,
                        channel_alias=display_name,
                        message_id=msg_id,
                        text=text[:2000],
                        reason=f"vision_error:{e}",
                    )
                return

    if not parsed:
        await _try_close_from_channel(display_name, text)
        if msg_id is not None:
            db.mark_message_processed(channel, msg_id)
        return

    side = str(parsed["side"]).upper().strip()
    if side not in ('LONG', 'SHORT'):
        if msg_id is not None:
            db.mark_message_processed(channel, msg_id)
        return

    symbol = normalize_symbol(str(parsed["symbol"]))
    try:
        listed, exchange_id, ticker = await asyncio.to_thread(data_layer.probe_listings, symbol)
    except Exception as e:
        if msg_id is not None:
            db.enqueue_ingest_retry(
                channel=channel,
                channel_alias=display_name,
                message_id=msg_id,
                text=text[:2000],
                reason=f"exchange_error:{e}",
            )
        print(f"[telegram_ingest] {display_name}: exchange probe fail {symbol} → retry")
        return

    if not exchange_id or not ticker:
        print(f"[telegram_ingest] {display_name}: символ {symbol} не торгуется на Bybit/Binance, пропуск")
        if msg_id is not None:
            db.mark_message_processed(channel, msg_id)
        return

    listed_csv = ','.join(listed)
    parser_tag = parsed.get("parser") or "ai"
    print(f"[telegram_ingest] {display_name}: {symbol} via {exchange_id} [{parser_tag}] (listed: {listed_csv})")

    last = ticker.get("last")
    entry, stop, tp1 = float(parsed["entry"]), float(parsed["stop"]), float(parsed["tp1"])
    quality, qdetail = _score_setup(side, entry, stop, tp1, last, display_name)
    if quality is None:
        print(f"[telegram_ingest] {display_name}: {symbol} отклонён — {qdetail}")
        if msg_id is not None:
            db.mark_message_processed(channel, msg_id)
        return

    if not _channel_day_ok(display_name):
        print(f"[telegram_ingest] {display_name}: дневной лимит ({MAX_PER_CHANNEL_DAY}), пропуск {symbol}")
        if msg_id is not None:
            db.mark_message_processed(channel, msg_id)
        return

    if _count_open_aggregated() >= AGG_MAX_OPEN:
        print(f"[telegram_ingest] Лимит агрегатора ({AGG_MAX_OPEN}) достигнут, пропуск {symbol} от {display_name}")
        if msg_id is not None:
            db.mark_message_processed(channel, msg_id)
        return

    # TP2/TP3: только если канал сам назвал; иначе soft placeholders для UI
    if parsed.get("tp2") is not None and parsed.get("tp3") is not None:
        tp2, tp3 = float(parsed["tp2"]), float(parsed["tp3"])
    elif parsed.get("tp2") is not None:
        tp2 = float(parsed["tp2"])
        _, tp3 = _derive_tp_ladder(side, entry, tp1)
    else:
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
            f"Parser: {parser_tag}",
            f"Quality filter: {qdetail}",
            f"Листинг: {data_layer.listings_label(listed)}",
        ],
        score=quality,
        exchange=exchange_id,
        listed_on=listed_csv,
        exit_mode="tp1_trail",
    )
    if err:
        print(f"[telegram_ingest] {display_name}: {symbol} пропущен ({err})")
        if msg_id is not None:
            db.mark_message_processed(channel, msg_id)
            db.clear_ingest_retry(channel, msg_id)
        return

    _channel_day_bump(display_name)
    db.touch_ingest_health(channel, alias=display_name, signal=True)
    db.add_event(opened_symbol, "telegram_aggregate_signal",
                 f"{display_name}: {side} {opened_symbol} @ {entry} ({qdetail}, {listed_csv}, {parser_tag})")
    print(f"[telegram_ingest] Открыт сигнал {opened_symbol} от {display_name} ({qdetail}, via {exchange_id})")

    if msg_id is not None:
        db.mark_message_processed(channel, msg_id)
        db.clear_ingest_retry(channel, msg_id)

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


async def _retry_loop(channels: dict):
    """Повторная обработка сообщений после временных сбоев AI/биржи."""
    while True:
        await asyncio.sleep(30)
        try:
            due = db.pop_due_ingest_retries(limit=15)
            for item in due:
                alias = item["channel_alias"]
                ch = item["channel"]
                text = item.get("text") or ""
                # Синтетический msg с id — чтобы _handle_message мог mark/clear
                class _FakeMsg:
                    def __init__(self, mid, raw):
                        self.id = mid
                        self.raw_text = raw
                        self.photo = None

                try:
                    await _handle_message(alias, _FakeMsg(item["message_id"], text), ch)
                except Exception as e:
                    print(f"[telegram_ingest] retry fail {ch}/{item['message_id']}: {e}")
            db.purge_failed_ingest_retries()
        except Exception as e:
            print(f"[telegram_ingest] retry loop: {e}")


async def _health_loop(channels: dict):
    """Алерт админам, если канал молчит дольше INGEST_SILENCE_MINUTES."""
    # Даём ingest прогреться
    await asyncio.sleep(120)
    while True:
        try:
            rows = {r["channel"]: r for r in db.list_ingest_health()}
            now = datetime.now()
            silent = []
            for username, alias in channels.items():
                row = rows.get(username)
                last_at = row.get("last_message_at") if row else None
                if not last_at:
                    # ещё не было ни одного сообщения с момента старта — не орём сразу
                    continue
                try:
                    age_min = (now - datetime.fromisoformat(last_at)).total_seconds() / 60
                except (ValueError, TypeError):
                    continue
                if age_min >= INGEST_SILENCE_MINUTES:
                    # не спамим чаще раза в час на канал
                    last_alert = _last_silence_alert_at.get(username, 0)
                    if (now.timestamp() - last_alert) >= 3600:
                        silent.append(f"· {alias} (@{username}): тишина {age_min:.0f} мин")
                        _last_silence_alert_at[username] = now.timestamp()
            if silent:
                await telegram_bot._notify_admins(
                    "⚠️ Ingest health\n"
                    f"Каналы молчат >{INGEST_SILENCE_MINUTES} мин:\n"
                    + "\n".join(silent)
                )
        except Exception as e:
            print(f"[telegram_ingest] health loop: {e}")
        await asyncio.sleep(INGEST_HEALTH_CHECK_SEC)


def ingest_health_snapshot() -> dict:
    """Для API /api/ingest/health."""
    channels = _parse_channel_config(TELEGRAM_SOURCE_CHANNELS) if TELEGRAM_SOURCE_CHANNELS else {}
    rows = {r["channel"]: r for r in db.list_ingest_health()}
    now = datetime.now()
    items = []
    for username, alias in channels.items():
        row = rows.get(username) or {}
        last_msg = row.get("last_message_at")
        last_sig = row.get("last_signal_at")
        age_min = None
        if last_msg:
            try:
                age_min = round((now - datetime.fromisoformat(last_msg)).total_seconds() / 60, 1)
            except (ValueError, TypeError):
                age_min = None
        items.append({
            "channel": username,
            "alias": alias,
            "last_message_at": last_msg,
            "last_signal_at": last_sig,
            "silence_minutes": age_min,
            "ok": age_min is None or age_min < INGEST_SILENCE_MINUTES,
            "last_error": row.get("last_error"),
            "day_count": db.channel_day_count(alias),
            "day_limit": MAX_PER_CHANNEL_DAY,
        })
    return {
        "configured": is_configured(),
        "silence_threshold_min": INGEST_SILENCE_MINUTES,
        "channels": items,
        "open_aggregated": _count_open_aggregated(),
        "agg_max_open": AGG_MAX_OPEN,
    }


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
    processed_messages + open_signal() отбрасывают дубли."""
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
                        await _handle_message(display_name, msg, username)
                    except Exception as e:
                        print(f"[telegram_ingest] Ошибка догоняющей обработки сообщения из {display_name}: {e}")
            except Exception as e:
                print(f"[telegram_ingest] Ошибка догоняющего опроса {display_name}: {e}")
                db.touch_ingest_health(username, alias=display_name, error=str(e)[:200])


# Меньше lookback = меньше Haiku-вызовов на каждый рестарт Railway
STARTUP_LOOKBACK = int(os.getenv("INGEST_STARTUP_LOOKBACK", "12") or "12")


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
            await _handle_message(display_name, event, username)
        except Exception as e:
            print(f"[telegram_ingest] Ошибка обработки сообщения из {display_name}: {e}")

    await client.start()
    try:
        db.prune_processed_messages(keep_days=14)
    except Exception as e:
        print(f"[telegram_ingest] prune processed: {e}")

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
                    await _handle_message(display_name, msg, username)
                except Exception as e:
                    print(f"[telegram_ingest] Ошибка стартового догона {display_name}: {e}")
            print(f"[telegram_ingest] Стартовый догон {display_name}: {len(recent)} сообщений")
        except Exception as e:
            print(f"[telegram_ingest] Не удалось прочитать {display_name}: {e}")
            last_ids[username] = 0
            db.touch_ingest_health(username, alias=display_name, error=str(e)[:200])

    backfill_task = asyncio.create_task(_backfill_loop(client, channels, last_ids))
    retry_task = asyncio.create_task(_retry_loop(channels))
    health_task = asyncio.create_task(_health_loop(channels))
    print(f"[telegram_ingest] Запущен, слушаю каналы: {', '.join(channels.values())}")
    try:
        await client.run_until_disconnected()
    finally:
        for task in (backfill_task, retry_task, health_task):
            task.cancel()
            try:
                await task
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
