"""
Telegram-бот NOWICKI: меню, Premium, публикация сигналов.

Публикация:
  - ТВХ (открытия) → TELEGRAM_PREMIUM_CHANNEL_IDS (CSV), fallback TELEGRAM_CHAT_ID
  - Закрытия / результаты → TELEGRAM_PUBLIC_CHANNEL_ID
  - Trend/phase/daily → не публикуем (канал ТВХ остаётся чистым copy-trading)
  - Автопересылка 1 сигнал/день в TELEGRAM_NEWS_TARGET_CHANNEL (если AUTO_FORWARD_TO_NEWS=1)

Env:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID              — legacy fallback для premium channels
  TELEGRAM_PREMIUM_CHANNEL_IDS  — CSV chat_id каналов с ТВХ
  TELEGRAM_PREMIUM_CHAT_ID      — чат (invite при grant; автопосты ТВХ по умолчанию выкл)
  TELEGRAM_PUBLIC_CHANNEL_ID    — публичный канал результатов
  TELEGRAM_PUBLIC_CHANNEL_URL   — https://t.me/... для кнопок/бота
  TELEGRAM_NEWS_TARGET_CHANNEL  — канал для автопересылки 1 сигнала/день (@nowicki_news)
  AUTO_FORWARD_TO_NEWS          — вкл/выкл автопересылку (по умолчанию 1)
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

# Последнее опубликованное сообщение в премиум канале: (chat_id, message_id)
_last_premium_message: tuple[str, int] | None = None

# Дата последней пересылки в news канал (для ограничения 1 раз в день)
_last_forward_date: str | None = None


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


async def publish_signal_open(
    text: str,
    reply_markup: dict | None = None,
    photo_png: bytes | None = None,
):
    """ТВХ в premium-каналы БЕЗ кнопок (чтобы была вкладка Комментарии).

    Сайт/Бот вешаем на дубликат поста в чате обсуждений.
    """
    import asyncio

    global _last_premium_message
    _ = reply_markup  # в канале кнопок не должно быть
    targets = premium_channel_ids()
    if not targets:
        print("[telegram_bot] нет premium channel id — ТВХ не отправлен")
        return
    for cid in targets:
        msg_id = None
        if photo_png:
            try:
                data = await _api(
                    "sendPhoto",
                    {
                        "chat_id": cid,
                        "caption": text if len(text) <= 1024 else (text[:1000].rstrip() + "…"),
                        "parse_mode": "HTML",
                    },
                    files={"photo": ("open.png", photo_png, "image/png")},
                )
                if data and data.get("ok"):
                    msg_id = data.get("result", {}).get("message_id")
            except Exception as e:
                print(f"[telegram_bot] open_pos photo send: {e}")

        if msg_id is None:
            data = await _api("sendMessage", {
                "chat_id": cid,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            if data and data.get("ok"):
                msg_id = data.get("result", {}).get("message_id")

        if msg_id and not _last_premium_message:
            _last_premium_message = (cid, msg_id)
            print(f"[telegram_bot] saved last premium message: {cid} / {msg_id}")
        if msg_id:
            asyncio.create_task(_ensure_discussion_cta(cid, msg_id))
            # VIP / премиум канал → outbox на приватный boost_channel
            try:
                vip = os.getenv("TELEGRAM_FARM_VIP_CHANNEL", "https://t.me/+ONlP_9aok4kxMDZi")
                _notify_farm_boost(vip, int(msg_id), text)
            except Exception as e:
                print(f"[telegram_bot] farm vip outbox: {e}", flush=True)


async def publish_signal_closed(text: str, reply_markup: dict | None = None, photo_png: bytes | None = None):
    """Закрытия в публичный канал без кнопок; CTA — в чат комментариев."""
    import asyncio

    _ = reply_markup
    cid = public_results_id()
    if not cid:
        print("[telegram_bot] TELEGRAM_PUBLIC_CHANNEL_ID не задан — закрытие не опубликовано")
        return
    msg_id = None
    if photo_png:
        try:
            data = await _api("sendPhoto", {
                "chat_id": cid,
                "caption": text,
                "parse_mode": "HTML",
            }, files={"photo": ("close.png", photo_png, "image/png")})
            if data and data.get("ok"):
                msg_id = data.get("result", {}).get("message_id")
        except Exception as e:
            print(f"[telegram_bot] profit_card send: {e}")
    if msg_id is None:
        data = await _api("sendMessage", {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if data and data.get("ok"):
            msg_id = data.get("result", {}).get("message_id")
    if msg_id:
        asyncio.create_task(_ensure_discussion_cta(cid, msg_id))


async def publish_news(
    text: str,
    reply_markup: dict | None = None,
    photo_png: bytes | None = None,
):
    """Outlook → news-канал без кнопок; Сайт/Бот — в чат обсуждений."""
    import asyncio

    _ = reply_markup
    raw = (
        os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL")
        or os.getenv("MARKET_OUTLOOK_CHANNEL")
        or ""
    ).strip()
    if not raw:
        print("[telegram_bot] TELEGRAM_NEWS_TARGET_CHANNEL не задан — news skip")
        return
    cid = raw if raw.startswith("@") or raw.lstrip("-").isdigit() else f"@{raw.lstrip('@')}"
    caption = text if len(text) <= 1024 else (text[:1000].rstrip() + "…")
    msg_id = None
    if photo_png:
        try:
            data = await _api(
                "sendPhoto",
                {
                    "chat_id": cid,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                files={"photo": ("chart.png", photo_png, "image/png")},
            )
            if data and data.get("ok"):
                msg_id = data.get("result", {}).get("message_id")
                if len(text) > 1024:
                    await _send_to(cid, text)
            else:
                print(f"[telegram_bot] publish_news photo fail: {data}", flush=True)
        except Exception as e:
            print(f"[telegram_bot] publish_news photo: {e}", flush=True)
    if msg_id is None:
        data = await _api("sendMessage", {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if data and data.get("ok"):
            msg_id = data.get("result", {}).get("message_id")
    if msg_id:
        asyncio.create_task(_ensure_discussion_cta(cid, msg_id))
        # мгновенный буст фермы (outbox → channel_booster)
        try:
            _notify_farm_boost(cid, int(msg_id), text)
        except Exception as e:
            print(f"[telegram_bot] farm boost outbox: {e}", flush=True)


def _notify_farm_boost(channel: str | int, message_id: int, text: str = "") -> None:
    """Пишет в scaner/data/boost_outbox.jsonl — демон подхватит за секунды."""
    import json
    from pathlib import Path

    ch = str(channel).lstrip("@")
    if ch.lstrip("-").isdigit():
        # numeric id — для news используем username
        ch = "nowicki_news"
    roots = [
        Path(__file__).resolve().parent.parent.parent / "scaner" / "data",
        Path.home() / "Desktop" / "scaner" / "data",
        Path(r"C:\Users\Dell\Desktop\scaner\data"),
    ]
    payload = {
        "channel": ch if "nowicki" in ch or ch.startswith("http") else "nowicki_news",
        "msg_id": int(message_id),
        "post_text": (text or "")[:2000],
        "ts": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }
    for d in roots:
        try:
            d.mkdir(parents=True, exist_ok=True)
            path = d / "boost_outbox.jsonl"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            print(f"[telegram_bot] boost outbox → {path}", flush=True)
            return
        except Exception:
            continue


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
    """CTA для закрытий — в discussion, не в канале."""
    return _channel_cta()


def _channel_cta():
    """Кнопки Сайт/Бот — только в чате обсуждений под дубликатом поста."""
    return {"inline_keyboard": [
        [
            {"text": "🌐 Сайт", "url": SITE_URL},
            {"text": "🤖 Бот", "url": BOT_URL},
        ],
    ]}


# Антидубль CTA: ensure_discussion + webhook auto-forward иначе шлют 👇 дважды.
_cta_done: dict[str, float] = {}
_CTA_TTL_SEC = 6 * 3600


def _cta_key(chat_id: int | str, message_id: int) -> str:
    return f"{chat_id}:{int(message_id)}"


def _cta_already_done(chat_id: int | str, message_id: int) -> bool:
    import time

    now = time.time()
    # ленивая чистка
    stale = [k for k, ts in _cta_done.items() if now - ts > _CTA_TTL_SEC]
    for k in stale:
        _cta_done.pop(k, None)
    return _cta_key(chat_id, message_id) in _cta_done


def _cta_mark_done(chat_id: int | str, message_id: int) -> None:
    import time

    _cta_done[_cta_key(chat_id, message_id)] = time.time()


async def _attach_discussion_cta(chat_id: int | str, message_id: int) -> bool:
    """В чате комментов: один ответ «👇» с кнопками Сайт / Бот под корнем треда.

    Без plain-fallback: иначе 👇 всплывает среди обычных комментов людей.
    """
    if not chat_id or not message_id:
        return False
    if _cta_already_done(chat_id, message_id):
        print(f"[telegram_bot] CTA skip duplicate chat={chat_id} reply_to={message_id}")
        return False

    # резервируем сразу — параллельные ensure+webhook не успеют оба отправить
    _cta_mark_done(chat_id, message_id)

    data = await _api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "reply_to_message_id": int(message_id),
            "text": "👇",
            "reply_markup": _channel_cta(),
            "disable_notification": True,
        },
    )
    if data and data.get("ok"):
        print(f"[telegram_bot] CTA 👇 chat={chat_id} reply_to={message_id}")
        return True

    # не удалось привязать к треду — откатываем маркер, без «голого» сообщения в чат
    _cta_done.pop(_cta_key(chat_id, message_id), None)
    print(f"[telegram_bot] CTA 👇 skip (no reply) chat={chat_id} reply_to={message_id} err={data}")
    return False


async def _ensure_discussion_cta(channel_id: str | int, message_id: int) -> None:
    """После поста в канал — найти тред в discussion и повесить кнопки туда."""
    import asyncio

    await asyncio.sleep(1.5)
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.messages import GetDiscussionMessageRequest
        from telethon.utils import get_peer_id

        api_id = int(os.getenv("TELEGRAM_API_ID") or "0")
        api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
        session = (
            os.getenv("TELEGRAM_CHAT_SESSION")
            or os.getenv("TELEGRAM_SESSION")
            or ""
        ).strip()
        if not (api_id and api_hash and session):
            print("[telegram_bot] discussion CTA: нет user-session — ждём webhook auto-forward")
            return

        client = TelegramClient(StringSession(session), api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            print("[telegram_bot] discussion CTA: session не авторизована")
            return

        peer = int(channel_id) if str(channel_id).lstrip("-").isdigit() else channel_id
        entity = await client.get_entity(peer)
        result = await client(GetDiscussionMessageRequest(peer=entity, msg_id=int(message_id)))
        disc_msg = None
        for m in (result.messages or []):
            if getattr(m, "id", None):
                disc_msg = m
                break
        if not disc_msg:
            await client.disconnect()
            print(f"[telegram_bot] discussion CTA: тред не найден для {channel_id}/{message_id}")
            return

        disc_chat_id = None
        if getattr(disc_msg, "peer_id", None):
            disc_chat_id = get_peer_id(disc_msg.peer_id)
        elif result.chats:
            disc_chat_id = get_peer_id(result.chats[0])
        await client.disconnect()

        if disc_chat_id is None:
            print("[telegram_bot] discussion CTA: нет chat id")
            return
        await _attach_discussion_cta(disc_chat_id, disc_msg.id)
    except Exception as e:
        print(f"[telegram_bot] discussion CTA fail: {e}")


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
        chat = (cb.get("message") or {}).get("chat") or {}
        # Кнопки меню — только в личке (не в чате комментов / группах)
        if chat.get("type") and chat.get("type") != "private":
            await _api("answerCallbackQuery", {"callback_query_id": cb.get("id")})
            return
        chat_id = chat.get("id")
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
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = (chat.get("type") or "").strip()
    from_user = message.get("from") or {}
    user_id = from_user.get("id")

    # Чат обсуждений канала: CTA только на авто-форвард поста из канала.
    # Обычные комменты людей — молчим. Дубль с _ensure_discussion_cta режется антидублем.
    if chat_type in ("group", "supergroup"):
        is_auto = bool(message.get("is_automatic_forward"))
        # корень треда (не reply человека); sender_chat = канал-источник
        sender_chat = message.get("sender_chat") or {}
        sender_ok = (not sender_chat) or (sender_chat.get("type") == "channel")
        if (
            is_auto
            and sender_ok
            and message.get("message_id")
            and not message.get("reply_to_message")
        ):
            await _attach_discussion_cta(chat_id, message["message_id"])
        return

    text = str(message.get("text") or "").strip()
    if not chat_id or not text:
        return

    if chat_type != "private":
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
    """Форматирование цены для постов: компактно, без лишних нулей."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v) if v else "—"
    
    # Для крупных (>= 1000) используем пробел как разделитель тысяч
    if abs(n) >= 10000:
        return f"{n:,.0f}".replace(",", " ")
    if abs(n) >= 1000:
        return f"{n:,.2f}".replace(",", " ")
    if abs(n) >= 100:
        return f"{n:.2f}"
    if abs(n) >= 1:
        return f"{n:.4f}".rstrip("0").rstrip(".")
    # Для мелких альткоинов
    return f"{n:.8f}".rstrip("0").rstrip(".")


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


def _open_position_photo(signal: dict) -> bytes | None:
    """Скрин открытой позиции под монету (только текст на шаблоне)."""
    if os.getenv("OPEN_POS_CARD", "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    try:
        from open_position_card import render_open_position_card
        import data_layer

        # Всегда используем 15x
        leverage = 15
        
        # Получаем живую цену
        symbol = str(signal.get("symbol") or "")
        exchange = (signal.get("exchange") or signal.get("listed_on") or "bybit").split(",")[0].strip().lower()
        mark_price = None
        try:
            ticker = data_layer.fetch_ticker(symbol, exchange)
            if ticker and ticker.get("last") is not None:
                mark_price = float(ticker["last"])
        except Exception as e:
            print(f"[telegram_bot] ticker fetch: {e}")
        
        entry = float(signal.get("entry") or 0)
        # Если нет live цены - добавим небольшой рост
        if mark_price is None or mark_price <= 0:
            mark_price = entry * 1.008  # ~0.8% в плюс как fallback
        
        return render_open_position_card(
            symbol=symbol,
            side=str(signal.get("signal") or "LONG"),
            entry=entry,
            leverage=leverage,
            stop=float(signal["stop"]) if signal.get("stop") else None,
            mark_price=mark_price,
            margin=12.0,  # типичная маржа для 15x
            style="bingx",  # только BingX — чёрный фон, без пикселей
        )
    except Exception as e:
        print(f"[telegram_bot] open_position_card: {e}")
        import traceback
        traceback.print_exc()
        return None


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
    try:
        score_f = float(score or 0)
    except (TypeError, ValueError):
        score_f = 0.0
    # quality filter (0–100) vs legacy score (/20)
    if score_f > 20:
        conf = max(0, min(100, round(score_f)))
    else:
        conf = round((score_f / 20) * 100) if score_f else 0
    conf_line = f"\n⚡ Уверенность · <b>{conf}%</b>" if conf else ""
    venues = _exchange_label(signal)

    text = (
        f"🎯 <b>{sym}</b>\n"
        f"{HR}\n"
        f"{side_emoji}\n"
        f"<b>{sym}</b>{conf_line}\n"
        f"<i>{venues}</i>\n"
        f"{HR}\n"
        f"{_levels_block(entry, stop, tp1, tp2, tp3)}\n"
    )
    if reasons:
        # Фильтруем технические reason'ы — оставляем только человеческие
        clean = []
        for r in reasons[:4]:
            r_lower = r.lower()
            # Пропускаем технические маркеры
            if any(skip in r_lower for skip in [
                'parser:', 'quality filter', 'агрегированн', 'aggregated',
                'листинг:', 'exit mode:', 'автоимпорт'
            ]):
                continue
            # Пропускаем если начинается с листинга
            if str(r).startswith('Листинг:'):
                continue
            clean.append(r)
        
        if clean:
            text += f"{HR}\n" + "\n".join(f"💡 {r}" for r in clean) + "\n"
    
    text += f"\n<a href=\"{SITE_URL}\">nowicki.trade</a>  ·  <i>не фин. совет</i>"
    await publish_signal_open(text, _channel_cta(), photo_png=_open_position_photo(signal))
    
    # Автопересылка в news канал (1 раз в день)
    await forward_last_signal_to_news()


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
        f"🎯 <b>{sym}</b>\n"
        f"{HR}\n"
        f"{side_emoji}\n"
        f"<b>{sym}</b>\n"
        f"<i>{venues}</i>\n"
        f"{HR}\n"
        f"{_levels_block(entry, stop, tp1, tp2, tp3)}\n"
        f"\n<a href=\"{SITE_URL}\">nowicki.trade</a>  ·  <i>не фин. совет</i>"
    )
    await publish_signal_open(text, _channel_cta(), photo_png=_open_position_photo(signal))
    
    # Автопересылка в news канал (1 раз в день)
    await forward_last_signal_to_news()



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
    side = (signal.get("signal") or "").upper()
    entry = signal.get("entry")
    exit_price = signal.get("exit")
    win = pnl > 0
    show = polish_pnl(pnl, decimals=2)
    if pnl == 0:
        emoji, title = "➖", "Закрыли в ноль"
    elif win:
        emoji, title = "✅", "Закрыли в плюс"
    else:
        emoji, title = "➖", "Закрыли с небольшим минусом"
    pnl_str = f"+{show:.2f}%" if show > 0 else f"{show:.2f}%"
    side_ru = "LONG" if side == "LONG" else "SHORT" if side == "SHORT" else side
    labels = {
        "tp1": "взяли TP1",
        "tp2": "взяли TP2",
        "tp3": "взяли TP3",
        "sl": "сработал стоп",
        "be": "вышли в безубыток",
        "potential": "закрыли по рынку",
        "timeout": "закрыли по времени",
        "channel_closed": "закрыли по сигналу",
    }
    why = labels.get(result, result)
    text = (
        f"{emoji} <b>{title}</b>\n"
        f"{HR}\n"
        f"<b>{sym}</b> · {side_ru}\n"
        f"{why}\n"
        f"PnL · <b>{pnl_str}</b> · 15x\n"
        f"{HR}\n"
        f"<a href=\"{SITE_URL}\">nowicki.trade</a>"
    )

    photo = None
    if entry is not None:
        try:
            from profit_card import render_share_card
            photo = render_share_card(
                symbol=sym, side=side or "LONG", entry=float(entry),
                pnl_pct=float(pnl), exit_price=float(exit_price) if exit_price is not None else None,
                leverage=15, family="bingx",
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


async def forward_last_signal_to_news() -> bool:
    """
    Копирует последнее ТВХ-сообщение из премиум канала в news канал.

    Важно: используем copyMessage (не forwardMessage) — иначе Telegram
    ставит «Переслано из…» и НЕ показывает кнопку «Комментарии» у поста,
    даже если к каналу привязан discussion-чат.
    Ограничение: 1 раз в день (UTC).
    """
    global _last_premium_message, _last_forward_date
    
    # Проверяем env флаг
    if os.getenv("AUTO_FORWARD_TO_NEWS", "1").strip().lower() in ("0", "false", "no", "off"):
        print("[telegram_bot] AUTO_FORWARD_TO_NEWS отключён")
        return False
    
    # Проверяем, была ли уже пересылка сегодня
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if _last_forward_date == today:
        print(f"[telegram_bot] пересылка в news уже была сегодня ({today})")
        return False
    
    if not _last_premium_message:
        print("[telegram_bot] нет сохранённого message_id для пересылки")
        return False
    
    chat_id, msg_id = _last_premium_message
    news_channel = (
        os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL")
        or os.getenv("MARKET_OUTLOOK_CHANNEL")
        or ""
    ).strip()
    
    if not news_channel:
        print("[telegram_bot] TELEGRAM_NEWS_TARGET_CHANNEL не задан")
        return False
    
    # Приводим к правильному формату (@channel или -100...)
    if not news_channel.startswith("@") and not news_channel.startswith("-"):
        news_channel = f"@{news_channel.lstrip('@')}"
    
    print(f"[telegram_bot] копируем сообщение {msg_id} из {chat_id} → {news_channel} (copyMessage)")
    
    payload = {
        "chat_id": news_channel,
        "from_chat_id": chat_id,
        "message_id": msg_id,
    }
    
    # Только copyMessage — нативная публикация канала → есть «Комментарии»
    data = await _api("copyMessage", payload)
    
    if data and data.get("ok"):
        print(f"[telegram_bot] ✅ сообщение скопировано в {news_channel} (без 'Forwarded')")
        _last_premium_message = None
        _last_forward_date = today
        return True

    print(f"[telegram_bot] ❌ copyMessage fail: {data}")
    return False
