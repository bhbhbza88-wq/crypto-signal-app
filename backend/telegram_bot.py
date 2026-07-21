"""
Telegram-бот NOWICKI: меню, Premium, публикация сигналов.

Публикация:
  - ТВХ (открытия) → TELEGRAM_PREMIUM_CHANNEL_IDS (CSV), fallback TELEGRAM_CHAT_ID
  - Закрытия / результаты → TELEGRAM_PUBLIC_CHANNEL_ID
  - Trend/phase/daily → не публикуем (канал ТВХ остаётся чистым copy-trading)

Env:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID              — legacy fallback для premium channels
  TELEGRAM_PREMIUM_CHANNEL_IDS  — CSV chat_id каналов с ТВХ
  TELEGRAM_PREMIUM_CHAT_ID      — чат (invite при grant; автопосты ТВХ по умолчанию выкл)
  TELEGRAM_PUBLIC_CHANNEL_ID    — публичный канал результатов
  TELEGRAM_PUBLIC_CHANNEL_URL   — https://t.me/... для кнопок/бота
  TELEGRAM_ADMIN_IDS            — CSV telegram user id админов (/grant)
  PUBLIC_CHANNEL_MAX_LOSS_PCT   — макс. |PnL%| минуса для публикации в публичный канал (default 3.0)
  CRYPTO_PAY_ADDRESS / NETWORK / AMOUNT — ручной USDT (fallback)
  CRYPTO_PAY_API_TOKEN                  — токен Crypto Pay (@CryptoBot) для автооплаты
  CRYPTO_PAY_ASSET / CRYPTO_PAY_DAYS    — монета (USDT) и срок Premium после оплаты
"""
from __future__ import annotations

import os
import hashlib
import json as _json
import re

import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TELEGRAM_PUBLIC_CHANNEL_ID = os.getenv("TELEGRAM_PUBLIC_CHANNEL_ID", "").strip() or "@papayaqq"
TELEGRAM_PREMIUM_CHAT_ID = os.getenv("TELEGRAM_PREMIUM_CHAT_ID", "").strip()
TELEGRAM_PUBLIC_CHANNEL_URL = (
    os.getenv("TELEGRAM_PUBLIC_CHANNEL_URL", "").strip()
    or "https://t.me/papayaqq"
)
RESULTS_URL = TELEGRAM_PUBLIC_CHANNEL_URL
BOT_URL = "https://telegram.me/trading4325_bot"
SITE_URL = "https://nowicki.trade"
SUPPORT_USER = "Kupyansk_2"
SUPPORT_URL = f"https://telegram.me/{SUPPORT_USER}"

CRYPTO_PAY_ADDRESS = os.getenv("CRYPTO_PAY_ADDRESS", "").strip()
CRYPTO_PAY_NETWORK = os.getenv("CRYPTO_PAY_NETWORK", "USDT TRC20").strip() or "USDT TRC20"
CRYPTO_PAY_AMOUNT = os.getenv("CRYPTO_PAY_AMOUNT", "29").strip() or "29"

WEBHOOK_SECRET = (
    os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    or (hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).hexdigest()[:32] if TELEGRAM_BOT_TOKEN else "")
)
HR = "────────────"

# Ожидание email после «Я оплатил»: telegram_chat_id -> True
_awaiting_email: dict[int, bool] = {}


def _parse_id_list(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def _admin_ids() -> set[int]:
    out = set()
    for p in _parse_id_list(os.getenv("TELEGRAM_ADMIN_IDS", "")):
        try:
            out.add(int(p))
        except ValueError:
            pass
    return out


def premium_channel_ids() -> list[str]:
    ids = _parse_id_list(os.getenv("TELEGRAM_PREMIUM_CHANNEL_IDS", ""))
    if ids:
        return ids
    if TELEGRAM_CHAT_ID:
        return [TELEGRAM_CHAT_ID]
    return []


def premium_invite_chat_ids() -> list[str]:
    """Куда выдаём invite после оплаты: каналы ТВХ + чат."""
    ids = list(premium_channel_ids())
    if TELEGRAM_PREMIUM_CHAT_ID and TELEGRAM_PREMIUM_CHAT_ID not in ids:
        ids.append(TELEGRAM_PREMIUM_CHAT_ID)
    return ids


def public_results_id() -> str | None:
    return TELEGRAM_PUBLIC_CHANNEL_ID or None


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
            {"command": "paid", "description": "Я оплатил Premium"},
            {"command": "grant", "description": "Админ: выдать Premium"},
            {"command": "help", "description": "Помощь"},
        ]
    })


async def send_message(chat_id: int | str, text: str, reply_markup: dict | None = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _api("sendMessage", payload)


async def _send_to(chat_id: str, text: str, reply_markup: dict | None = None):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _api("sendMessage", payload)


async def publish_signal_open(text: str, reply_markup: dict | None = None):
    """ТВХ — только в premium-каналы (чат без автопостов)."""
    targets = premium_channel_ids()
    if not targets:
        print("[telegram_bot] нет premium channel id — ТВХ не отправлен")
        return
    for cid in targets:
        await _send_to(cid, text, reply_markup)


async def publish_signal_closed(text: str, reply_markup: dict | None = None, photo_png: bytes | None = None):
    """Закрытия — только публичный канал результатов."""
    cid = public_results_id()
    if not cid:
        # Миграция: если public ещё не задан — не спамим premium-каналы закрытиями
        print("[telegram_bot] TELEGRAM_PUBLIC_CHANNEL_ID не задан — закрытие не опубликовано")
        return
    if photo_png:
        try:
            await _api("sendPhoto", {
                "chat_id": cid,
                "caption": text,
                "parse_mode": "HTML",
                "reply_markup": _json.dumps(reply_markup) if reply_markup else None,
            }, files={"photo": ("close.png", photo_png, "image/png")})
            return
        except Exception as e:
            print(f"[telegram_bot] profit_card send: {e}")
    await _send_to(cid, text, reply_markup)


# Обратная совместимость для старых вызовов
async def send_telegram(text: str, reply_markup: dict | None = None):
    await publish_signal_open(text, reply_markup)


def _dock():
    return {
        "keyboard": [
            [{"text": "💎 Premium"}, {"text": "✅ Я оплатил"}],
            [{"text": "📊 Результаты"}, {"text": "✍️ Поддержка"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def _menu_kb():
    return {"inline_keyboard": [
        [{"text": "💎 Оформить Premium", "callback_data": "premium"}],
        [{"text": "✅ Я оплатил", "callback_data": "paid"}],
        [
            {"text": "📊 Результаты", "url": RESULTS_URL},
            {"text": "🌐 Сайт", "url": SITE_URL},
        ],
        [{"text": f"✍️ @{SUPPORT_USER}", "url": SUPPORT_URL}],
    ]}


def _premium_kb(pay_url: str | None = None, pay_label: str = "💳 Оплатить"):
    rows = []
    if pay_url:
        rows.append([{"text": pay_label, "url": pay_url}])
    rows.append([{"text": "✅ Я оплатил вручную", "callback_data": "paid"}])
    rows.append([{"text": f"✍️ Написать @{SUPPORT_USER}", "url": SUPPORT_URL}])
    rows.append([
        {"text": "🌐 Тарифы", "url": f"{SITE_URL}/app/pricing"},
        {"text": "‹ Меню", "callback_data": "menu"},
    ])
    return {"inline_keyboard": rows}


def _results_cta():
    return {"inline_keyboard": [
        [
            {"text": "🌐 Сайт", "url": SITE_URL},
            {"text": "💎 Premium", "url": f"{BOT_URL}?start=premium"},
        ],
    ]}


def _channel_cta():
    """Кнопки под постами ТВХ (premium)."""
    return {"inline_keyboard": [
        [
            {"text": "🌐 Сайт", "url": SITE_URL},
            {"text": "🤖 Бот", "url": BOT_URL},
        ],
    ]}


def _bot_username() -> str:
    m = re.search(r"(?:telegram\.me|t\.me)/([\w]+)", BOT_URL)
    return m.group(1) if m else ""


def build_telegram_link_deeplink(token: str) -> str:
    username = _bot_username()
    return f"https://t.me/{username}?start=tglink_{token}" if username else BOT_URL


async def start_telegram_link(chat_id: int, token: str):
    """Пользователь пришёл по deep-link «Подключить Telegram» с сайта.
    Если Premium уже активен на сайте — сразу шлём invite-ссылки в закрытые
    ТВХ-каналы, без ручного /grant. Если премиума нет — просто привязываем
    аккаунт и предлагаем оформить Premium (когда оформит — каналы откроются
    сами при следующей выдаче, см. notify_telegram_id_premium_ready)."""
    import database as db
    import auth

    user_id = db.consume_auth_token(token, kind="tg_link")
    if not user_id:
        await send_message(
            chat_id,
            "Ссылка для привязки Telegram устарела или уже использована.\n"
            "Вернись на сайт (личный кабинет) и получи новую ссылку.",
        )
        await send_welcome(chat_id)
        return

    user = db.get_user_by_id(user_id)
    if not user:
        await send_welcome(chat_id)
        return

    db.set_user_telegram_id(user_id, chat_id)
    eff_tier = auth.effective_tier(user)
    if auth.tier_allows(eff_tier, "premium"):
        await send_message(
            chat_id,
            f"<b>✅ Telegram привязан к {user['email']}</b>\n{HR}\n"
            "У тебя уже есть Premium на сайте — вот доступ к каналам с ТВХ:",
        )
        await send_premium_invites_message(chat_id, user["email"], user.get("premium_until"))
    else:
        await send_message(
            chat_id,
            f"<b>Telegram привязан к {user['email']}</b>\n{HR}\n"
            "Premium на сайте пока не активен — как только оформишь, каналы с ТВХ "
            "откроются автоматически, без лишних действий.",
        )
        await send_premium(chat_id)


async def send_welcome(chat_id: int, start_payload: str = "", with_dock: bool = False):
    raw_payload = (start_payload or "").strip()
    if raw_payload.startswith("tglink_"):
        await start_telegram_link(chat_id, raw_payload[len("tglink_"):])
        return
    payload = raw_payload.lower()
    if payload in ("premium", "pay"):
        await send_premium(chat_id)
        return
    if payload == "paid":
        await ask_paid_email(chat_id)
        return
    text = (
        f"<b>◈ NOWICKI</b>\n"
        f"{HR}\n"
        "Сигналы с уровнями <b>entry · stop · TP</b>.\n\n"
        f"📊 Публичные <b>результаты</b> — в канале\n"
        f"🔐 <b>ТВХ</b> (входы) — в Premium-каналах после оплаты\n"
        f"{HR}\n"
        f"<a href=\"{RESULTS_URL}\">Смотреть результаты</a> · <a href=\"{SITE_URL}\">сайт</a>"
    )
    kb = _menu_kb()
    if with_dock:
        await send_message(chat_id, text, _dock())
        await send_message(chat_id, "Быстрые действия:", kb)
    else:
        await send_message(chat_id, text, kb)


async def send_premium(chat_id: int):
    import crypto_pay
    import heleket_pay

    pay_url = None
    auto_block = ""
    pay_label = "💳 Оплатить"

    import database as db
    user = db.get_user_by_telegram_id(chat_id)
    email = user["email"] if user else None

    if heleket_pay.is_configured():
        invoice = await heleket_pay.create_invoice_for_telegram(chat_id, period="month")
        if invoice:
            pay_url = invoice.get("url")
            amount = heleket_pay.plan_amount("month")
            currency = heleket_pay.HELEKET_CURRENCY
            pay_label = "💳 Оплатить (Heleket)"
            auto_block = (
                f"<b>1.</b> Нажми <b>«Оплатить (Heleket)»</b> ниже\n"
                f"Сумма: <b>${amount} {currency}</b> · крипта или карта\n"
                f"После оплаты Premium и invite в каналы придут сами.\n"
            )
            if not user:
                auto_block += (
                    "\n⚠️ Лучше сначала привяжи Telegram на сайте "
                    "(Pricing → Подключить Telegram), чтобы Premium сел на нужный аккаунт.\n"
                )
    elif crypto_pay.is_configured():
        invoice = await crypto_pay.create_invoice(telegram_id=chat_id, email=email)
        if invoice:
            pay_url = (
                invoice.get("bot_invoice_url")
                or invoice.get("pay_url")
                or invoice.get("mini_app_invoice_url")
            )
            pay_label = "💳 Оплатить в Crypto Bot"
            auto_block = (
                f"<b>1.</b> Нажми <b>«Оплатить в Crypto Bot»</b> ниже\n"
                f"Сумма: <b>{crypto_pay.CRYPTO_PAY_AMOUNT} {crypto_pay.CRYPTO_PAY_ASSET}</b>\n"
                f"После оплаты Premium и invite в каналы придут сами.\n"
            )
            if not user:
                auto_block += (
                    "\n⚠️ Лучше сначала привяжи Telegram на сайте "
                    "(Pricing → Подключить Telegram), чтобы Premium сел на нужный аккаунт.\n"
                )

    if CRYPTO_PAY_ADDRESS:
        manual = (
            f"<b>{'2' if pay_url else '1'}.</b> Или перевод вручную <b>${CRYPTO_PAY_AMOUNT}</b> USDT\n"
            f"Сеть: <b>{CRYPTO_PAY_NETWORK}</b>\n"
            f"<code>{CRYPTO_PAY_ADDRESS}</code>\n"
            f"Потом «Я оплатил вручную» + email с nowicki.trade"
        )
    elif not pay_url:
        manual = f"Для оплаты напиши <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a>"
    else:
        manual = f"Проблемы с оплатой? Напиши <a href=\"{SUPPORT_URL}\">@{SUPPORT_USER}</a>"

    pay = "\n".join(p for p in (auto_block, manual) if p)
    text = (
        f"<b>💎 Premium · ${CRYPTO_PAY_AMOUNT}/мес</b>\n"
        f"{HR}\n"
        "· доступ к каналам с ТВХ (входы)\n"
        "· чат Premium\n"
        "· полная история на сайте\n"
        "· AI-ассистент 50/день\n"
        f"{HR}\n"
        f"{pay}"
    )
    await send_message(chat_id, text, _premium_kb(pay_url, pay_label))


async def ask_paid_email(chat_id: int):
    _awaiting_email[chat_id] = True
    await send_message(
        chat_id,
        f"<b>Подтверждение оплаты</b>\n{HR}\n"
        "Пришли <b>email</b> аккаунта на nowicki.trade одним сообщением.\n"
        "Админ проверит перевод и пришлёт invite-ссылки в каналы ТВХ.",
    )


async def send_help(chat_id: int):
    text = (
        f"<b>Помощь</b>\n"
        f"{HR}\n"
        "/start — меню\n"
        "/premium — оплата\n"
        "/paid — я оплатил (указать email)\n"
        "/help — эта справка\n\n"
        f"Результаты: {RESULTS_URL}\n"
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


async def _notify_admins(text: str):
    for aid in _admin_ids():
        try:
            await send_message(aid, text)
        except Exception as e:
            print(f"[telegram_bot] notify admin {aid}: {e}")


async def create_premium_invites() -> list[tuple[str, str]]:
    """[(chat_id, invite_url), ...]"""
    links = []
    for cid in premium_invite_chat_ids():
        data = await _api("createChatInviteLink", {
            "chat_id": cid,
            "member_limit": 1,
            "name": "NOWICKI Premium",
        })
        if data and data.get("ok"):
            url = (data.get("result") or {}).get("invite_link")
            if url:
                links.append((cid, url))
            else:
                print(f"[telegram_bot] invite empty for {cid}: {data}")
        else:
            print(f"[telegram_bot] createChatInviteLink failed for {cid}: {data}")
    return links


async def send_premium_invites_message(telegram_id: int, email: str, until: str | None) -> int:
    """Шлёт человеку в личку invite-ссылки в Premium-каналы (ТВХ).
    Возвращает число созданных ссылок (0 — не удалось создать invite,
    сообщение с просьбой написать поддержку уйдёт всё равно)."""
    links = await create_premium_invites()
    until_str = until[:10] if until else "—"
    if links:
        lines = "\n".join(f"· <a href=\"{url}\">Открыть доступ {i+1}</a>" for i, (_, url) in enumerate(links))
        await send_message(
            telegram_id,
            f"<b>✅ Premium активирован</b>\n{HR}\n"
            f"Email: <code>{email}</code>\n"
            f"До: <code>{until_str}</code>\n"
            f"{HR}\n"
            f"Одноразовые ссылки (по 1 входу):\n{lines}\n\n"
            f"Сайт: {SITE_URL}/app/overview",
        )
    else:
        await send_message(
            telegram_id,
            f"<b>✅ Premium на сайте включён</b> ({email}), но invite-ссылки не создались.\n"
            f"Напиши @{SUPPORT_USER} — выдадим доступ вручную.",
        )
    return len(links)


async def grant_premium_access(email: str, notify_telegram_id: int | None = None, days: int = 30) -> str:
    """Ставит premium на сайте + шлёт invite-ссылки в TG."""
    import database as db

    email = (email or "").lower().strip()
    user = db.get_user_by_email(email)
    if not user:
        return f"Пользователь с email <code>{email}</code> не найден на сайте."

    until = db.grant_premium(user["id"], days=days)
    if notify_telegram_id:
        db.set_user_telegram_id(user["id"], notify_telegram_id)

    req = db.get_pending_premium_request(email=email)
    if req:
        db.resolve_premium_request(req["id"], "granted")
        if not notify_telegram_id:
            notify_telegram_id = req.get("telegram_id")

    n_links = 0
    if notify_telegram_id:
        n_links = await send_premium_invites_message(notify_telegram_id, email, until)
    return (
        f"OK: Premium → <code>{email}</code> до {until[:10]}. "
        f"Invites: {n_links}. TG notify: {notify_telegram_id or '—'}"
    )


async def notify_telegram_id_premium_ready(telegram_id: int, email: str, until: str | None) -> None:
    """Вызывается, когда Premium выдан НЕ через бота (напр. с сайта/админки),
    а у пользователя telegram_id уже привязан — шлём invite-ссылки сразу,
    без ручного /grant."""
    if not telegram_id:
        return
    try:
        await send_premium_invites_message(telegram_id, email, until)
    except Exception as e:
        print(f"[telegram_bot] notify_telegram_id_premium_ready: {e}")


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


async def _handle_paid_email(chat_id: int, email: str):
    import database as db

    email = email.lower().strip()
    if not _EMAIL_RE.match(email):
        await send_message(chat_id, "Это не похоже на email. Пришли адрес вида name@gmail.com")
        return
    user = db.get_user_by_email(email)
    if not user:
        await send_message(
            chat_id,
            f"Аккаунт <code>{email}</code> не найден на nowicki.trade.\n"
            f"Сначала зарегистрируйся на сайте, потом снова /paid.",
        )
        return
    db.set_user_telegram_id(user["id"], chat_id)
    db.add_premium_request(chat_id, email)
    _awaiting_email.pop(chat_id, None)
    await send_message(
        chat_id,
        f"Заявка принята для <code>{email}</code>.\n"
        f"Админ проверит оплату и пришлёт invite-ссылки.\n"
        f"Можно также написать @{SUPPORT_USER} со скрином.",
    )
    await _notify_admins(
        f"<b>💳 Заявка Premium</b>\n"
        f"TG: <code>{chat_id}</code>\n"
        f"Email: <code>{email}</code>\n"
        f"Выдать: <code>/grant {email}</code>"
    )


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
        elif data == "paid":
            await ask_paid_email(chat_id)
        elif data == "menu":
            await send_welcome(chat_id)
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = message.get("chat", {}).get("id")
    from_user = message.get("from") or {}
    user_id = from_user.get("id")
    text = str(message.get("text") or "").strip()
    if not chat_id or not text:
        return

    # Ответ email после «Я оплатил»
    if _awaiting_email.get(chat_id) and not text.startswith("/"):
        await _handle_paid_email(chat_id, text)
        return

    if text == "💎 Premium":
        await send_premium(chat_id)
        return
    if text in ("📊 Результаты", "📡 Канал"):
        await send_message(chat_id, f"📊 Публичные результаты:\n{RESULTS_URL}")
        return
    if text in ("✅ Я оплатил", "Я оплатил"):
        await ask_paid_email(chat_id)
        return
    if text == "✍️ Поддержка":
        await send_support(chat_id)
        return

    cmd, _, payload = text.partition(" ")
    cmd = cmd.split("@", 1)[0].lower()
    payload = payload.strip()

    if cmd == "/start":
        await send_welcome(chat_id, payload, with_dock=True)
    elif cmd in ("/premium", "/pay"):
        await send_premium(chat_id)
    elif cmd in ("/paid", "/paydone"):
        await ask_paid_email(chat_id)
    elif cmd == "/help":
        await send_help(chat_id)
    elif cmd == "/support":
        await send_support(chat_id)
    elif cmd == "/grant":
        if user_id not in _admin_ids():
            await send_message(chat_id, "Команда только для админов.")
            return
        email = payload.split()[0] if payload else ""
        if not email or "@" not in email:
            await send_message(chat_id, "Использование: <code>/grant email@example.com</code>")
            return
        import database as db
        req = db.get_pending_premium_request(email=email)
        notify_id = req["telegram_id"] if req else None
        result = await grant_premium_access(email, notify_telegram_id=notify_id)
        await send_message(chat_id, result)
    else:
        await send_welcome(chat_id)


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


def _exchange_label(signal: dict) -> str:
    """Где доступна монета: только Bybit / только Binance / обе."""
    from data_layer import listings_label
    listed = signal.get("listed_on")
    if not listed:
        listed = signal.get("exchange") or "bybit"
    return listings_label(listed)


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
    venues = _exchange_label(signal)

    text = (
        f"<b>◈ NOWICKI SIGNAL</b>\n"
        f"{HR}\n"
        f"{side_emoji}\n"
        f"<b>{sym}</b>{conf_line}\n"
        f"<i>доступно: {venues}</i>\n"
        f"{HR}\n"
        f"{_levels_block(entry, stop, tp1, tp2, tp3)}\n"
    )
    if reasons:
        clean = [r for r in reasons[:3] if r and "агрегированн" not in r.lower()
                 and "Aggregated" not in r and not str(r).startswith("Листинг:")]
        if clean:
            text += f"{HR}\n" + "\n".join(f"· {r}" for r in clean) + "\n"
    text += f"\n<a href=\"{SITE_URL}\">nowicki.trade</a>  ·  <i>не фин. совет</i>"
    await publish_signal_open(text, _channel_cta())


async def notify_manual_signal(signal: dict, source: str):
    sym = signal.get("symbol", "")
    side = signal.get("signal", "")
    entry = signal.get("entry", 0)
    tp1 = signal.get("tp1", 0)
    tp2 = signal.get("tp2", 0)
    tp3 = signal.get("tp3", 0)
    stop = signal.get("stop", 0)
    side_emoji = "🟢 LONG" if side == "LONG" else "🔴 SHORT"
    venues = _exchange_label(signal)

    text = (
        f"<b>◈ NOWICKI SIGNAL</b>\n"
        f"{HR}\n"
        f"{side_emoji}\n"
        f"<b>{sym}</b>\n"
        f"<i>доступно: {venues}</i>\n"
        f"{HR}\n"
        f"{_levels_block(entry, stop, tp1, tp2, tp3)}\n"
        f"\n<a href=\"{SITE_URL}\">nowicki.trade</a>  ·  <i>не фин. совет</i>"
    )
    await publish_signal_open(text, _channel_cta())



# Публичный канал результатов — витрина, а не полный журнал сделок: крупные
# минусы туда не публикуем (иначе выглядит как обычный слив, а не сигналка,
# за которую стоит платить). Профит и небольшой минус — публикуем, чуть
# приукрасив цифру (polish_pnl), как и остальную витрину.
PUBLIC_CHANNEL_MAX_LOSS_PCT = float(os.getenv("PUBLIC_CHANNEL_MAX_LOSS_PCT", "3.0") or "3.0")


async def notify_signal_closed(signal: dict, result: str, pnl: float):
    from display_polish import polish_pnl

    try:
        pnl = float(pnl)
    except (TypeError, ValueError):
        return
    if pnl < 0 and abs(pnl) > PUBLIC_CHANNEL_MAX_LOSS_PCT:
        print(f"[telegram_bot] закрытие {signal.get('symbol')} ({pnl:+.2f}%) — крупный минус, в канал не публикуем")
        return

    sym = signal.get("symbol", "")
    side = signal.get("signal", "")
    entry = signal.get("entry")
    exit_price = signal.get("exit")
    win = pnl > 0
    show = polish_pnl(pnl, decimals=2)
    if pnl == 0:
        emoji, title = "➖", "БЕЗУБЫТОК"
    elif win:
        emoji, title = "✅", "СДЕЛКА В ПЛЮС"
    else:
        emoji, title = "➖", "МИНИМАЛЬНЫЙ МИНУС"
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

    photo = None
    if entry is not None:
        try:
            from profit_card import render_profit_card
            photo = render_profit_card(
                symbol=sym, side=side or "LONG", entry=float(entry),
                pnl_pct=float(pnl), exit_price=float(exit_price) if exit_price is not None else None,
            )
        except Exception as e:
            print(f"[telegram_bot] profit_card: {e}")

    await publish_signal_closed(text, _results_cta(), photo_png=photo)


async def notify_market_phase(old_phase: str, new_phase: str, details: dict):
    # Не публикуем в ТВХ/results — шум для copy-trading
    print(f"[telegram_bot] phase {old_phase} → {new_phase} (skip publish)")


async def notify_trend_signal(symbol: str, action: str, price: float, pnl: float = None):
    print(f"[telegram_bot] trend {action} {symbol} (skip publish)")


async def send_daily_summary(stats: dict):
    from display_polish import polish_pnl, polish_winrate

    # Итоги дня — в публичный канал результатов, если настроен
    today = stats.get("today", {})
    total = today.get("total", 0)
    winrate = polish_winrate(today.get("winrate", 0))
    show = polish_pnl(today.get("total_pnl", 0), decimals=2)
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
    await publish_signal_closed(text, _results_cta())
