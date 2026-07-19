"""
Crypto Pay (@CryptoBot) — автоматическая оплата Premium.

Env:
  CRYPTO_PAY_API_TOKEN  — токен приложения из @CryptoBot → Crypto Pay
  CRYPTO_PAY_AMOUNT     — сумма (default 29)
  CRYPTO_PAY_ASSET      — монета (default USDT)
  CRYPTO_PAY_DAYS       — дней Premium после оплаты (default 30)
  CRYPTO_PAY_TESTNET    — 1 = testnet API
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import httpx

CRYPTO_PAY_API_TOKEN = os.getenv("CRYPTO_PAY_API_TOKEN", "").strip()
CRYPTO_PAY_AMOUNT = os.getenv("CRYPTO_PAY_AMOUNT", "29").strip() or "29"
CRYPTO_PAY_ASSET = os.getenv("CRYPTO_PAY_ASSET", "USDT").strip() or "USDT"
CRYPTO_PAY_DAYS = int(os.getenv("CRYPTO_PAY_DAYS", "30") or "30")
CRYPTO_PAY_TESTNET = os.getenv("CRYPTO_PAY_TESTNET", "").strip().lower() in ("1", "true", "yes")

_API_BASE = (
    "https://testnet-pay.crypt.bot/api"
    if CRYPTO_PAY_TESTNET
    else "https://pay.crypt.bot/api"
)

_SETTING_INVOICE_PREFIX = "cryptopay_invoice_"


def is_configured() -> bool:
    return bool(CRYPTO_PAY_API_TOKEN)


async def _api(method: str, params: dict | None = None) -> dict | None:
    if not CRYPTO_PAY_API_TOKEN:
        return None
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_API_TOKEN}
    url = f"{_API_BASE}/{method}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers, params=params or {})
            data = r.json()
    except Exception as e:
        print(f"[crypto_pay] {method} error: {e}")
        return None
    if not data.get("ok"):
        print(f"[crypto_pay] {method} failed: {data}")
        return None
    return data.get("result")


async def create_invoice(*, telegram_id: int, email: str | None = None) -> dict | None:
    """Создаёт invoice. payload: tg:<id>|uid:<user_id> или tg:<id>."""
    payload_parts = [f"tg:{int(telegram_id)}"]
    if email:
        payload_parts.append(f"email:{email.lower().strip()}")
    params = {
        "asset": CRYPTO_PAY_ASSET,
        "amount": str(CRYPTO_PAY_AMOUNT),
        "description": f"NOWICKI Premium · ${CRYPTO_PAY_AMOUNT}/мес",
        "payload": "|".join(payload_parts)[:4096],
        "expires_in": 3600,
        "paid_btn_name": "callback",
        "paid_btn_url": "https://t.me/trading4325_bot",
        "allow_comments": "false",
        "allow_anonymous": "false",
    }
    return await _api("createInvoice", params)


async def set_webhook(url: str) -> bool:
    result = await _api("setWebhook", {"url": url})
    ok = result is not None
    print(f"[crypto_pay] setWebhook → {url}: {'ok' if ok else 'fail'}")
    return ok


def verify_webhook_signature(body: bytes, signature: str | None) -> bool:
    """crypto-pay-api-signature = HMAC-SHA256(body, SHA256(token))."""
    if not CRYPTO_PAY_API_TOKEN or not signature:
        return False
    secret = hashlib.sha256(CRYPTO_PAY_API_TOKEN.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def parse_payload(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not raw:
        return out
    for part in str(raw).split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _invoice_already_processed(invoice_id: int) -> bool:
    import database as db
    return bool(db.get_setting(f"{_SETTING_INVOICE_PREFIX}{invoice_id}"))


def _mark_invoice_processed(invoice_id: int) -> None:
    import database as db
    db.set_setting(f"{_SETTING_INVOICE_PREFIX}{invoice_id}", "1")


async def handle_webhook_update(update: dict[str, Any]) -> dict:
    """Обрабатывает update от Crypto Pay. Возвращает краткий статус."""
    import database as db
    import telegram_bot

    update_type = update.get("update_type") or update.get("type")
    invoice = update.get("payload") or {}
    if update_type != "invoice_paid":
        return {"ok": True, "skipped": update_type}

    invoice_id = invoice.get("invoice_id")
    status = invoice.get("status")
    if status and status != "paid":
        return {"ok": True, "skipped": f"status={status}"}
    if invoice_id is None:
        return {"ok": False, "error": "no invoice_id"}

    try:
        invoice_id = int(invoice_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad invoice_id"}

    if _invoice_already_processed(invoice_id):
        return {"ok": True, "duplicate": True, "invoice_id": invoice_id}

    meta = parse_payload(invoice.get("payload"))
    tg_raw = meta.get("tg")
    email = (meta.get("email") or "").lower().strip() or None
    telegram_id = None
    if tg_raw:
        try:
            telegram_id = int(tg_raw)
        except ValueError:
            telegram_id = None

    user = None
    if telegram_id:
        user = db.get_user_by_telegram_id(telegram_id)
    if not user and email:
        user = db.get_user_by_email(email)

    if not user:
        _mark_invoice_processed(invoice_id)
        if telegram_id:
            await telegram_bot.send_message(
                telegram_id,
                f"<b>✅ Оплата получена</b>\n{telegram_bot.HR}\n"
                "Аккаунт на nowicki.trade с этим Telegram не найден.\n"
                "Пришли <b>email</b> одним сообщением — активируем Premium.\n"
                f"Или напиши @{telegram_bot.SUPPORT_USER}.",
            )
            telegram_bot._awaiting_email[telegram_id] = True
        await telegram_bot._notify_admins(
            f"💰 Crypto Pay invoice #{invoice_id} оплачен, но user не найден.\n"
            f"tg={telegram_id} payload={invoice.get('payload')}"
        )
        return {"ok": True, "needs_email": True, "invoice_id": invoice_id}

    email = user["email"]
    if telegram_id:
        db.set_user_telegram_id(user["id"], telegram_id)

    result = await telegram_bot.grant_premium_access(
        email,
        notify_telegram_id=telegram_id or user.get("telegram_id"),
        days=CRYPTO_PAY_DAYS,
    )
    _mark_invoice_processed(invoice_id)
    await telegram_bot._notify_admins(
        f"💰 Crypto Pay → Premium\n"
        f"invoice #{invoice_id} · {email}\n{result}"
    )
    return {"ok": True, "granted": email, "invoice_id": invoice_id}
