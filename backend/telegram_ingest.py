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
import json
import base64
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


async def _extract_signal_from_image(image_bytes: bytes, caption: str = "") -> dict | None:
    """Некоторые каналы публикуют сигнал как скриншот/баннер (цены нарисованы
    на картинке) без подписи или с почти пустой подписью — такие посты раньше
    вообще не попадали в анализ, потому что _extract_signal читает только
    текст. Тот же промпт и та же схема ответа, просто по картинке вместо
    текста (gpt-4o-mini умеет читать изображения)."""
    if not OPENAI_API_KEY or not image_bytes:
        return None
    b64 = base64.b64encode(image_bytes).decode()
    user_content = [
        {"type": "text", "text": caption[:500] if caption.strip() else "Извлеки параметры сигнала со скриншота."},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ]
    payload = {
        "model": AI_MODEL,
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
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
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
        bio="Автоматический импорт из внешнего потока данных (Premium Aggregator Feed)",
    )

    opened_symbol, err = open_signal(
        symbol, side, entry, stop, tp1, tp2, tp3,
        trader_id=trader_id, regime=SOURCE_TYPE,
        reasons=[f"Сигнал получен методом автоматического импорта из внешнего потока: {display_name}"],
    )
    if err:
        print(f"[telegram_ingest] {display_name}: {symbol} пропущен ({err})")
        return

    db.add_event(opened_symbol, "telegram_aggregate_signal",
                 f"{display_name}: {side} {opened_symbol} @ {entry}")
    print(f"[telegram_ingest] Открыт сигнал {opened_symbol} от {display_name}")


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
        display_name = channels.get(username, "Сторонний агрегированный поток данных (Провайдер)")
        try:
            await _handle_message(display_name, event)
        except Exception as e:
            print(f"[telegram_ingest] Ошибка обработки сообщения из {display_name}: {e}")

    await client.start()

    last_ids = {}
    for username in channels:
        try:
            latest = await client.get_messages(username, limit=1)
            last_ids[username] = latest[0].id if latest else 0
        except Exception as e:
            print(f"[telegram_ingest] Не удалось получить последний message id для {channels[username]}: {e}")
            last_ids[username] = 0
    asyncio.create_task(_backfill_loop(client, channels, last_ids))

    print(f"[telegram_ingest] Запущен, слушаю каналы: {', '.join(channels.values())}")
    await client.run_until_disconnected()
