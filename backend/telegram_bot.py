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
SUPPORT_USER = "Kupyansk_2"
SUPPORT_URL = f"https://telegram.me/{SUPPORT_USER}"

CRYPTO_PAY_ADDRESS = os.getenv("CRYPTO_PAY_ADDRESS", "").strip()
CRYPTO_PAY_NETWORK = os.getenv("CRYPTO_PAY_NETWORK", "USDT TRC20").strip() or "USDT TRC20"
CRYPTO_PAY_AMOUNT = os.getenv("CRYPTO_PAY_AMOUNT", "29").strip() or "29"

WEBHOOK_SECRET = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).hexdigest()[:32] if TELEGRAM_BOT_TOKEN else ""

# Визуальный ритм сообщений
HR = "────────────────"
BRAND = "NOWICKI"


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
    """Вебхук + команды + описание бота + кнопка меню «Открыть сайт»."""
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

    await _api("setMyCommands", {
        "commands": [
            {"command": "start", "description": "Главное меню"},
            {"command": "premium", "description": "Premium · оплата USDT"},
            {"command": "status", "description": "Живая статистика"},
            {"command": "support", "description": "Связь после оплаты"},
            {"command": "help", "description": "Справка"},
        ]
    })
    await _api("setMyShortDescription", {
        "short_description": "AI-сканер крипты · сигналы с TP/SL · Premium за USDT"
    })
    await _api("setMyDescription", {
        "description": (
            "NOWICKI — платформа крипто-сигналов.\n\n"
            "• Живая лента с entry / stop / TP\n"
            "• Реальный трек-рекорд на Bybit\n"
            "• Premium: полная история + AI\n\n"
            f"Сайт: {SITE_URL}\n"
            f"После оплаты: @{SUPPORT_USER}"
        )
    })
    # Кнопка слева от поля ввода — открывает сайт как Web App / browser
    await _api("setChatMenuButton", {
        "menu_button": {
            "type": "web_app",
            "text": "Открыть NOWICKI",
            "web_app": {"url": SITE_URL},
        }
    })
    print("[telegram_bot] Меню и описание бота обновлены")


async def _render(chat_id: int, text: str, reply_markup: dict | None = None,
                  message_id: int | None = None):
    """Одно «окно» бота: edit существующего сообщения или новое."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if message_id:
        payload["message_id"] = message_id
        res = await _api("editMessageText", payload)
        if res and res.get("ok"):
            return
        desc = (res or {}).get("description") or ""
        if "message is not modified" in desc:
            return
    await _api("sendMessage", payload)


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None):
    await _render(chat_id, text, reply_markup)


def _nav(active: str = "home"):
    """Единая сетка — как нижняя навигация мини-приложения."""
    def mark(key, label):
        return f"· {label} ·" if key == active else label

    return {"inline_keyboard": [
        [
            {"text": mark("premium", "💎 Premium"), "callback_data": "premium"},
            {"text": mark("status", "📊 Статус"), "callback_data": "status"},
        ],
        [
            {"text": mark("support", "✍️ Поддержка"), "callback_data": "support"},
            {"text": mark("help", "📖 Справка"), "callback_data": "help"},
        ],
        [
            {"text": "📡 Канал", "url": CHANNEL_URL},
            {"text": "🌐 Сайт", "url": SITE_URL},
        ],
    ]}


def _kb_premium():
    return {"inline_keyboard": [
        [{"text": f"✍️ Написать @{SUPPORT_USER}", "url": SUPPORT_URL}],
        [
            {"text": "📋 Тарифы", "url": f"{SITE_URL}/app/pricing"},
            {"text": "📡 Канал", "url": CHANNEL_URL},
        ],
        [{"text": "‹ Назад в меню", "callback_data": "menu"}],
    ]}


def _kb_support():
    return {"inline_keyboard": [
        [{"text": f"Открыть чат @{SUPPORT_USER}", "url": SUPPORT_URL}],
        [
            {"text": "💎 К оплате", "callback_data": "premium"},
            {"text": "‹ Меню", "callback_data": "menu"},
        ],
    ]}


def _reply_dock():
    return {
        "keyboard": [
            [{"text": "🏠 Меню"}, {"text": "💎 Premium"}, {"text": "📊 Статус"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Команда или кнопка меню…",
    }


def _snapshot():
    """Живые цифры для статуса / главного экрана."""
    try:
        import database as db
        history = db.load_history(limit=2000) or []
        if not history:
            return None
        total = len(history)
        wins = sum(1 for t in history if float(t.get("pnl") or 0) > 0)
        pnl = sum(float(t.get("pnl") or 0) for t in history)
        wr = round(wins / total * 100, 1) if total else 0
        avg = round(pnl / total, 1) if total else 0
        return {"total": total, "winrate": wr, "avg_pnl": avg, "total_pnl": round(pnl, 1)}
    except Exception as e:
        print(f"[telegram_bot] snapshot: {e}")
        return None


def _fmt_pnl(n: float) -> str:
    return f"+{n}%" if n > 0 else f"{n}%"


async def screen_home(chat_id: int, message_id: int | None = None, with_dock: bool = False):
    snap = _snapshot()
    stats_line = ""
    if snap:
        stats_line = (
            f"\n{HR}\n"
            f"📈 Винрейт  <b>{snap['winrate']}%</b>\n"
            f"📦 Сделок   <b>{snap['total']}</b>\n"
            f"💵 Ср. PnL  <b>{_fmt_pnl(snap['avg_pnl'])}</b>\n"
        )
    text = (
        f"<b>◈  {BRAND}</b>\n"
        f"<i>AI market scanner</i>\n"
        f"{HR}\n"
        "Ищем точки входа с чёткими уровнями\n"
        "<b>entry · stop · take-profit</b>\n"
        f"{stats_line}"
        f"{HR}\n"
        "Выбери раздел ниже — или открой сайт\n"
        "кнопкой меню слева от поля ввода."
    )
    await _render(chat_id, text, _nav("home"), message_id)
    if with_dock and not message_id:
        await _api("sendMessage", {
            "chat_id": chat_id,
            "text": "▾  меню закреплено внизу",
            "reply_markup": _reply_dock(),
        })


async def screen_help(chat_id: int, message_id: int | None = None):
    text = (
        f"<b>📖  Справка</b>\n"
        f"{HR}\n"
        "<b>Навигация</b>\n"
        "· кнопки под сообщением\n"
        "· док внизу чата\n"
        "· «Открыть NOWICKI» у поля ввода\n\n"
        "<b>Команды</b>\n"
        "/start — меню\n"
        "/premium — оплата\n"
        "/status — статистика\n"
        "/support — после оплаты\n\n"
        "<b>Premium</b>\n"
        f"USDT → затем сообщение @{SUPPORT_USER}\n"
        f"{HR}\n"
        f"<a href=\"{SITE_URL}\">nowicki.trade</a>  ·  "
        f"<a href=\"{CHANNEL_URL}\">канал</a>"
    )
    await _render(chat_id, text, _nav("help"), message_id)


async def screen_premium(chat_id: int, message_id: int | None = None):
    if CRYPTO_PAY_ADDRESS:
        steps = (
            f"<b>Шаг 1 · Оплата</b>\n"
            f"Сумма  <b>${CRYPTO_PAY_AMOUNT}</b> USDT\n"
            f"Сеть   <b>{CRYPTO_PAY_NETWORK}</b>\n\n"
            f"Адрес (тапни — скопируется):\n"
            f"<code>{CRYPTO_PAY_ADDRESS}</code>\n\n"
            f"<b>Шаг 2 · Активация</b>\n"
            f"Напиши <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a> и пришли:\n"
            f"  1. email с nowicki.trade\n"
            f"  2. скрин или tx hash\n\n"
            f"<i>Обычно активируем в течение дня.</i>"
        )
    else:
        steps = (
            f"Адрес скоро появится.\n"
            f"Пока напиши <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a>."
        )
    text = (
        f"<b>💎  Premium</b>   <code>${CRYPTO_PAY_AMOUNT}/мес</code>\n"
        f"{HR}\n"
        "▸ полная история и PnL по дням\n"
        "▸ AI-ассистент · 50 запросов/день\n"
        "▸ приоритет к новым фичам\n"
        f"{HR}\n"
        f"{steps}\n"
        f"{HR}\n"
        "<i>⚠️ Не является финансовым советом</i>"
    )
    await _render(chat_id, text, _kb_premium(), message_id)


async def screen_status(chat_id: int, message_id: int | None = None):
    snap = _snapshot()
    if snap:
        body = (
            f"🟢  Сканер <b>онлайн</b>\n\n"
            f"Винрейт     <b>{snap['winrate']}%</b>\n"
            f"Сделок      <b>{snap['total']}</b>\n"
            f"Ср. PnL     <b>{_fmt_pnl(snap['avg_pnl'])}</b>\n"
            f"Сумм. PnL   <b>{_fmt_pnl(snap['total_pnl'])}</b>"
        )
    else:
        body = (
            "🟢  Сканер <b>онлайн</b>\n\n"
            "Статистика подгружается…\n"
            "Актуальные цифры — на сайте."
        )
    text = (
        f"<b>📊  Статус</b>\n"
        f"{HR}\n"
        f"{body}\n"
        f"{HR}\n"
        f"🌐  <a href=\"{SITE_URL}\">nowicki.trade</a>\n"
        f"📡  <a href=\"{CHANNEL_URL}\">канал сигналов</a>\n"
        f"✍️  <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a>"
    )
    await _render(chat_id, text, _nav("status"), message_id)


async def screen_support(chat_id: int, message_id: int | None = None):
    text = (
        f"<b>✍️  Поддержка</b>\n"
        f"{HR}\n"
        "После оплаты или по любому вопросу —\n"
        f"пиши лично  <a href=\"{SUPPORT_URL}\"><b>@{SUPPORT_USER}</b></a>\n\n"
        "В сообщении укажи:\n"
        "· email аккаунта на сайте\n"
        "· скрин / hash перевода (если оплата)\n"
        f"{HR}\n"
        "<i>Отвечаем в порядке очереди, обычно быстро.</i>"
    )
    await _render(chat_id, text, _kb_support(), message_id)


async def send_welcome(chat_id: int, start_payload: str = ""):
    if start_payload.strip().lower() in ("premium", "pay", "vip"):
        await screen_premium(chat_id)
        return
    await screen_home(chat_id, with_dock=True)


async def send_help(chat_id: int):
    await screen_help(chat_id)


async def send_premium(chat_id: int):
    await screen_premium(chat_id)


async def send_status(chat_id: int):
    await screen_status(chat_id)


async def handle_update(update: dict):
    """Callbacks правят одно сообщение — навигация как в приложении."""
    cb = update.get("callback_query")
    if cb:
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        message_id = cb.get("message", {}).get("message_id")
        data = (cb.get("data") or "").strip().lower()
        await _api("answerCallbackQuery", {"callback_query_id": cb.get("id")})
        if not chat_id:
            return
        screens = {
            "premium": screen_premium,
            "pay": screen_premium,
            "status": screen_status,
            "help": screen_help,
            "support": screen_support,
            "menu": screen_home,
            "home": screen_home,
        }
        fn = screens.get(data)
        if fn:
            await fn(chat_id, message_id)
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = message.get("chat", {}).get("id")
    text = str(message.get("text") or "").strip()
    if not chat_id or not text:
        return

    dock = {
        "🏠 Меню": lambda: screen_home(chat_id),
        "💎 Premium": lambda: screen_premium(chat_id),
        "📊 Статус": lambda: screen_status(chat_id),
        "📖 Помощь": lambda: screen_help(chat_id),
        "✍️ Поддержка": lambda: screen_support(chat_id),
    }
    if text in dock:
        await dock[text]()
        return

    low = text.lower()
    if low in ("меню", "menu"):
        await screen_home(chat_id); return
    if low in ("premium", "оплатить", "vip"):
        await screen_premium(chat_id); return
    if low in ("status", "статус", "stats"):
        await screen_status(chat_id); return
    if low in ("help", "помощь", "справка"):
        await screen_help(chat_id); return
    if low in ("support", "поддержка"):
        await screen_support(chat_id); return

    cmd, _, payload = text.partition(" ")
    cmd = cmd.split("@", 1)[0].lower()

    if cmd == "/start":
        await send_welcome(chat_id, payload)
    elif cmd == "/help":
        await screen_help(chat_id)
    elif cmd == "/menu":
        await screen_home(chat_id)
    elif cmd in ("/premium", "/pay"):
        await screen_premium(chat_id)
    elif cmd in ("/status", "/stats"):
        await screen_status(chat_id)
    elif cmd in ("/support", "/pay_support"):
        await screen_support(chat_id)
    else:
        await _render(
            chat_id,
            f"<b>◈  {BRAND}</b>\n"
            f"{HR}\n"
            "Не распознал запрос.\n"
            "Нажми кнопку ниже или /start\n\n"
            f"После оплаты — <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a>",
            _nav("home"),
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
        f"{HR}\n"
        f"📊 <b>{sym}</b> · Bybit\n"
        f"{conf_emoji} Уверенность: <b>{conf}%</b> (Score {score}/20)\n"
        f"📈 Режим рынка: <b>{regime}</b>\n"
        f"{HR}\n"
        f"💰 Вход:  <code>{entry:.4f}</code>\n"
        f"🎯 TP1:   <code>{tp1:.4f}</code>\n"
        f"🎯 TP2:   <code>{tp2:.4f}</code>\n"
        f"🎯 TP3:   <code>{tp3:.4f}</code>\n"
        f"🛑 Стоп:  <code>{stop:.4f}</code>\n"
    )

    if reasons:
        text += f"{HR}\n"
        text += "📋 <b>Причины входа:</b>\n"
        for r in reasons[:4]:
            text += f"• {r}\n"

    text += "\n⚠️ <i>Не является финансовым советом</i>"
    await send_telegram(text)


async def notify_manual_signal(signal: dict, source: str):
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
        f"{HR}\n"
        f"📊 <b>{sym}</b> · Bybit\n"
        f"✍️ Автор: <b>{source}</b>\n"
        f"{HR}\n"
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
        f"{HR}\n"
        f"📊 <b>{sym}</b> · {side}\n"
        f"📋 Результат: <b>{result_labels.get(result, result)}</b>\n"
        f"💵 PnL: <b>{pnl_str}</b>\n"
        f"{HR}\n"
        f"<i>{BRAND} Crypto Scanner</i>"
    )
    await send_telegram(text)


async def notify_market_phase(old_phase: str, new_phase: str, details: dict):
    labels = {'UPTREND': 'АПТРЕНД 📈', 'DOWNTREND': 'ДАУНТРЕНД 📉', 'SIDEWAYS': 'БОКОВИК ↔️'}
    emoji = {'UPTREND': '🟢', 'DOWNTREND': '🔴', 'SIDEWAYS': '🟡'}.get(new_phase, '🔵')
    text = (
        f"{emoji} <b>NOWICKI — Смена фазы рынка</b>\n"
        f"{HR}\n"
        f"Было: <b>{labels.get(old_phase, old_phase)}</b>\n"
        f"Стало: <b>{labels.get(new_phase, new_phase)}</b>\n"
        f"{HR}\n"
        f"📊 BTC: <code>{details.get('btc_close', 0)}</code>\n"
        f"🌡 Монет в аптренде: <b>{details.get('breadth_pct', 0)}%</b>\n"
        f"⚡ Моментум 60д: <b>{details.get('momentum_60d_pct', 0)}%</b>\n"
        f"✅ Risk-on: <b>{details.get('risk_on_score', 0)}/4</b>\n"
        f"{HR}\n"
        f"<i>Информационно — не торговый сигнал</i>"
    )
    await send_telegram(text)


async def notify_trend_signal(symbol: str, action: str, price: float, pnl: float = None):
    sym = symbol.replace('/USDT', '')
    if action == 'enter':
        text = (
            f"📈 <b>Trend-Following — ВХОД</b>\n"
            f"{HR}\n"
            f"📊 <b>{sym}</b> вошёл в восходящий тренд (EMA50&gt;EMA200)\n"
            f"💰 Цена: <code>{price:.4f}</code>\n"
            f"<i>Держим, пока тренд вверх. Выход — пересечение EMA вниз.</i>"
        )
    else:
        pnl_str = f"+{pnl:.1f}%" if (pnl or 0) > 0 else f"{pnl:.1f}%"
        emoji = "✅" if (pnl or 0) > 0 else "🔻"
        text = (
            f"{emoji} <b>Trend-Following — ВЫХОД</b>\n"
            f"{HR}\n"
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
        f"{HR}\n"
        f"📊 Сделок: <b>{total}</b>\n"
        f"🎯 Винрейт: <b>{winrate}%</b>\n"
        f"💵 PnL: <b>{pnl_str}</b>\n"
        f"{HR}\n"
        f"TP1: {today.get('tp1', 0)} | "
        f"TP2+: {today.get('tp2_plus', 0)} | "
        f"Стоп: {today.get('stops', 0)} | "
        f"Б/У: {today.get('breakeven', 0)}\n"
        f"<i>{BRAND} Crypto Scanner</i>"
    )
    await send_telegram(text)
