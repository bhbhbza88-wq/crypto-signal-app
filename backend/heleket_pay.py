"""
Heleket — автоматическая оплата Premium (крипта / карта на их форме).

Env:
  HELEKET_MERCHANT_UUID      — UUID мерчанта из личного кабинета
  HELEKET_PAYMENT_API_KEY    — payment API key (не payout!)
  HELEKET_CALLBACK_URL       — webhook (default: https://<RAILWAY_PUBLIC_DOMAIN>/api/heleket-webhook)
  HELEKET_SUCCESS_URL        — редирект после оплаты (default: FRONTEND_URL/app/pricing?paid=1)
  HELEKET_RETURN_URL         — кнопка «назад» на форме (default: FRONTEND_URL/app/pricing)
  HELEKET_CURRENCY           — USD (default)
  HELEKET_AMOUNT_MONTH       — 29
  HELEKET_AMOUNT_3MO         — 75
  HELEKET_AMOUNT_LIFETIME    — 299
  HELEKET_TEST_AMOUNT        — если задан (напр. 1), все тарифы = эта сумма для теста
  HELEKET_WEBHOOK_IP         — 31.133.220.8 (optional check)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

import httpx

HELEKET_MERCHANT_UUID = os.getenv("HELEKET_MERCHANT_UUID", "").strip()
HELEKET_PAYMENT_API_KEY = os.getenv("HELEKET_PAYMENT_API_KEY", "").strip()
HELEKET_CURRENCY = os.getenv("HELEKET_CURRENCY", "USD").strip() or "USD"
HELEKET_WEBHOOK_IP = os.getenv("HELEKET_WEBHOOK_IP", "31.133.220.8").strip()

_FRONTEND = (os.getenv("FRONTEND_URL", "https://nowicki.trade") or "https://nowicki.trade").rstrip("/")
HELEKET_SUCCESS_URL = os.getenv("HELEKET_SUCCESS_URL", f"{_FRONTEND}/app/pricing?paid=1").strip()
HELEKET_RETURN_URL = os.getenv("HELEKET_RETURN_URL", f"{_FRONTEND}/app/pricing").strip()

_PLAN_AMOUNTS = {
    "month": os.getenv("HELEKET_AMOUNT_MONTH", "29").strip() or "29",
    "3mo": os.getenv("HELEKET_AMOUNT_3MO", "75").strip() or "75",
    "lifetime": os.getenv("HELEKET_AMOUNT_LIFETIME", "299").strip() or "299",
}
_TEST_AMOUNT = os.getenv("HELEKET_TEST_AMOUNT", "").strip()
if _TEST_AMOUNT:
    _PLAN_AMOUNTS = {k: _TEST_AMOUNT for k in _PLAN_AMOUNTS}
_PLAN_DAYS = {
    "month": int(os.getenv("HELEKET_DAYS_MONTH", "30") or "30"),
    "3mo": int(os.getenv("HELEKET_DAYS_3MO", "90") or "90"),
    "lifetime": int(os.getenv("HELEKET_DAYS_LIFETIME", "3650") or "3650"),
}

_API = "https://api.heleket.com/v1/payment"
_PAID_STATUSES = frozenset({"paid", "paid_over"})


def is_configured() -> bool:
    return bool(HELEKET_MERCHANT_UUID and HELEKET_PAYMENT_API_KEY)


def callback_url() -> str:
    explicit = os.getenv("HELEKET_CALLBACK_URL", "").strip()
    if explicit:
        return explicit
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if domain:
        return f"https://{domain}/api/heleket-webhook"
    api_base = os.getenv("API_PUBLIC_URL", "").strip().rstrip("/")
    if api_base:
        return f"{api_base}/api/heleket-webhook"
    return f"{_FRONTEND}/api/heleket-webhook"


def plan_amount(period: str) -> str:
    return _PLAN_AMOUNTS.get(period, _PLAN_AMOUNTS["month"])


def plan_amounts() -> dict[str, str]:
    return dict(_PLAN_AMOUNTS)


def is_test_mode() -> bool:
    return bool(_TEST_AMOUNT)


def plan_days(period: str) -> int:
    return _PLAN_DAYS.get(period, _PLAN_DAYS["month"])


def _json_for_sign(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("/", "\\/")


def _make_sign(data: dict, api_key: str) -> str:
    payload = _json_for_sign(data)
    b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return hashlib.md5((b64 + api_key).encode("utf-8")).hexdigest()


def verify_webhook_payload(body: dict[str, Any]) -> bool:
    if not HELEKET_PAYMENT_API_KEY:
        return False
    sign = body.get("sign")
    if not sign:
        return False
    data = {k: v for k, v in body.items() if k != "sign"}
    expected = _make_sign(data, HELEKET_PAYMENT_API_KEY)
    # hmac.compare_digest (hashlib has no compare_digest) — unequal lengths → False, not crash
    a = str(sign).lower().encode("utf-8")
    b = expected.lower().encode("utf-8")
    if len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def webhook_ip_allowed(ip: str | None) -> bool:
    if not HELEKET_WEBHOOK_IP:
        return True
    return (ip or "").strip() == HELEKET_WEBHOOK_IP


def _new_order_id(user_id: int) -> str:
    ts = int(time.time())
    tail = secrets.token_hex(4)
    return f"hk-{user_id}-{ts}-{tail}"


def _meta_string(*, user_id: int, period: str, telegram_id: int | None = None) -> str:
    parts = [f"uid:{user_id}", f"period:{period}"]
    if telegram_id:
        parts.append(f"tg:{int(telegram_id)}")
    return "|".join(parts)[:255]


def parse_meta(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not raw:
        return out
    for part in str(raw).split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


async def create_invoice(
    *,
    user_id: int,
    email: str,
    period: str = "month",
    telegram_id: int | None = None,
) -> dict | None:
    """Создаёт invoice в Heleket. Возвращает result dict (url, uuid, order_id…)."""
    import database as db

    if not is_configured():
        return None
    period = period if period in _PLAN_AMOUNTS else "month"
    amount = plan_amount(period)
    order_id = _new_order_id(user_id)

    payload = {
        "amount": amount,
        "currency": HELEKET_CURRENCY,
        "order_id": order_id,
        "url_callback": callback_url(),
        "url_success": HELEKET_SUCCESS_URL,
        "url_return": HELEKET_RETURN_URL,
        "lifetime": 3600,
        "additional_data": _meta_string(user_id=user_id, period=period, telegram_id=telegram_id),
        "payer_email": (email or "").strip() or None,
        "is_payment_multiple": True,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    body_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    b64 = base64.b64encode(body_str.encode("utf-8")).decode("ascii")
    sign = hashlib.md5((b64 + HELEKET_PAYMENT_API_KEY).encode("utf-8")).hexdigest()
    headers = {
        "merchant": HELEKET_MERCHANT_UUID,
        "sign": sign,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(_API, content=body_str.encode("utf-8"), headers=headers)
            data = r.json()
    except Exception as e:
        print(f"[heleket] create invoice error: {e}")
        return None

    if data.get("state") != 0:
        print(f"[heleket] create failed: {data}")
        return None

    result = data.get("result") or {}
    db.create_heleket_order(
        order_id=order_id,
        user_id=user_id,
        heleket_uuid=result.get("uuid"),
        period=period,
        amount=amount,
        currency=HELEKET_CURRENCY,
        pay_url=result.get("url"),
    )
    result["order_id"] = order_id
    return result


async def create_invoice_for_telegram(chat_id: int, period: str = "month") -> dict | None:
    import database as db

    user = db.get_user_by_telegram_id(chat_id)
    if not user:
        return None
    return await create_invoice(
        user_id=user["id"],
        email=user["email"],
        period=period,
        telegram_id=chat_id,
    )


async def _signed_post_async(path: str, payload: dict) -> dict | None:
    if not is_configured():
        return None
    body_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    b64 = base64.b64encode(body_str.encode("utf-8")).decode("ascii")
    sign = hashlib.md5((b64 + HELEKET_PAYMENT_API_KEY).encode("utf-8")).hexdigest()
    headers = {
        "merchant": HELEKET_MERCHANT_UUID,
        "sign": sign,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                f"https://api.heleket.com{path}",
                content=body_str.encode("utf-8"),
                headers=headers,
            )
            return r.json()
    except Exception as e:
        print(f"[heleket] POST {path} error: {e}")
        return None


async def fetch_payment_info(*, order_id: str | None = None, uuid: str | None = None) -> dict | None:
    payload: dict[str, str] = {}
    if order_id:
        payload["order_id"] = order_id
    elif uuid:
        payload["uuid"] = uuid
    else:
        return None
    data = await _signed_post_async("/v1/payment/info", payload)
    if not data or data.get("state") != 0:
        return None
    return data.get("result") or None


async def fulfill_paid_order(
    *,
    order_id: str,
    heleket_uuid: str | None = None,
    additional_data: str | None = None,
    status_hint: str | None = None,
) -> dict:
    """Идемпотентная выдача Premium по оплаченному order_id."""
    import database as db
    import telegram_bot

    status = (status_hint or "").strip().lower()
    if status and status not in _PAID_STATUSES:
        return {"ok": True, "skipped": status}

    if not order_id:
        return {"ok": False, "error": "no order_id"}

    order = db.get_heleket_order(order_id)
    if order and order.get("status") == "granted":
        user = db.get_user_by_id(order["user_id"]) if order.get("user_id") else None
        return {
            "ok": True,
            "duplicate": True,
            "order_id": order_id,
            "granted": (user or {}).get("email"),
            "tier": (user or {}).get("tier"),
            "premium_until": (user or {}).get("premium_until"),
        }

    meta = parse_meta(additional_data)
    user_id = None
    period = "month"
    telegram_id = None

    if order:
        user_id = order.get("user_id")
        period = order.get("period") or "month"
    if meta.get("uid"):
        try:
            user_id = int(meta["uid"])
        except ValueError:
            pass
    if meta.get("period") in _PLAN_AMOUNTS:
        period = meta["period"]
    if meta.get("tg"):
        try:
            telegram_id = int(meta["tg"])
        except ValueError:
            telegram_id = None

    # Fallback: order_id = hk-{user_id}-{ts}-{tail}
    if not user_id and isinstance(order_id, str) and order_id.startswith("hk-"):
        parts = order_id.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            user_id = int(parts[1])

    user = db.get_user_by_id(user_id) if user_id else None
    if not user and order:
        user = db.get_user_by_id(order["user_id"])

    if not user:
        db.mark_heleket_order(order_id, "paid_no_user", heleket_uuid=heleket_uuid)
        await telegram_bot._notify_admins(
            f"💰 Heleket оплачен, user не найден\norder={order_id} uuid={heleket_uuid}"
        )
        return {"ok": True, "needs_manual": True, "order_id": order_id}

    if telegram_id:
        db.set_user_telegram_id(user["id"], telegram_id)
    elif user.get("telegram_id"):
        telegram_id = int(user["telegram_id"])

    days = plan_days(period)
    result = await telegram_bot.grant_premium_access(
        user["email"],
        notify_telegram_id=telegram_id,
        days=days,
    )
    db.mark_heleket_order(order_id, "granted", heleket_uuid=heleket_uuid)
    user = db.get_user_by_id(user["id"]) or user
    await telegram_bot._notify_admins(
        f"💰 Heleket → Premium ({period}, {days}d)\n"
        f"order={order_id} · {user['email']}\n{result}"
    )
    return {
        "ok": True,
        "granted": user["email"],
        "order_id": order_id,
        "period": period,
        "tier": user.get("tier"),
        "premium_until": user.get("premium_until"),
    }


async def handle_webhook(body: dict[str, Any]) -> dict:
    if not verify_webhook_payload(body):
        print("[heleket] webhook invalid_sign")
        return {"ok": False, "error": "invalid_sign"}

    status = (body.get("status") or body.get("payment_status") or "").strip().lower()
    order_id = body.get("order_id")
    heleket_uuid = body.get("uuid")

    if status not in _PAID_STATUSES:
        # Keep latest non-terminal status on the local order for CRM
        if order_id and status:
            import database as db
            order = db.get_heleket_order(order_id)
            if order and order.get("status") not in ("granted",):
                db.mark_heleket_order(order_id, status, heleket_uuid=heleket_uuid)
        return {"ok": True, "skipped": status or "unknown"}

    return await fulfill_paid_order(
        order_id=order_id,
        heleket_uuid=heleket_uuid,
        additional_data=body.get("additional_data"),
        status_hint=status,
    )


async def sync_order_from_heleket(order_id: str) -> dict:
    """Pull payment/info from Heleket and grant if paid."""
    info = await fetch_payment_info(order_id=order_id)
    if not info:
        return {"ok": False, "error": "not_found", "order_id": order_id}
    status = (info.get("status") or info.get("payment_status") or "").strip().lower()
    if status not in _PAID_STATUSES:
        import database as db
        order = db.get_heleket_order(order_id)
        if order and order.get("status") not in ("granted",) and status:
            db.mark_heleket_order(order_id, status, heleket_uuid=info.get("uuid"))
        return {"ok": True, "skipped": status or "unknown", "order_id": order_id}
    return await fulfill_paid_order(
        order_id=info.get("order_id") or order_id,
        heleket_uuid=info.get("uuid"),
        additional_data=info.get("additional_data"),
        status_hint=status,
    )


async def sync_user_payments(user_id: int) -> dict:
    """Check recent orders for this user against Heleket; grant if any paid."""
    import database as db

    orders = db.list_heleket_orders_for_user(user_id, limit=10)
    if not orders:
        return {"ok": True, "checked": 0, "granted": None}

    granted = None
    checked = 0
    results = []
    for order in orders:
        if order.get("status") == "granted":
            user = db.get_user_by_id(user_id)
            return {
                "ok": True,
                "checked": 0,
                "already": True,
                "granted": (user or {}).get("email"),
                "tier": (user or {}).get("tier"),
                "premium_until": (user or {}).get("premium_until"),
            }
        checked += 1
        r = await sync_order_from_heleket(order["order_id"])
        results.append(r)
        if r.get("granted"):
            granted = r
            break

    user = db.get_user_by_id(user_id)
    out = {
        "ok": True,
        "checked": checked,
        "granted": (granted or {}).get("granted"),
        "tier": (user or {}).get("tier"),
        "premium_until": (user or {}).get("premium_until"),
        "results": results,
    }
    return out


async def recover_pending_paid_orders(*, limit: int = 30) -> dict:
    """Startup/admin: re-check pending local orders via Heleket payment/info."""
    import database as db

    if not is_configured():
        return {"ok": False, "error": "not_configured"}
    pending = db.list_pending_heleket_orders(limit=limit)
    granted = []
    skipped = 0
    for order in pending:
        r = await sync_order_from_heleket(order["order_id"])
        if r.get("granted") and not r.get("duplicate"):
            granted.append(r["granted"])
        else:
            skipped += 1
    if granted:
        print(f"[heleket] recover granted={granted}")
    return {"ok": True, "pending": len(pending), "granted": granted, "skipped": skipped}
