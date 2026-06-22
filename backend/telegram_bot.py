"""
Telegram уведомления для NWICKI
Добавь в Railway переменные окружения:
  TELEGRAM_BOT_TOKEN=твой_токен
  TELEGRAM_CHAT_ID=твой_chat_id
"""
import os
import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

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
