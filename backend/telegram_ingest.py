"""
Premium Aggregator Feed — слушает публичные Telegram-каналы через Telethon и
извлекает из сообщений явные сделки (символ/сторона/вход/стоп/TP1) через
OpenAI. Работает только если сконфигурирован через env — иначе no-op, чтобы
обычный запуск (dev или прод без настроенного парсера) не ломался.

Честность источника: имя канала попадает в traders.name как есть,
source_type='telegram_aggregate' — только для внутреннего учёта/лимита.
source_url НЕ сохраняется и никуда не выводится: пользователю показываем
текстовое "Источник: <канал>" без ссылки (см. SignalCard.jsx) — атрибуция
есть, трафик на сторонние каналы не уводим. TP2/TP3 в сообщениях канала
почти никогда не называются тремя уровнями — достраиваем их от TP1 тем же
шагом, что entry->TP1 (наша собственная trailing-механика, не выдаём это
за слова канала — ни в reasons, ни где-либо ещё).
"""

import os
import json
import asyncio

import httpx

import database as db
import data_layer
from signal_ingest import normalize_symbol, open_signal

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")
# "username1:Display Name 1,username2:Display Name 2"
TELEGRAM_SOURCE_CHANNELS = os.getenv("TELEGRAM_SOURCE_CHANNELS", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = "gpt-4o-mini"

SOURCE_TYPE = "telegram_aggregate"
AGG_MAX_OPEN = 5

EXTRACTOR_SYSTEM_PROMPT = (
    "Ты извлекаешь параметры торгового сигнала из сообщения крипто-канала. "
    "Верни ТОЛЬКО JSON без пояснений: "
    '{"is_signal": bool, "symbol": string, "side": "LONG"|"SHORT", '
    '"entry": number, "stop": number, "tp1": number}. '
    "is_signal=false, если в сообщении нет конкретной сделки с явной ценой входа "
    "и стоп-лоссом (реклама, комментарий, разбор без чисел, апдейт по старой "
    "позиции, объявление без риск-менеджмента). Не придумывай entry/stop/tp1, "
    "если они не названы в тексте прямо — в этом случае is_signal=false. "
    "symbol верни как тикер к USDT, например BTCUSDT."
)


def _parse_channel_config(raw: str) -> dict:
    channels = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        username, _, display = part.partition(":")
        username = username.strip().lstrip("@")
        channels[username] = (display.strip() or username)
    return channels


async def _extract_signal(text: str) -> dict | None:
    if not OPENAI_API_KEY or not text.strip():
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
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
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


def _derive_tp_ladder(side: str, entry: float, tp1: float) -> tuple[float, float]:
    """Канал почти никогда не называет TP2/TP3 отдельно — достраиваем их от TP1
    тем же шагом, что entry->TP1. Это наша механика частичного закрытия,
    а не слова канала — никогда не подписываем это как исходящее от источника."""
    step = tp1 - entry if side == 'LONG' else entry - tp1
    sign = 1 if side == 'LONG' else -1
    return tp1 + sign * step, tp1 + sign * 2 * step


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


async def _handle_message(display_name: str, text: str):
    parsed = await _extract_signal(text)
    if not parsed:
        return

    side = str(parsed["side"]).upper().strip()
    if side not in ('LONG', 'SHORT'):
        return

    symbol = normalize_symbol(str(parsed["symbol"]))
    ticker = await asyncio.to_thread(data_layer.fetch_ticker, symbol)
    if not ticker:
        print(f"[telegram_ingest] {display_name}: символ {symbol} не торгуется на Bybit, пропуск")
        return

    if _count_open_aggregated() >= AGG_MAX_OPEN:
        print(f"[telegram_ingest] Лимит агрегатора ({AGG_MAX_OPEN}) достигнут, пропуск {symbol} от {display_name}")
        return

    entry, stop, tp1 = float(parsed["entry"]), float(parsed["stop"]), float(parsed["tp1"])
    tp2, tp3 = _derive_tp_ladder(side, entry, tp1)

    trader_id = db.get_or_create_source_trader(
        display_name, source_url=None, source_type=SOURCE_TYPE,
        bio="Мониторинг публичного Telegram-канала (Premium Aggregator Feed)",
    )

    opened_symbol, err = open_signal(
        symbol, side, entry, stop, tp1, tp2, tp3,
        trader_id=trader_id, regime=SOURCE_TYPE,
        reasons=[f"Агрегированный сигнал из приватного источника: {display_name}"],
    )
    if err:
        print(f"[telegram_ingest] {display_name}: {symbol} пропущен ({err})")
        return

    db.add_event(opened_symbol, "telegram_aggregate_signal",
                 f"{display_name}: {side} {opened_symbol} @ {entry}")
    print(f"[telegram_ingest] Открыт сигнал {opened_symbol} от {display_name}")


def is_configured() -> bool:
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION and TELEGRAM_SOURCE_CHANNELS)


async def run():
    if not is_configured():
        print("[telegram_ingest] Не сконфигурирован (нужны TELEGRAM_API_ID/HASH/SESSION/SOURCE_CHANNELS) — пропуск запуска")
        return

    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    channels = _parse_channel_config(TELEGRAM_SOURCE_CHANNELS)
    client = TelegramClient(StringSession(TELEGRAM_SESSION), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)

    @client.on(events.NewMessage(chats=list(channels.keys())))
    async def _on_message(event):
        chat = await event.get_chat()
        username = (getattr(chat, "username", "") or "").lstrip("@")
        display_name = channels.get(username, username or "Telegram")
        try:
            await _handle_message(display_name, event.raw_text or "")
        except Exception as e:
            print(f"[telegram_ingest] Ошибка обработки сообщения из {display_name}: {e}")

    await client.start()
    print(f"[telegram_ingest] Запущен, слушаю каналы: {', '.join(channels.values())}")
    await client.run_until_disconnected()
