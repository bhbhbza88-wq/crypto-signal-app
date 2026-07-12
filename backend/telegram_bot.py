"""
Telegram уведомления для NWICKI
Добавь в Railway переменные окружения:
  TELEGRAM_BOT_TOKEN=твой_токен
  TELEGRAM_CHAT_ID=твой_chat_id
"""
import os
import hashlib
import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Канал, куда ведёт кнопка приветствия — первая точка контакта до перехода
# в реальный канал (см. /api/telegram-webhook в main.py).
CHANNEL_URL = "https://t.me/chlebchik"
SITE_URL = "https://terrific-expression-production.up.railway.app"

# Секрет для проверки, что POST на /api/telegram-webhook реально пришёл от
# Telegram, а не от кого попало — детерминированно выводим из токена бота,
# чтобы не заводить ещё одну переменную окружения на Railway.
WEBHOOK_SECRET = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).hexdigest()[:32] if TELEGRAM_BOT_TOKEN else ""


async def set_webhook():
    """Регистрирует вебхук в Telegram — вызывается один раз при старте приложения
    (main.py lifespan). Идемпотентно: повторный вызов с тем же URL не ломает
    ничего, просто подтверждает регистрацию заново на каждом деплое.
    RAILWAY_PUBLIC_DOMAIN — переменная, которую Railway сам прокидывает в
    контейнер для сервисов с публичным доменом, вручную задавать не нужно."""
    if not TELEGRAM_BOT_TOKEN:
        return
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not domain:
        print("[telegram_bot] RAILWAY_PUBLIC_DOMAIN не задан — вебхук не зарегистрирован "
              "(ожидаемо при локальном запуске, не в проде)")
        return
    webhook_url = f"https://{domain}/api/telegram-webhook"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"url": webhook_url, "secret_token": WEBHOOK_SECRET})
            data = resp.json()
            if data.get("ok"):
                print(f"[telegram_bot] Вебхук зарегистрирован: {webhook_url}")
            else:
                print(f"[telegram_bot] Ошибка регистрации вебхука: {data}")
    except Exception as e:
        print(f"[telegram_bot] Ошибка регистрации вебхука: {e}")


async def send_welcome(chat_id: int):
    """Приветствие для пользователя, который написал боту /start — первым делом
    встречает его бот с кнопкой в реальный канал, а не голая ссылка."""
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = (
        "👋 <b>Привет! Это NWICKI.</b>\n\n"
        "AI-сканер анализирует крипторынок каждые 2 минуты и находит точки входа "
        "с уровнями TP/SL — без магии, на технических индикаторах (EMA, RSI, ADX, ATR).\n\n"
        "Чем мы отличаемся от других каналов с сигналами:\n"
        "🎯 Показываем <b>реальный винрейт</b> — не только удачные сделки\n"
        "📊 Три независимые стратегии торгуют <b>на бумаге</b>, прежде чем на реальные деньги\n"
        "🚫 Никаких обещаний «иксов» и гарантированной прибыли\n\n"
        "Жми на кнопку ниже — увидишь сигналы и статистику 👇"
    )
    keyboard = {"inline_keyboard": [
        [{"text": "📡 Канал с сигналами", "url": CHANNEL_URL}],
        [{"text": "📈 Открыть платформу", "url": SITE_URL}],
    ]}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={
                "chat_id": chat_id, "text": text,
                "parse_mode": "HTML", "reply_markup": keyboard,
            })
    except Exception as e:
        print(f"[telegram_bot] Ошибка отправки приветствия: {e}")


async def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML"
            })
    except Exception as e:
        print(f"[Telegram] Ошибка отправки: {e}")

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
    conf  = round((score / 20) * 100)
    conf_emoji = "🔥" if conf >= 80 else "⚡" if conf >= 60 else "⚠️"

    text = (
        f"{emoji} <b>NWICKI SIGNAL — {side}</b>\n"
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
    """Сигнал от трейдера (ручной ввод в админке) или внешнего источника
    (вебхук TradingView) — без V8 score/confidence, это чужая сделка, не наш скан."""
    sym   = signal.get("symbol", "")
    side  = signal.get("signal", "")
    entry = signal.get("entry", 0)
    tp1   = signal.get("tp1", 0)
    tp2   = signal.get("tp2", 0)
    tp3   = signal.get("tp3", 0)
    stop  = signal.get("stop", 0)

    emoji = "🟢" if side == "LONG" else "🔴"
    text = (
        f"{emoji} <b>NWICKI SIGNAL — {side}</b>\n"
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
    }

    text = (
        f"{emoji} <b>NWICKI — Сделка закрыта</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{sym}</b> · {side}\n"
        f"📋 Результат: <b>{result_labels.get(result, result)}</b>\n"
        f"💵 PnL: <b>{pnl_str}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<i>NWICKI Crypto Scanner</i>"
    )

    await send_telegram(text)

async def notify_market_phase(old_phase: str, new_phase: str, details: dict):
    """Смена фазы рынка (информационный, редкий и ценный сигнал)."""
    labels = {'UPTREND': 'АПТРЕНД 📈', 'DOWNTREND': 'ДАУНТРЕНД 📉', 'SIDEWAYS': 'БОКОВИК ↔️'}
    emoji = {'UPTREND': '🟢', 'DOWNTREND': '🔴', 'SIDEWAYS': '🟡'}.get(new_phase, '🔵')
    text = (
        f"{emoji} <b>NWICKI — Смена фазы рынка</b>\n"
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
    """Вход/выход Trend-Following по монете (редкие позиционные сделки)."""
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
        f"{emoji} <b>NWICKI — Итоги дня</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 Сделок: <b>{total}</b>\n"
        f"🎯 Винрейт: <b>{winrate}%</b>\n"
        f"💵 PnL: <b>{pnl_str}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"TP1: {today.get('tp1', 0)} | "
        f"TP2+: {today.get('tp2_plus', 0)} | "
        f"Стоп: {today.get('stops', 0)} | "
        f"Б/У: {today.get('breakeven', 0)}\n"
        f"<i>NWICKI Crypto Scanner</i>"
    )

    await send_telegram(text)
