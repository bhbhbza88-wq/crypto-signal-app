"""
Telegram уведомления и диалог с пользователем для NOWICKI.
Env:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  CRYPTO_PAY_ADDRESS   — USDT-адрес (TRC20/TON и т.п.)
  CRYPTO_PAY_NETWORK   — подпись сети, по умолчанию USDT TRC20
  CRYPTO_PAY_AMOUNT    — сумма за месяц, по умолчанию 29
"""
import os
import hashlib
import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

CHANNEL_URL = "https://telegram.me/chlebchik"
SITE_URL = "https://nowicki.trade"

CRYPTO_PAY_ADDRESS = os.getenv("CRYPTO_PAY_ADDRESS", "").strip()
CRYPTO_PAY_NETWORK = os.getenv("CRYPTO_PAY_NETWORK", "USDT TRC20").strip() or "USDT TRC20"
CRYPTO_PAY_AMOUNT = os.getenv("CRYPTO_PAY_AMOUNT", "29").strip() or "29"

WEBHOOK_SECRET = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).hexdigest()[:32] if TELEGRAM_BOT_TOKEN else ""


async def _api(method: str, payload: dict | None = None):
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload or {})
            return resp.json()
    except Exception as e:
        print(f"[telegram_bot] {method} error: {e}")
        return None


async def set_webhook():
    """Регистрирует вебхук + меню команд при старте приложения."""
    if not TELEGRAM_BOT_TOKEN:
        return
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not domain:
        print("[telegram_bot] RAILWAY_PUBLIC_DOMAIN не задан — вебхук не зарегистрирован "
              "(ожидаемо при локальном запуске, не в проде)")
        return
    webhook_url = f"https://{domain}/api/telegram-webhook"
    data = await _api("setWebhook", {"url": webhook_url, "secret_token": WEBHOOK_SECRET})
    if data and data.get("ok"):
        print(f"[telegram_bot] Вебхук зарегистрирован: {webhook_url}")
    else:
        print(f"[telegram_bot] Ошибка регистрации вебхука: {data}")

    cmds = await _api("setMyCommands", {
        "commands": [
            {"command": "start", "description": "Старт и ссылки"},
            {"command": "help", "description": "Что умеет бот"},
            {"command": "premium", "description": "Оплата Premium криптой"},
            {"command": "status", "description": "Статистика и сайт"},
        ]
    })
    if cmds and cmds.get("ok"):
        print("[telegram_bot] Меню команд обновлено")


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


def _main_keyboard():
    return {"inline_keyboard": [
        [{"text": "📡 Канал с сигналами", "url": CHANNEL_URL}],
        [{"text": "📈 Открыть платформу", "url": SITE_URL}],
        [{"text": "💎 Premium", "callback_data": "premium"}],
    ]}


async def send_welcome(chat_id: int, start_payload: str = ""):
    if start_payload.strip().lower() in ("premium", "pay", "vip"):
        await send_premium(chat_id)
        return
    text = (
        "👋 <b>Привет! Это NOWICKI.</b>\n\n"
        "AI-сканер ищет точки входа с уровнями TP/SL.\n"
        "На сайте — живая лента, винрейт и история сделок.\n\n"
        "Команды: /premium · /status · /help"
    )
    await send_message(chat_id, text, _main_keyboard())


async def send_help(chat_id: int):
    text = (
        "📖 <b>Команды NOWICKI</b>\n\n"
        "/start — приветствие и ссылки\n"
        "/premium — оплата Premium криптой\n"
        "/status — статистика и сайт\n"
        "/help — это меню\n\n"
        f"Канал: {CHANNEL_URL}\n"
        f"Платформа: {SITE_URL}"
    )
    await send_message(chat_id, text, _main_keyboard())


async def send_premium(chat_id: int):
    if CRYPTO_PAY_ADDRESS:
        addr_block = (
            f"Сеть: <b>{CRYPTO_PAY_NETWORK}</b>\n"
            f"Адрес:\n<code>{CRYPTO_PAY_ADDRESS}</code>\n\n"
            "После оплаты напиши сюда:\n"
            "1) email аккаунта на nowicki.trade\n"
            "2) скрин / tx hash перевода\n\n"
            "Активируем Premium вручную в течение дня."
        )
    else:
        addr_block = (
            "Адрес для оплаты скоро появится здесь.\n"
            "Пока напиши нам email аккаунта на nowicki.trade — "
            "подскажем, куда перевести."
        )
    text = (
        f"💎 <b>NOWICKI Premium — ${CRYPTO_PAY_AMOUNT}/мес</b>\n\n"
        "• Полная история сделок и PnL\n"
        "• AI-ассистент 50 запросов/день\n"
        "• Приоритетный доступ к фичам\n\n"
        f"{addr_block}\n\n"
        "⚠️ Не является финансовым советом"
    )
    keyboard = {"inline_keyboard": [
        [{"text": "📈 Открыть платформу", "url": f"{SITE_URL}/app/pricing"}],
        [{"text": "📡 Канал", "url": CHANNEL_URL}],
    ]}
    await send_message(chat_id, text, keyboard)


async def send_status(chat_id: int):
    text = (
        "📊 <b>Статус NOWICKI</b>\n\n"
        "Сканер онлайн · сигналы публикуются в канал и на сайт.\n"
        "Актуальный винрейт и история — на платформе.\n\n"
        f"👉 {SITE_URL}\n"
        f"📡 {CHANNEL_URL}\n\n"
        "Premium: /premium"
    )
    await send_message(chat_id, text, _main_keyboard())


async def handle_update(update: dict):
    """Роутер команд и callback-кнопок из webhook."""
    cb = update.get("callback_query")
    if cb:
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        data = (cb.get("data") or "").strip().lower()
        if chat_id and data in ("premium", "pay"):
            await send_premium(chat_id)
            await _api("answerCallbackQuery", {"callback_query_id": cb.get("id")})
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = message.get("chat", {}).get("id")
    text = str(message.get("text") or "").strip()
    if not chat_id or not text:
        return

    cmd, _, payload = text.partition(" ")
    cmd = cmd.split("@", 1)[0].lower()

    if cmd == "/start":
        await send_welcome(chat_id, payload)
    elif cmd in ("/help", "/menu"):
        await send_help(chat_id)
    elif cmd in ("/premium", "/pay"):
        await send_premium(chat_id)
    elif cmd in ("/status", "/stats"):
        await send_status(chat_id)
    else:
        await send_message(
            chat_id,
            "Не понял команду. Напиши /help — покажу доступные опции.",
        )


async def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    await _api("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    })


async def notify_new_signal(signal: dict):
    sym   = signal.get("symbol", "")
    side  = signal.get("signal", "")
    score = signal.get("score", 0)
    entry = signal.get("entry", 0)
    tp1   = signal.get("tp1", 0)
    tp2   = signal.get("tp2", 0)
    tp3   = signal.get("tp3", 0)
    stop  = signal.get("stop", 0)
    regime= signal.get("regime", "")
    reasons = signal.get("entry_reasons", [])

    emoji = "🟢" if side == "LONG" else "🔴"
    conf  = round((score / 20) * 100) if score else 0
    conf_emoji = "🔥" if conf >= 80 else "⚡" if conf >= 60 else "⚠️"

    text = (
        f"{emoji} <b>NOWICKI SIGNAL — {side}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{sym}</b> · Bybit\n"
        f"{conf_emoji} Уверенность: <b>{conf}%</b> (Score {score}/20)\n"
        f"📈 Режим рынка: <b>{regime}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Вход:  <code>{entry:.4f}</code>\n"
        f"🎯 TP1:   <code>{tp1:.4f}</code>\n"
        f"🎯 TP2:   <code>{tp2:.4f}</code>\n"
        f"🎯 TP3:   <code>{tp3:.4f}</code>\n"
        f"🛑 Стоп:  <code>{stop:.4f}</code>\n"
    )

    if reasons:
        text += "━━━━━━━━━━━━━━━━\n"
        text += "📋 <b>Причины входа:</b>\n"
        for r in reasons[:4]:
            text += f"• {r}\n"

    text += "\n⚠️ <i>Не является финансовым советом</i>"
    await send_telegram(text)


async def notify_manual_signal(signal: dict, source: str):
    """Сигнал от трейдера / внешнего источника — без V8 score."""
    sym   = signal.get("symbol", "")
    side  = signal.get("signal", "")
    entry = signal.get("entry", 0)
    tp1   = signal.get("tp1", 0)
    tp2   = signal.get("tp2", 0)
    tp3   = signal.get("tp3", 0)
    stop  = signal.get("stop", 0)

    emoji = "🟢" if side == "LONG" else "🔴"
    text = (
        f"{emoji} <b>NOWICKI SIGNAL — {side}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{sym}</b> · Bybit\n"
        f"✍️ Автор: <b>{source}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Вход:  <code>{entry:.4f}</code>\n"
        f"🎯 TP1:   <code>{tp1:.4f}</code>\n"
        f"🎯 TP2:   <code>{tp2:.4f}</code>\n"
        f"🎯 TP3:   <code>{tp3:.4f}</code>\n"
        f"🛑 Стоп:  <code>{stop:.4f}</code>\n"
        f"\n⚠️ <i>Не является финансовым советом</i>"
    )
    await send_telegram(text)


async def notify_signal_closed(signal: dict, result: str, pnl: float):
    sym  = signal.get("symbol", "")
    side = signal.get("signal", "")
    emoji = "✅" if pnl > 0 else "❌"
    pnl_str = f"+{pnl:.2f}%" if pnl > 0 else f"{pnl:.2f}%"

    result_labels = {
        "tp1": "TP1 достигнут 🎯",
        "tp2": "TP2 достигнут 🎯🎯",
        "tp3": "TP3 достигнут 🎯🎯🎯",
        "sl":  "Стоп-лосс ❌",
        "be":  "Безубыток ↔️",
        "potential": "Закрыто по потере потенциала ⚠️",
        "timeout": "Закрыто по таймауту ⏱",
        "channel_closed": "Закрыто источником сигнала 📡",
    }

    text = (
        f"{emoji} <b>NOWICKI — Сделка закрыта</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{sym}</b> · {side}\n"
        f"📋 Результат: <b>{result_labels.get(result, result)}</b>\n"
        f"💵 PnL: <b>{pnl_str}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<i>NOWICKI Crypto Scanner</i>"
    )
    await send_telegram(text)


async def notify_market_phase(old_phase: str, new_phase: str, details: dict):
    labels = {'UPTREND': 'АПТРЕНД 📈', 'DOWNTREND': 'ДАУНТРЕНД 📉', 'SIDEWAYS': 'БОКОВИК ↔️'}
    emoji = {'UPTREND': '🟢', 'DOWNTREND': '🔴', 'SIDEWAYS': '🟡'}.get(new_phase, '🔵')
    text = (
        f"{emoji} <b>NOWICKI — Смена фазы рынка</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Было: <b>{labels.get(old_phase, old_phase)}</b>\n"
        f"Стало: <b>{labels.get(new_phase, new_phase)}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 BTC: <code>{details.get('btc_close', 0)}</code>\n"
        f"🌡 Монет в аптренде: <b>{details.get('breadth_pct', 0)}%</b>\n"
        f"⚡ Моментум 60д: <b>{details.get('momentum_60d_pct', 0)}%</b>\n"
        f"✅ Risk-on: <b>{details.get('risk_on_score', 0)}/4</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<i>Информационно — не торговый сигнал</i>"
    )
    await send_telegram(text)


async def notify_trend_signal(symbol: str, action: str, price: float, pnl: float = None):
    sym = symbol.replace('/USDT', '')
    if action == 'enter':
        text = (
            f"📈 <b>Trend-Following — ВХОД</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{sym}</b> вошёл в восходящий тренд (EMA50&gt;EMA200)\n"
            f"💰 Цена: <code>{price:.4f}</code>\n"
            f"<i>Держим, пока тренд вверх. Выход — пересечение EMA вниз.</i>"
        )
    else:
        pnl_str = f"+{pnl:.1f}%" if (pnl or 0) > 0 else f"{pnl:.1f}%"
        emoji = "✅" if (pnl or 0) > 0 else "🔻"
        text = (
            f"{emoji} <b>Trend-Following — ВЫХОД</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{sym}</b> вышел из тренда → кэш\n"
            f"💰 Цена: <code>{price:.4f}</code> · PnL: <b>{pnl_str}</b>\n"
            f"<i>Тренд развернулся (EMA50&lt;EMA200).</i>"
        )
    await send_telegram(text)


async def send_daily_summary(stats: dict):
    today = stats.get("today", {})
    total = today.get("total", 0)
    winrate = today.get("winrate", 0)
    pnl = today.get("total_pnl", 0)
    pnl_str = f"+{pnl:.2f}%" if pnl > 0 else f"{pnl:.2f}%"
    emoji = "📈" if pnl > 0 else "📉"

    text = (
        f"{emoji} <b>NOWICKI — Итоги дня</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 Сделок: <b>{total}</b>\n"
        f"🎯 Винрейт: <b>{winrate}%</b>\n"
        f"💵 PnL: <b>{pnl_str}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"TP1: {today.get('tp1', 0)} | "
        f"TP2+: {today.get('tp2_plus', 0)} | "
        f"Стоп: {today.get('stops', 0)} | "
        f"Б/У: {today.get('breakeven', 0)}\n"
        f"<i>NOWICKI Crypto Scanner</i>"
    )
    await send_telegram(text)
