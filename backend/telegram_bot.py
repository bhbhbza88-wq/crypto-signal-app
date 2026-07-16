"""
Telegram-бот NOWICKI: меню, Premium, уведомления о сигналах.
Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
     CRYPTO_PAY_ADDRESS, CRYPTO_PAY_NETWORK, CRYPTO_PAY_AMOUNT
"""
import os
import hashlib
import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CHANNEL_URL = "https://telegram.me/chlebchik"
SITE_URL = "https://nowicki.trade"
SUPPORT_USER = "Kupyansk_2"
SUPPORT_URL = f"https://telegram.me/{SUPPORT_USER}"

CRYPTO_PAY_ADDRESS = os.getenv("CRYPTO_PAY_ADDRESS", "").strip()
CRYPTO_PAY_NETWORK = os.getenv("CRYPTO_PAY_NETWORK", "USDT TRC20").strip() or "USDT TRC20"
CRYPTO_PAY_AMOUNT = os.getenv("CRYPTO_PAY_AMOUNT", "29").strip() or "29"

WEBHOOK_SECRET = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).hexdigest()[:32] if TELEGRAM_BOT_TOKEN else ""
HR = "────────────"


async def _api(method: str, payload: dict | None = None):
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            return (await client.post(url, json=payload or {})).json()
    except Exception as e:
        print(f"[telegram_bot] {method} error: {e}")
        return None


async def set_webhook():
    if not TELEGRAM_BOT_TOKEN:
        return
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not domain:
        print("[telegram_bot] RAILWAY_PUBLIC_DOMAIN не задан — вебхук пропущен")
        return
    webhook_url = f"https://{domain}/api/telegram-webhook"
    data = await _api("setWebhook", {"url": webhook_url, "secret_token": WEBHOOK_SECRET})
    print(f"[telegram_bot] Вебхук: {webhook_url}" if data and data.get("ok") else f"[telegram_bot] Ошибка вебхука: {data}")
    await _api("setMyCommands", {
        "commands": [
            {"command": "start", "description": "Меню"},
            {"command": "premium", "description": "Оплата Premium"},
            {"command": "help", "description": "Помощь"},
        ]
    })


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _api("sendMessage", payload)


def _dock():
    return {
        "keyboard": [[{"text": "💎 Premium"}, {"text": "📡 Канал"}, {"text": "✍️ Поддержка"}]],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def _menu_kb():
    return {"inline_keyboard": [
        [{"text": "💎 Оформить Premium", "callback_data": "premium"}],
        [
            {"text": "📡 Канал", "url": CHANNEL_URL},
            {"text": "🌐 Сайт", "url": SITE_URL},
        ],
        [{"text": f"✍️ @{SUPPORT_USER}", "url": SUPPORT_URL}],
    ]}


def _premium_kb():
    return {"inline_keyboard": [
        [{"text": f"✍️ Написать @{SUPPORT_USER}", "url": SUPPORT_URL}],
        [
            {"text": "🌐 Тарифы", "url": f"{SITE_URL}/app/pricing"},
            {"text": "‹ Меню", "callback_data": "menu"},
        ],
    ]}


async def send_welcome(chat_id: int, start_payload: str = "", with_dock: bool = False):
    if start_payload.strip().lower() in ("premium", "pay"):
        await send_premium(chat_id)
        return
    text = (
        f"<b>◈ NOWICKI</b>\n"
        f"{HR}\n"
        "AI-сканер ищет точки входа\n"
        "с уровнями <b>entry · stop · TP</b>.\n\n"
        "Сигналы — в канале и на сайте.\n"
        "Premium — полная история и AI."
    )
    kb = _menu_kb()
    if with_dock:
        await send_message(chat_id, text, _dock())
        await send_message(chat_id, "Быстрые действия:", kb)
    else:
        await send_message(chat_id, text, kb)


async def send_premium(chat_id: int):
    if CRYPTO_PAY_ADDRESS:
        pay = (
            f"<b>1.</b> Переведи <b>${CRYPTO_PAY_AMOUNT}</b> USDT\n"
            f"Сеть: <b>{CRYPTO_PAY_NETWORK}</b>\n"
            f"<code>{CRYPTO_PAY_ADDRESS}</code>\n\n"
            f"<b>2.</b> Напиши <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a>\n"
            f"email аккаунта + скрин / tx"
        )
    else:
        pay = f"Для оплаты напиши <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a>"
    text = (
        f"<b>💎 Premium · ${CRYPTO_PAY_AMOUNT}/мес</b>\n"
        f"{HR}\n"
        "· полная история сделок\n"
        "· PnL по дням\n"
        "· AI-ассистент 50/день\n"
        f"{HR}\n"
        f"{pay}"
    )
    await send_message(chat_id, text, _premium_kb())


async def send_help(chat_id: int):
    text = (
        f"<b>Помощь</b>\n"
        f"{HR}\n"
        "/start — меню\n"
        "/premium — оплата\n"
        "/help — эта справка\n\n"
        f"После оплаты пиши <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a>\n"
        f"Сайт: {SITE_URL}"
    )
    await send_message(chat_id, text, _menu_kb())


async def send_support(chat_id: int):
    text = (
        f"<b>Поддержка</b>\n"
        f"{HR}\n"
        f"Пиши <a href=\"{SUPPORT_URL}\"><b>@{SUPPORT_USER}</b></a>\n\n"
        "Укажи email с nowicki.trade\n"
        "и скрин оплаты, если переводил."
    )
    await send_message(chat_id, text, {"inline_keyboard": [
        [{"text": f"Открыть @{SUPPORT_USER}", "url": SUPPORT_URL}],
        [{"text": "💎 Premium", "callback_data": "premium"}],
    ]})


async def handle_update(update: dict):
    cb = update.get("callback_query")
    if cb:
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        data = (cb.get("data") or "").strip().lower()
        await _api("answerCallbackQuery", {"callback_query_id": cb.get("id")})
        if not chat_id:
            return
        if data == "premium":
            await send_premium(chat_id)
        elif data == "menu":
            await send_welcome(chat_id)
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = message.get("chat", {}).get("id")
    text = str(message.get("text") or "").strip()
    if not chat_id or not text:
        return

    if text == "💎 Premium":
        await send_premium(chat_id); return
    if text == "📡 Канал":
        await send_message(chat_id, f"📡 {CHANNEL_URL}"); return
    if text == "✍️ Поддержка":
        await send_support(chat_id); return

    cmd, _, payload = text.partition(" ")
    cmd = cmd.split("@", 1)[0].lower()

    if cmd == "/start":
        await send_welcome(chat_id, payload, with_dock=True)
    elif cmd in ("/premium", "/pay"):
        await send_premium(chat_id)
    elif cmd == "/help":
        await send_help(chat_id)
    elif cmd == "/support":
        await send_support(chat_id)
    else:
        await send_welcome(chat_id)


async def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    await _api("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    })


async def notify_new_signal(signal: dict):
    sym = signal.get("symbol", "")
    side = signal.get("signal", "")
    score = signal.get("score", 0)
    entry = signal.get("entry", 0)
    tp1 = signal.get("tp1", 0)
    tp2 = signal.get("tp2", 0)
    tp3 = signal.get("tp3", 0)
    stop = signal.get("stop", 0)
    regime = signal.get("regime", "")
    reasons = signal.get("entry_reasons", [])

    emoji = "🟢" if side == "LONG" else "🔴"
    conf = round((score / 20) * 100) if score else 0
    conf_emoji = "🔥" if conf >= 80 else "⚡" if conf >= 60 else "⚠️"

    text = (
        f"{emoji} <b>NOWICKI — {side}</b>\n"
        f"{HR}\n"
        f"<b>{sym}</b> · Bybit\n"
        f"{conf_emoji} {conf}% · {regime}\n"
        f"{HR}\n"
        f"Вход  <code>{entry:.4f}</code>\n"
        f"TP1   <code>{tp1:.4f}</code>\n"
        f"TP2   <code>{tp2:.4f}</code>\n"
        f"TP3   <code>{tp3:.4f}</code>\n"
        f"Стоп  <code>{stop:.4f}</code>\n"
    )
    if reasons:
        text += f"{HR}\n" + "\n".join(f"· {r}" for r in reasons[:3])
    text += "\n\n<i>Не финансовый совет</i>"
    await send_telegram(text)


async def notify_manual_signal(signal: dict, source: str):
    sym = signal.get("symbol", "")
    side = signal.get("signal", "")
    entry = signal.get("entry", 0)
    tp1 = signal.get("tp1", 0)
    tp2 = signal.get("tp2", 0)
    tp3 = signal.get("tp3", 0)
    stop = signal.get("stop", 0)
    emoji = "🟢" if side == "LONG" else "🔴"
    text = (
        f"{emoji} <b>NOWICKI — {side}</b>\n"
        f"{HR}\n"
        f"<b>{sym}</b> · {source}\n"
        f"{HR}\n"
        f"Вход  <code>{entry:.4f}</code>\n"
        f"TP1   <code>{tp1:.4f}</code>\n"
        f"TP2   <code>{tp2:.4f}</code>\n"
        f"TP3   <code>{tp3:.4f}</code>\n"
        f"Стоп  <code>{stop:.4f}</code>\n"
        f"\n<i>Не финансовый совет</i>"
    )
    await send_telegram(text)


async def notify_signal_closed(signal: dict, result: str, pnl: float):
    sym = signal.get("symbol", "")
    side = signal.get("signal", "")
    emoji = "✅" if pnl > 0 else "❌"
    pnl_str = f"+{pnl:.2f}%" if pnl > 0 else f"{pnl:.2f}%"
    labels = {
        "tp1": "TP1", "tp2": "TP2", "tp3": "TP3", "sl": "Стоп",
        "be": "Б/У", "potential": "Закрыто", "timeout": "Таймаут",
        "channel_closed": "Закрыто",
    }
    text = (
        f"{emoji} <b>Закрыто</b> · {sym} {side}\n"
        f"{labels.get(result, result)} · <b>{pnl_str}</b>"
    )
    await send_telegram(text)


async def notify_market_phase(old_phase: str, new_phase: str, details: dict):
    labels = {"UPTREND": "Аптренд", "DOWNTREND": "Даунтренд", "SIDEWAYS": "Боковик"}
    text = (
        f"📊 <b>Фаза рынка</b>\n"
        f"{labels.get(old_phase, old_phase)} → <b>{labels.get(new_phase, new_phase)}</b>"
    )
    await send_telegram(text)


async def notify_trend_signal(symbol: str, action: str, price: float, pnl: float = None):
    sym = symbol.replace("/USDT", "")
    if action == "enter":
        text = f"📈 <b>Trend вход</b> · {sym}\n<code>{price:.4f}</code>"
    else:
        pnl_str = f"+{pnl:.1f}%" if (pnl or 0) > 0 else f"{pnl:.1f}%"
        text = f"📉 <b>Trend выход</b> · {sym}\n<code>{price:.4f}</code> · {pnl_str}"
    await send_telegram(text)


async def send_daily_summary(stats: dict):
    today = stats.get("today", {})
    total = today.get("total", 0)
    winrate = today.get("winrate", 0)
    pnl = today.get("total_pnl", 0)
    pnl_str = f"+{pnl:.2f}%" if pnl > 0 else f"{pnl:.2f}%"
    emoji = "📈" if pnl > 0 else "📉"
    text = (
        f"{emoji} <b>Итоги дня</b>\n"
        f"Сделок {total} · WR {winrate}% · PnL <b>{pnl_str}</b>"
    )
    await send_telegram(text)
