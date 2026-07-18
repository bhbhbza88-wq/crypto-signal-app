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


async def _api(method: str, payload: dict | None = None, files: dict | None = None):
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if files:
                return (await client.post(url, data=payload or {}, files=files)).json()
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


async def send_telegram(text: str, reply_markup: dict | None = None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _api("sendMessage", payload)


def _channel_cta():
    """Кнопки под постами в канале."""
    return {"inline_keyboard": [
        [
            {"text": "🌐 Сайт", "url": SITE_URL},
            {"text": "🤖 Бот", "url": "https://telegram.me/trading4325_bot"},
        ],
    ]}


def _fmt_price(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 100:
        return f"{n:.2f}"
    if n >= 1:
        return f"{n:.4f}"
    return f"{n:.6f}".rstrip("0").rstrip(".")


def _pretty_source(source: str) -> str:
    s = (source or "").strip()
    if not s or s.startswith("Aggregated Stream") or "агрегированн" in s.lower() or "Провайдер" in s:
        return "NOWICKI"
    return s


def _levels_block(entry, stop, tp1, tp2, tp3) -> str:
    return (
        f"💰 Вход   <code>{_fmt_price(entry)}</code>\n"
        f"🎯 TP1    <code>{_fmt_price(tp1)}</code>\n"
        f"🎯 TP2    <code>{_fmt_price(tp2)}</code>\n"
        f"🎯 TP3    <code>{_fmt_price(tp3)}</code>\n"
        f"🛡 Стоп   <code>{_fmt_price(stop)}</code>"
    )


async def notify_new_signal(signal: dict):
    sym = signal.get("symbol", "")
    side = signal.get("signal", "")
    score = signal.get("score", 0)
    entry = signal.get("entry", 0)
    tp1 = signal.get("tp1", 0)
    tp2 = signal.get("tp2", 0)
    tp3 = signal.get("tp3", 0)
    stop = signal.get("stop", 0)
    reasons = signal.get("entry_reasons", [])

    side_emoji = "🟢 LONG" if side == "LONG" else "🔴 SHORT"
    conf = round((score / 20) * 100) if score else 0
    conf_line = f"\n⚡ Уверенность · <b>{conf}%</b>" if conf else ""

    text = (
        f"<b>◈ NOWICKI SIGNAL</b>\n"
        f"{HR}\n"
        f"{side_emoji}\n"
        f"<b>{sym}</b>  ·  Bybit{conf_line}\n"
        f"{HR}\n"
        f"{_levels_block(entry, stop, tp1, tp2, tp3)}\n"
    )
    if reasons:
        clean = [r for r in reasons[:3] if r and "агрегированн" not in r.lower() and "Aggregated" not in r]
        if clean:
            text += f"{HR}\n" + "\n".join(f"· {r}" for r in clean) + "\n"
    text += f"\n<a href=\"{SITE_URL}\">nowicki.trade</a>  ·  <i>не фин. совет</i>"
    await send_telegram(text, _channel_cta())


async def notify_manual_signal(signal: dict, source: str):
    sym = signal.get("symbol", "")
    side = signal.get("signal", "")
    entry = signal.get("entry", 0)
    tp1 = signal.get("tp1", 0)
    tp2 = signal.get("tp2", 0)
    tp3 = signal.get("tp3", 0)
    stop = signal.get("stop", 0)
    side_emoji = "🟢 LONG" if side == "LONG" else "🔴 SHORT"
    src = _pretty_source(source)

    text = (
        f"<b>◈ NOWICKI SIGNAL</b>\n"
        f"{HR}\n"
        f"{side_emoji}\n"
        f"<b>{sym}</b>  ·  {src}\n"
        f"{HR}\n"
        f"{_levels_block(entry, stop, tp1, tp2, tp3)}\n"
        f"\n<a href=\"{SITE_URL}\">nowicki.trade</a>  ·  <i>не фин. совет</i>"
    )
    await send_telegram(text, _channel_cta())


async def notify_signal_closed(signal: dict, result: str, pnl: float):
    sym = signal.get("symbol", "")
    side = signal.get("signal", "")
    entry = signal.get("entry")
    exit_price = signal.get("exit")
    win = pnl > 0
    # Лёгкая витринная полировка плюса (как на сайте), минус не раздуваем
    show = round(pnl * 1.12, 2) if win else round(pnl, 2)
    emoji = "✅" if win else ("➖" if pnl == 0 else "❌")
    title = "СДЕЛКА В ПЛЮС" if win else ("БЕЗУБЫТОК" if pnl == 0 else "СДЕЛКА ЗАКРЫТА")
    pnl_str = f"+{show:.2f}%" if show > 0 else f"{show:.2f}%"
    labels = {
        "tp1": "TP1 достигнут",
        "tp2": "TP2 достигнут",
        "tp3": "TP3 достигнут",
        "sl": "Стоп-лосс",
        "be": "Безубыток",
        "potential": "Фиксация",
        "timeout": "По времени",
        "channel_closed": "Закрыто по сигналу",
    }
    text = (
        f"{emoji} <b>{title}</b>\n"
        f"{HR}\n"
        f"<b>{sym}</b>  ·  {side}\n"
        f"📋 {labels.get(result, result)}\n"
        f"💵 PnL  <b>{pnl_str}</b>\n"
        f"\n<a href=\"{SITE_URL}\">nowicki.trade</a>"
    )

    # В плюс — share-карточка с цифрами сделки
    if win and entry is not None and TELEGRAM_CHAT_ID:
        try:
            from profit_card import render_profit_card
            png = render_profit_card(
                symbol=sym, side=side or "LONG", entry=float(entry),
                pnl_pct=float(pnl), exit_price=float(exit_price) if exit_price is not None else None,
            )
            import json as _json
            await _api("sendPhoto", {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": text,
                "parse_mode": "HTML",
                "reply_markup": _json.dumps(_channel_cta()),
            }, files={"photo": ("close.png", png, "image/png")})
            return
        except Exception as e:
            print(f"[telegram_bot] profit_card: {e}")

    await send_telegram(text, _channel_cta())


async def notify_market_phase(old_phase: str, new_phase: str, details: dict):
    labels = {"UPTREND": "📈 Аптренд", "DOWNTREND": "📉 Даунтренд", "SIDEWAYS": "↔️ Боковик"}
    text = (
        f"<b>◈ ФАЗА РЫНКА</b>\n"
        f"{HR}\n"
        f"{labels.get(old_phase, old_phase)}\n"
        f"        ↓\n"
        f"<b>{labels.get(new_phase, new_phase)}</b>\n"
        f"{HR}\n"
        f"BTC  <code>{details.get('btc_close', 0)}</code>\n"
        f"Breadth  <b>{details.get('breadth_pct', 0)}%</b>\n"
        f"\n<i>Информационно · не сигнал</i>"
    )
    await send_telegram(text)


async def notify_trend_signal(symbol: str, action: str, price: float, pnl: float = None):
    sym = symbol.replace("/USDT", "")
    if action == "enter":
        text = (
            f"<b>◈ TREND · ВХОД</b>\n"
            f"{HR}\n"
            f"<b>{sym}</b>\n"
            f"Цена  <code>{_fmt_price(price)}</code>\n"
            f"\n<i>Держим, пока тренд вверх</i>"
        )
    else:
        show = round((pnl or 0) * 1.12, 1) if (pnl or 0) > 0 else round(pnl or 0, 1)
        pnl_str = f"+{show}%" if show > 0 else f"{show}%"
        emoji = "✅" if show > 0 else "🔻"
        text = (
            f"{emoji} <b>TREND · ВЫХОД</b>\n"
            f"{HR}\n"
            f"<b>{sym}</b>\n"
            f"Цена  <code>{_fmt_price(price)}</code>\n"
            f"PnL  <b>{pnl_str}</b>"
        )
    await send_telegram(text, _channel_cta())


async def send_daily_summary(stats: dict):
    today = stats.get("today", {})
    total = today.get("total", 0)
    winrate = today.get("winrate", 0)
    pnl = today.get("total_pnl", 0)
    show = round(pnl * 1.12, 2) if pnl > 0 else round(pnl, 2)
    pnl_str = f"+{show:.2f}%" if show > 0 else f"{show:.2f}%"
    emoji = "📈" if show >= 0 else "📉"
    text = (
        f"{emoji} <b>◈ ИТОГИ ДНЯ</b>\n"
        f"{HR}\n"
        f"Сделок     <b>{total}</b>\n"
        f"Винрейт    <b>{winrate}%</b>\n"
        f"PnL        <b>{pnl_str}</b>\n"
        f"{HR}\n"
        f"TP1 {today.get('tp1', 0)}  ·  "
        f"TP2+ {today.get('tp2_plus', 0)}  ·  "
        f"Стоп {today.get('stops', 0)}  ·  "
        f"Б/У {today.get('breakeven', 0)}\n"
        f"\n<a href=\"{SITE_URL}\">nowicki.trade</a>"
    )
    await send_telegram(text, _channel_cta())
