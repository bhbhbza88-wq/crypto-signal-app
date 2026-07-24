"""
FastAPI backend — V8 стратегия.
Бэктест использует should_enter() + get_mults() + calc_levels() из nfi_strategy (V8).
"""

import os
import json
import hmac
import asyncio
import secrets
import urllib.request
import urllib.error
import pandas as pd
import time as _time
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

_SENTRY_DSN = (os.getenv("SENTRY_DSN") or "").strip()
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        environment=(os.getenv("SENTRY_ENVIRONMENT") or "production").strip() or "production",
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1") or "0.1"),
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
        send_default_pii=False,
    )

import database as db
import auth
import telegram_bot
import crypto_pay
import heleket_pay
import public_feed
import email_smtp
from scanner import start_background_scanner, MAX_OPEN_TRADES
import data_layer
from data_layer import exchange, api_call, build_features, detect_regime, CANDIDATES
import nfi_strategy
from nfi_strategy import (
    build_nfi_features, should_enter,
    get_mults, calc_levels, calc_position_size, volatility_position_size,
    backtest_levels, ADX_MIN, get_risk_status
)
from signal_ingest import normalize_symbol, open_signal
import telegram_ingest
import chat_engage
import ai_client


PRICING_NUDGE_INTERVAL_SEC = int(os.getenv("PRICING_NUDGE_INTERVAL_SEC", "1200") or "1200")  # 20 мин


async def _pricing_nudge_loop():
    """Раз в 15–30 мин: free + verified + ≥24ч → одно pricing-письмо."""
    await asyncio.sleep(60)  # дать БД/SMTP подняться
    while True:
        try:
            if email_smtp.is_configured():
                for u in db.list_users_for_pricing_nudge(limit=30):
                    try:
                        email_smtp.send_pricing_nudge_email(u["email"])
                    except Exception as e:
                        print(f"[email] pricing nudge failed for {u.get('email')}: {e}")
                    finally:
                        db.mark_pricing_nudge_sent(u["id"])
                    await asyncio.sleep(0.4)
        except Exception as e:
            print(f"[email] pricing nudge loop: {e}")
        await asyncio.sleep(max(900, PRICING_NUDGE_INTERVAL_SEC))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    start_background_scanner()
    if telegram_ingest.is_configured():
        asyncio.create_task(telegram_ingest.run())
    # Отдельный клиент только если TELEGRAM_CHAT_SESSION ≠ ingest.
    # Иначе chat_engage цепляется к клиенту ingest (один аккаунт).
    if chat_engage.needs_own_client():
        asyncio.create_task(chat_engage.run())
    asyncio.create_task(telegram_bot.set_webhook())
    asyncio.create_task(_pricing_nudge_loop())
    if heleket_pay.is_configured():
        asyncio.create_task(heleket_pay.recover_pending_paid_orders())
    # Crypto Pay webhook URL ставится вручную в @CryptoBot → My Apps → Webhooks
    # (API-метода setWebhook у Crypto Pay нет).
    yield


app = FastAPI(title="Crypto Signal App V8", lifespan=lifespan)


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "https://nowicki.trade",
        "https://www.nowicki.trade",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Telegram-Bot-Api-Secret-Token"],
)

# Простой in-memory rate limit (per-process; на одном инстансе Railway достаточно)
_rate_buckets: dict[str, list[float]] = {}


def _rate_limit(key: str, limit: int = 10, window: float = 60.0) -> None:
    now = _time.time()
    bucket = _rate_buckets.setdefault(key, [])
    bucket[:] = [t for t in bucket if now - t < window]
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Слишком много попыток, подожди минуту")
    bucket.append(now)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.post("/api/telegram-webhook")
async def telegram_webhook(request: Request,
                            x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    """Вебхук бота: /start, /help, /premium, /status и callback-кнопки.
    secret_token проверяем, чтобы принимать только запросы от Telegram."""
    if not telegram_bot.WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook not configured")
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
        x_telegram_bot_api_secret_token, telegram_bot.WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=403, detail="Invalid secret token")

    update = await request.json()
    await telegram_bot.handle_update(update)
    return {"ok": True}


@app.post("/api/crypto-pay-webhook")
async def crypto_pay_webhook(request: Request):
    """Webhook Crypto Pay (@CryptoBot): invoice_paid → автовыдача Premium."""
    if not crypto_pay.is_configured():
        raise HTTPException(status_code=503, detail="Crypto Pay not configured")
    body = await request.body()
    signature = request.headers.get("crypto-pay-api-signature")
    if not crypto_pay.verify_webhook_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    try:
        update = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    result = await crypto_pay.handle_webhook_update(update)
    return result


@app.post("/api/heleket-webhook")
async def heleket_webhook(request: Request):
    """Webhook Heleket: status paid → автовыдача Premium."""
    if not heleket_pay.is_configured():
        raise HTTPException(status_code=503, detail="Heleket not configured")
    ip = _client_ip(request)
    if not heleket_pay.webhook_ip_allowed(ip):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    return await heleket_pay.handle_webhook(body)


# ── Аутентификация / монетизация ──────────────────────────────────
class AuthRequest(BaseModel):
    email: str
    password: str

class UpgradeRequest(BaseModel):
    tier: str   # 'premium' | 'vip'


class TraderCreate(BaseModel):
    name: str
    avatar_url: str | None = None
    bio: str | None = None


class AddSignalRequest(BaseModel):
    trader_id: int
    symbol: str
    signal: str      # 'LONG' | 'SHORT'
    entry: float
    stop: float
    tp1: float
    tp2: float
    tp3: float
    note: str | None = None   # комментарий трейдера к сделке (необязательно)


def _token_from_header(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(authorization: str | None = Header(default=None)):
    """Возвращает пользователя или None (необязательная авторизация)."""
    return auth.user_from_token(_token_from_header(authorization))


def require_user(authorization: str | None = Header(default=None)):
    user = auth.user_from_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


class HeleketCreateRequest(BaseModel):
    period: str = "month"  # month | 3mo | lifetime


@app.get("/api/payments/config")
def payments_config():
    return {
        "heleket": heleket_pay.is_configured(),
        "crypto_pay": crypto_pay.is_configured(),
        "heleket_plans": heleket_pay.plan_amounts(),
        "heleket_test_mode": heleket_pay.is_test_mode(),
        "heleket_currency": heleket_pay.HELEKET_CURRENCY,
    }


@app.post("/api/payments/heleket/create")
async def heleket_create_invoice(req: HeleketCreateRequest, user=Depends(require_user)):
    """Создаёт счёт Heleket и возвращает ссылку на оплату."""
    if not heleket_pay.is_configured():
        raise HTTPException(status_code=503, detail="Heleket не настроен")
    period = req.period if req.period in ("month", "3mo", "lifetime") else "month"
    invoice = await heleket_pay.create_invoice(
        user_id=user["id"],
        email=user["email"],
        period=period,
        telegram_id=user.get("telegram_id"),
    )
    if not invoice or not invoice.get("url"):
        raise HTTPException(status_code=502, detail="Не удалось создать счёт Heleket")
    return {
        "pay_url": invoice["url"],
        "order_id": invoice.get("order_id"),
        "amount": heleket_pay.plan_amount(period),
        "currency": heleket_pay.HELEKET_CURRENCY,
        "period": period,
    }


@app.post("/api/payments/heleket/sync")
async def heleket_sync_payment(user=Depends(require_user)):
    """После возврата с оплаты: сверяем pending-счета с Heleket и выдаём Premium."""
    if not heleket_pay.is_configured():
        raise HTTPException(status_code=503, detail="Heleket не настроен")
    _rate_limit(f"heleket:sync:{user['id']}", limit=12, window=60)
    result = await heleket_pay.sync_user_payments(user["id"])
    # Always return fresh user profile so UI can unlock without full reload
    fresh = auth.public_user(db.get_user_by_id(user["id"]) or user)
    result["user"] = fresh
    return result


def require_tier(min_tier: str):
    def dep(authorization: str | None = Header(default=None)):
        user = auth.user_from_token(_token_from_header(authorization))
        if not user:
            raise HTTPException(status_code=401, detail="Требуется вход")
        if not auth.tier_allows(auth.effective_tier(user), min_tier):
            raise HTTPException(status_code=403, detail=f"Нужен тариф {min_tier} или выше")
        return user
    return dep


def require_admin(authorization: str | None = Header(default=None)):
    user = auth.user_from_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    if not user.get('is_admin'):
        raise HTTPException(status_code=403, detail="Только для администратора")
    return user


@app.post("/api/admin/heleket-recover")
async def admin_heleket_recover(admin=Depends(require_admin)):
    """Админ: перепроверить все pending Heleket-заказы и выдать Premium где paid."""
    if not heleket_pay.is_configured():
        raise HTTPException(status_code=503, detail="Heleket не настроен")
    return await heleket_pay.recover_pending_paid_orders(limit=50)


@app.post("/api/auth/register")
def auth_register(req: AuthRequest, request: Request):
    _rate_limit(f"auth:reg:{_client_ip(request)}", limit=5, window=60)
    data, err = auth.register(req.email, req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return data


@app.post("/api/auth/login")
def auth_login(req: AuthRequest, request: Request):
    _rate_limit(f"auth:login:{_client_ip(request)}", limit=10, window=60)
    user, token = auth.login(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail=token)
    return {"token": token, "user": auth.public_user(user)}


class GoogleAuthRequest(BaseModel):
    id_token: str


class EmailOnlyRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@app.get("/api/auth/config")
def auth_config():
    """Публичные флаги для фронта (Google client id, SMTP)."""
    return auth.public_auth_config()


@app.post("/api/auth/google")
def auth_google(req: GoogleAuthRequest, request: Request):
    _rate_limit(f"auth:google:{_client_ip(request)}", limit=20, window=60)
    user, token = auth.login_with_google(req.id_token)
    if not user:
        raise HTTPException(status_code=401, detail=token)
    return {"token": token, "user": auth.public_user(user)}


class TokenRequest(BaseModel):
    token: str


@app.post("/api/auth/verify-email")
def auth_verify_email(req: TokenRequest, request: Request):
    _rate_limit(f"auth:verify:{_client_ip(request)}", limit=20, window=60)
    data, err = auth.verify_email(req.token)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return data


@app.post("/api/auth/resend-verification")
def auth_resend_verification(req: EmailOnlyRequest, request: Request):
    _rate_limit(f"auth:resend:{_client_ip(request)}", limit=5, window=60)
    data, err = auth.resend_verification(req.email)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return data


@app.post("/api/auth/forgot-password")
def auth_forgot_password(req: EmailOnlyRequest, request: Request):
    _rate_limit(f"auth:forgot:{_client_ip(request)}", limit=5, window=60)
    data, err = auth.request_password_reset(req.email)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return data


@app.post("/api/auth/reset-password")
def auth_reset_password(req: ResetPasswordRequest, request: Request):
    _rate_limit(f"auth:reset:{_client_ip(request)}", limit=10, window=60)
    data, err = auth.reset_password(req.token, req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return data


@app.post("/api/auth/logout")
def auth_logout(authorization: str | None = Header(default=None)):
    tok = _token_from_header(authorization)
    if tok:
        auth.logout(tok)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(default=None)):
    u = auth.user_from_token(_token_from_header(authorization))
    if not u:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return {"user": auth.public_user(u)}


@app.post("/api/billing/upgrade")
def billing_upgrade(req: UpgradeRequest, user=Depends(require_user)):
    """Смена тарифа: только админ, либо BILLING_STUB=1 для локальных тестов.

    BILLING_STUB игнорируется на Railway (проде) — иначе случайно выставленная
    переменная позволила бы любому юзеру выдать себе premium/vip.
    """
    on_railway = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))
    stub = (
        not on_railway
        and os.getenv("BILLING_STUB", "").strip().lower() in ("1", "true", "yes")
    )
    if not stub and not user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Смена тарифа только через оплату. Напиши @Kupyansk_2 после перевода.",
        )
    if req.tier not in ('free', 'premium', 'vip'):
        raise HTTPException(status_code=400, detail="Неизвестный тариф")
    db.set_user_tier(user['id'], req.tier)
    return {"ok": True, "tier": req.tier}


# ── Трейдеры и ручные сигналы (ТВХ от людей) ──────────────────────
@app.get("/api/traders")
def list_traders():
    """Публичный список трейдеров с честной статистикой (считается вживую из history)."""
    return db.list_traders(only_active=True)


@app.post("/api/admin/traders")
def admin_create_trader(req: TraderCreate, admin=Depends(require_admin)):
    trader_id = db.create_trader(req.name, req.avatar_url, req.bio)
    return db.get_trader(trader_id)


@app.get("/api/admin/traders")
def admin_list_traders(admin=Depends(require_admin)):
    return db.list_traders(only_active=False)


class GrantPremiumRequest(BaseModel):
    email: str
    days: int = 30
    tier: str = "premium"


@app.post("/api/admin/grant-premium")
def admin_grant_premium(req: GrantPremiumRequest, background_tasks: BackgroundTasks, admin=Depends(require_admin)):
    """Выдать Premium по email (админка сайта).

    Если у юзера уже привязан Telegram (через кнопку «Подключить Telegram»
    в личном кабинете или прошлый /paid), invite-ссылки на закрытые каналы
    уходят ему в бота сразу — без отдельного /grant в самом боте."""
    email = (req.email or "").lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Укажи корректный email")
    days = max(1, min(int(req.days or 30), 3650))
    tier = (req.tier or "premium").lower().strip()
    if tier not in ("premium", "vip", "free"):
        raise HTTPException(status_code=400, detail="Тариф: free / premium / vip")

    user = db.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail=f"Пользователь {email} не найден. Пусть сначала зарегистрируется на сайте.")

    if tier == "free":
        db.set_user_tier(user["id"], "free")
        with db.get_conn() as conn:
            conn.execute("UPDATE users SET premium_until=NULL WHERE id=?", (user["id"],))
        pending = db.get_pending_premium_request(email=email)
        if pending:
            db.resolve_premium_request(pending["id"], "cancelled")
        return {"ok": True, "email": email, "tier": "free", "premium_until": None}

    until = db.grant_premium(user["id"], days=days)
    if tier == "vip":
        db.set_user_tier(user["id"], "vip")
    pending = db.get_pending_premium_request(email=email)
    if pending:
        db.resolve_premium_request(pending["id"], "granted")
    if user.get("telegram_id"):
        background_tasks.add_task(
            telegram_bot.notify_telegram_id_premium_ready, user["telegram_id"], email, until)
    return {
        "ok": True,
        "email": email,
        "tier": tier if tier == "vip" else "premium",
        "premium_until": until,
        "user_id": user["id"],
    }


@app.post("/api/telegram/link-token")
def telegram_link_token(user=Depends(require_user)):
    """Токен для кнопки «Подключить Telegram» в личном кабинете: открывает
    бота, привязывает Telegram-аккаунт к сайту и, если Premium уже активен,
    сразу выдаёт invite-ссылки в закрытые каналы с ТВХ."""
    token = secrets.token_urlsafe(24)
    expires_at = (datetime.now() + timedelta(minutes=30)).isoformat()
    db.create_auth_token(token, user["id"], "tg_link", expires_at)
    return {"token": token, "bot_url": telegram_bot.build_telegram_link_deeplink(token)}


class ChatEngageTestRequest(BaseModel):
    target: str = "Kupyansk_2"
    # symbol/signal/entry/pnl не задаём по умолчанию — если не передали явно,
    # chat_engage сам выбирает случайную монету/сторону/% для практики.
    symbol: str | None = None
    signal: str | None = None
    entry: float | None = None
    pnl: float | None = None
    exit_price: float | None = None


@app.post("/api/admin/chat-engage-test")
def admin_chat_engage_test(req: ChatEngageTestRequest, admin=Depends(require_admin)):
    """Практика: карточка профита + текст контакту/чату (по умолчанию Kupyansk_2).

    Без явных symbol/signal/entry/pnl каждый вызов даёт случайную монету и %.
    """
    import chat_engage
    side = None
    if req.signal:
        side = req.signal.upper().strip()
        if side not in ("LONG", "SHORT"):
            raise HTTPException(status_code=400, detail="signal: LONG или SHORT")
    ok, msg = chat_engage.fire_practice_profit(
        target=req.target or "Kupyansk_2",
        symbol=req.symbol,
        side=side,
        entry=req.entry,
        pnl=req.pnl,
        exit_price=req.exit_price,
    )
    if not ok:
        raise HTTPException(status_code=503, detail=msg)
    return {"ok": True, "detail": msg, "target": (req.target or "Kupyansk_2").lstrip("@")}


@app.get("/api/admin/chat-style-stats")
def admin_chat_style_stats(admin=Depends(require_admin)):
    return {
        "total": db.count_chat_style_samples(),
        "sources": ["BinanceRussianSpeaking", "cryptoinside_chat", "tg_chat_backup"],
        "note": "Сэмплы качаются один раз при старте (если пусто). Повторно — только через /api/admin/chat-style-refresh.",
    }


@app.post("/api/admin/chat-style-refresh")
async def admin_chat_style_refresh(admin=Depends(require_admin)):
    """Принудительно скачать свежие реплики из крипто-чатов-учителей."""
    import chat_engage
    # refresh идёт через уже живой telethon-клиент chat_engage
    client = getattr(chat_engage, "_live_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="chat_engage клиент ещё не онлайн — подожди деплой/старт",
        )
    stats = await chat_engage._refresh_style_samples(client, force=True)
    return stats


@app.post("/api/admin/backfill-channel-history")
def admin_backfill_channel_history(
    background_tasks: BackgroundTasks,
    limit: int | None = None,
    reset: bool = False,
    admin=Depends(require_admin),
):
    """Публикует ещё не отправленную историю закрытых сделок в публичный канал
    результатов (папаяqq). Идемпотентно — помнит id последней отправленной
    записи, повторный вызов шлёт только новое (reset=true — перепостить всё).
    Крупные минусы отфильтровываются автоматически (telegram_bot.PUBLIC_CHANNEL_MAX_LOSS_PCT).
    Работает в фоне — между постами пауза 2.5-5.5с, чтобы не спамить канал."""
    import asyncio
    import backfill_telegram

    def _run():
        asyncio.run(backfill_telegram.run_backfill(limit=limit, reset=reset))

    background_tasks.add_task(_run)
    return {
        "ok": True,
        "detail": "Бэкфилл запущен в фоне — сообщения появятся в канале постепенно.",
    }


@app.get("/api/admin/premium-requests")
def admin_premium_requests(admin=Depends(require_admin)):
    """Последние заявки «Я оплатил» из Telegram-бота."""
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT id, telegram_id, email, created_at, status
               FROM premium_requests ORDER BY id DESC LIMIT 30"""
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/admin/users")
def admin_list_users(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    tier: str | None = None,
    admin=Depends(require_admin),
):
    """CRM-lite: список пользователей (поиск по email, фильтр free/premium/unverified)."""
    tier_filter = (tier or "").strip().lower() or None
    if tier_filter and tier_filter not in ("free", "premium", "unverified"):
        raise HTTPException(status_code=400, detail="tier: free | premium | unverified")
    users = db.list_users(limit=limit, offset=offset, q=q, tier_filter=tier_filter)
    return {"users": users, "limit": limit, "offset": offset}


@app.get("/api/admin/channel-daily")
def admin_channel_daily(days: int = 14, admin=Depends(require_admin)):
    """История по каналам: сколько сделок за день и сколько в плюс."""
    return db.channel_daily_stats(days=days)


@app.post("/api/admin/add-signal")
def admin_add_signal(req: AddSignalRequest, background_tasks: BackgroundTasks, admin=Depends(require_admin)):
    trader = db.get_trader(req.trader_id)
    if not trader:
        raise HTTPException(status_code=404, detail="Трейдер не найден")

    signal = req.signal.upper().strip()
    if signal not in ('LONG', 'SHORT'):
        raise HTTPException(status_code=400, detail="signal должен быть LONG или SHORT")

    symbol, err = open_signal(
        req.symbol, signal, req.entry, req.stop, req.tp1, req.tp2, req.tp3,
        trader_id=req.trader_id, regime="manual",
        reasons=[req.note] if req.note else None,
    )
    if err == 'already_open':
        raise HTTPException(status_code=409, detail=f"По {normalize_symbol(req.symbol)} уже есть открытая позиция")
    if err == 'invalid_levels':
        detail = ("Для LONG: stop < entry < tp1 < tp2 < tp3" if signal == 'LONG'
                  else "Для SHORT: stop > entry > tp1 > tp2 > tp3")
        raise HTTPException(status_code=400, detail=detail)

    db.add_event(symbol, 'manual_signal', f"Новый сигнал от {trader['name']}: {signal} {symbol} @ {req.entry}")
    opened = db.get_trade(symbol) or {}
    background_tasks.add_task(telegram_bot.notify_manual_signal, {
        "symbol": symbol, "signal": signal,
        "entry": req.entry, "stop": req.stop,
        "tp1": req.tp1, "tp2": req.tp2, "tp3": req.tp3,
        "exchange": opened.get("exchange") or "bybit",
        "listed_on": opened.get("listed_on") or opened.get("exchange") or "bybit",
    }, trader['name'])
    try:
        import chat_engage
        chat_engage.fire_open(symbol, signal, req.entry)
    except Exception as e:
        print(f"chat_engage open: {e}")
    return {"ok": True, "symbol": symbol, "trader": trader['name']}


# ── AI (OpenRouter главный; Groq/Anthropic — fallback) ───────────────

GROQ_API_KEY = ai_client.GROQ_API_KEY  # legacy alias
AI_MODEL = ai_client.MODEL_CHAT
AI_DAILY_LIMITS = {'free': 5, 'premium': 50, 'vip': 200}
CHART_DAILY_LIMITS = {'free': 2, 'premium': 15, 'vip': 40}
_ai_usage: dict[int, dict] = {}   # user_id -> {'date': 'YYYY-MM-DD', 'count': int}
_chart_usage: dict[int, dict] = {}

CHART_ANALYZE_SYSTEM = """Ты — обычный трейдер-приятель в чате NOWICKI. Смотришь скрин графика
(Bybit / Binance / TradingView, в т.ч. с iPhone) и коротко говоришь, как сам видишь картину.

ТОН: просто, по-человечески, без официоза и канцелярита.
Пиши как в Telegram: коротко, живо, можно «я бы», «тут скорее», «мне так видится».
Не пиши «desk analyst», «конfluence», «инвалидация сетапа» — говори простыми словами.

ПРАВИЛА:
1. Только то, что видно на картинке. Не выдумывай цены/уровни/индикаторы.
2. Сам прочитай со скрина тикер/монету и таймфрейм (заголовок, угол графика, UI биржи) —
   заполни symbol и timeframe. Если не читается — null, не угадывай.
3. Кнопки «Лонг/Шорт» внизу приложения — просто UI биржи, не сигнал.
4. Если скрин мутный / нет графика — bias=flat, evidence_ok=false, честно скажи что не разобрать.
5. Не обещай прибыль, иксы, «100%», «обязательно зайдёт».
6. long/short только если есть хотя бы 2 понятных аргумента с картинки.
7. Язык ответа = language пользователя (иначе русский).
8. bias только: long | short | flat.

В поле take обязательно напиши личное мнение одной-двумя фразами, например:
- «Я бы тут взял лонг, пока держится выше …»
- «Я бы скорее шортнул отбой от …»
- «Я бы пока не лез — картинка мутная / лучше подождать»

Верни ТОЛЬКО JSON:
{
  "evidence_ok": bool,
  "symbol": string|null,
  "timeframe": string|null,
  "price_hint": string|null,
  "bias": "long"|"short"|"flat",
  "confidence": "low"|"medium"|"high",
  "take": string,
  "seen": [string],
  "reasons": [string],
  "invalidation": string,
  "risks": [string],
  "watch": [string],
  "disclaimer": string
}

seen / reasons / risks / watch — короткие простые фразы (не отчёт).
invalidation — где идея ломается, простыми словами.
disclaimer — одна короткая фраза вроде: «это мой взгляд на скрин, не сигнал».
"""


class ChartAnalyzeRequest(BaseModel):
    image_base64: str
    media_type: str = "image/jpeg"
    symbol_hint: str | None = None
    timeframe_hint: str | None = None
    question: str | None = None
    language: str | None = None


def _chart_quota(user_id: int, tier: str) -> tuple[dict, int]:
    limit = CHART_DAILY_LIMITS.get(tier, CHART_DAILY_LIMITS['free'])
    today = datetime.now().strftime('%Y-%m-%d')
    usage = _chart_usage.get(user_id)
    if not usage or usage['date'] != today:
        usage = {'date': today, 'count': 0}
    return usage, limit


def _default_take(bias: str, lang: str = "ru") -> str:
    lang = (lang or "ru")[:2].lower()
    if lang == "en":
        return {
            "long": "I'd take a long here if the structure holds.",
            "short": "I'd rather short this if rejection holds.",
            "flat": "I wouldn't enter yet — wait for a clearer picture.",
        }[bias]
    if lang == "pl":
        return {
            "long": "Ja bym wziął longa, jeśli struktura się utrzyma.",
            "short": "Ja bym raczej shortował przy odrzuceniu.",
            "flat": "Ja bym jeszcze nie wchodził — poczekaj na czytelniejszy obraz.",
        }[bias]
    return {
        "long": "Я бы тут взял лонг, если структура держится.",
        "short": "Я бы скорее взял шорт, если отбой подтвердится.",
        "flat": "Я бы пока не лез — лучше подождать более чистую картинку.",
    }[bias]


def _normalize_chart_result(raw: dict, lang: str = "ru") -> dict:
    bias = str(raw.get('bias') or 'flat').lower().strip()
    if bias in ('bullish', 'buy', 'long'):
        bias = 'long'
    elif bias in ('bearish', 'sell', 'short'):
        bias = 'short'
    elif bias not in ('long', 'short', 'flat'):
        bias = 'flat'
    conf = str(raw.get('confidence') or 'low').lower().strip()
    try:
        cnum = float(conf)
        conf = 'high' if cnum >= 0.75 else 'medium' if cnum >= 0.45 else 'low'
    except Exception:
        pass
    if conf not in ('low', 'medium', 'high'):
        conf = 'low'
    evidence_ok = bool(raw.get('evidence_ok'))
    reasons = [str(x).strip() for x in (raw.get('reasons') or []) if str(x).strip()][:5]
    seen = [str(x).strip() for x in (raw.get('seen') or []) if str(x).strip()][:6]
    risks = [str(x).strip() for x in (raw.get('risks') or []) if str(x).strip()][:4]
    watch = [str(x).strip() for x in (raw.get('watch') or []) if str(x).strip()][:4]

    if not evidence_ok or len(reasons) < 2:
        if bias in ('long', 'short') and (not evidence_ok or len(reasons) < 2):
            bias = 'flat'
            conf = 'low'

    take = (raw.get('take') or '').strip()
    if not take:
        take = _default_take(bias, lang)
    # если после нормализации ушли в flat — подмени take
    if bias == 'flat' and any(w in take.lower() for w in ('лонг', 'шорт', 'long', 'short')):
        # оставим take модели, если она сама сказала «не лез»; иначе дефолт
        if not any(w in take.lower() for w in ('не лез', 'подожд', "wouldn't", 'wait', 'nie wchod', 'poczek')):
            take = _default_take('flat', lang)

    disclaimer = (raw.get('disclaimer') or '').strip() or (
        "Это просто взгляд на скрин, не торговый сигнал."
    )
    inv = (raw.get('invalidation') or '').strip() or "на скрине не видно, где идея ломается"
    return {
        "evidence_ok": evidence_ok,
        "symbol": raw.get('symbol') or None,
        "timeframe": raw.get('timeframe') or None,
        "price_hint": raw.get('price_hint') or None,
        "bias": bias,
        "confidence": conf,
        "take": take[:400],
        "seen": seen,
        "reasons": reasons,
        "invalidation": inv,
        "risks": risks,
        "watch": watch,
        "disclaimer": disclaimer[:240],
    }


@app.post("/api/ai/chart-analyze")
async def ai_chart_analyze(req: ChartAnalyzeRequest, authorization: str | None = Header(default=None)):
    """Разбор скриншота графика: структурированный bias, не «сигнал»."""
    import base64
    import re as _re

    user = auth.user_from_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Войди в аккаунт, чтобы разобрать график")
    if not ai_client.fast_configured():
        raise HTTPException(status_code=503, detail="Разбор графика временно недоступен")

    tier = auth.effective_tier(user)
    usage, limit = _chart_quota(user['id'], tier)
    if usage['count'] >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Дневной лимит разборов графика исчерпан ({limit}/день на тарифе {tier}).",
        )

    media = (req.media_type or "image/jpeg").split(";")[0].strip().lower()
    # iPhone часто шлёт пустой type / heic / image/jpg
    if media in ("", "application/octet-stream", "image/heic", "image/heif", "image/jpg"):
        media = "image/jpeg"
    if media not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        raise HTTPException(status_code=400, detail="Нужен JPEG, PNG, WebP или скрин из Фото")
    if media == "image/gif":
        media = "image/jpeg"

    raw_b64 = (req.image_base64 or "").strip()
    if "," in raw_b64 and raw_b64.lower().startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[1]
    raw_b64 = _re.sub(r"\s+", "", raw_b64)
    if not raw_b64:
        raise HTTPException(status_code=400, detail="Пустое изображение")
    try:
        image_bytes = base64.b64decode(raw_b64, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный base64 изображения")
    if len(image_bytes) < 400:
        raise HTTPException(status_code=400, detail="Файл слишком маленький")
    if len(image_bytes) > 6_000_000:
        raise HTTPException(status_code=400, detail="Файл слишком большой (сжми скрин)")

    # Всегда в JPEG через Pillow — стабильнее для Haiku на мобильных скринах
    image_bytes, media = ai_client.normalize_image_bytes(image_bytes, media)
    if len(image_bytes) > 2_800_000:
        raise HTTPException(status_code=400, detail="После сжатия файл всё ещё слишком большой")

    lang = (req.language or "ru").strip().lower()[:5]
    caption_parts = [
        f"language={lang}",
        "Посмотри скрин просто и по-человечески.",
        "В take напиши: я бы взял лонг / шорт / пока не лез — смотря по картинке.",
        "Это может быть мобильный скрин Bybit/Binance/TradingView с iPhone.",
        "Кнопки Лонг/Шорт внизу экрана — UI, не сигнал.",
    ]
    if req.symbol_hint:
        caption_parts.append(f"user_symbol_hint={req.symbol_hint.strip()[:32]}")
    if req.timeframe_hint:
        caption_parts.append(f"user_timeframe_hint={req.timeframe_hint.strip()[:16]}")
    if req.question:
        caption_parts.append(f"user_question={req.question.strip()[:300]}")

    try:
        raw = await ai_client.vision_json_completion(
            system=CHART_ANALYZE_SYSTEM,
            image_bytes=image_bytes,
            caption="\n".join(caption_parts),
            max_tokens=1100,
            media_type=media,
            require_ingest_flag=False,
        )
    except Exception as e:
        print(f"[chart_analyze] error: {e}")
        raise HTTPException(
            status_code=502,
            detail="Не удалось разобрать этот скрин. Попробуй ещё раз или сохрани как JPEG из Фото.",
        )

    result = _normalize_chart_result(raw if isinstance(raw, dict) else {}, lang=lang)
    if req.symbol_hint and not result.get("symbol"):
        result["symbol"] = req.symbol_hint.strip()[:32]
    if req.timeframe_hint and not result.get("timeframe"):
        result["timeframe"] = req.timeframe_hint.strip()[:16]

    usage['count'] += 1
    _chart_usage[user['id']] = usage
    try:
        database.grant_chart_vote_pending(user['id'])
    except Exception as e:
        print(f"[chart_analyze] vote pending: {e}")
    return {
        "analysis": result,
        "used": usage['count'],
        "limit": limit,
        "can_vote": True,
    }


class ChartHelpVoteRequest(BaseModel):
    helped: bool


@app.get("/api/chart-reviews")
def get_chart_reviews(limit: int = 40, authorization: str | None = Header(default=None)):
    try:
        database._seed_chart_reviews_if_needed()
        database._ensure_chart_vote_baseline()
    except Exception:
        pass
    user = current_user(authorization)
    uid = user["id"] if user else None
    return {
        "stats": database.chart_review_stats(user_id=uid),
        "reviews": database.list_chart_reviews(limit=limit),
    }


@app.post("/api/chart-reviews/vote")
def post_chart_help_vote(req: ChartHelpVoteRequest, user=Depends(require_user)):
    try:
        stats = database.cast_chart_help_vote(user["id"], bool(req.helped))
    except ValueError as e:
        if str(e) == "need_analysis":
            raise HTTPException(
                400,
                "Сначала загрузи скрин и получи разбор — потом можно поставить плюс или минус",
            )
        raise HTTPException(400, str(e))
    return {"ok": True, "stats": stats}


class AIChatRequest(BaseModel):
    messages: list[dict]


def _ai_strategy_knowledge() -> str:
    return (
        "NOWICKI: сигналы приходят из внешних каналов / ручного ввода / webhook "
        "(не собственный автопоиск монет). Трекер ведёт TP/стоп/BE по открытым сделкам. "
        "Можешь кратко говорить про уровни, R:R, инвалидацию — без лекций."
    )


def _ai_market_context() -> str:
    """Короткий живой промпт + урезанные данные (быстрее и менее шаблонно)."""
    lines = [
        "Ты — Nick с NOWICKI. Пишешь как живой трейдер в терминале: коротко, по-человечески, без канцелярита.",
        "Не AI-помощник и не «desk analyst» в каждом абзаце.",
        "",
        "СТИЛЬ:",
        "- Отвечай как в чате/терминале: короткие фразы, можно «хм», «смотри», «короче».",
        "- Никаких шаблонов Bias / Setup / Invalidation / Risk / Watch и маркированных простыней без нужды.",
        "- Простой вопрос → 1–4 коротких строки. Разбор → живым текстом, не чеклистом.",
        "- Не начинай одинаково («Конечно!», «Отличный вопрос», «Давай разберём»).",
        "- Язык ответа = язык последнего сообщения пользователя.",
        "",
        "ПРАВИЛА:",
        "- Не обещай прибыль / 100%. Не «покупай всё».",
        "- Не выдумывай цены и сигналы вне блока ДАННЫЕ.",
        "- Нет данных — скажи прямо.",
        "",
        _ai_strategy_knowledge(),
        "",
        "═══ ДАННЫЕ ═══",
    ]

    try:
        ov = data_layer.get_market_overview()
        if ov:
            lines.append(
                f"режим BTC={ov.get('btc_regime')} | "
                f"up={ov.get('uptrend_count')} dn={ov.get('downtrend_count')} chop={ov.get('chop_count')}"
            )
            syms = ov.get('symbols') or []
            hot = sorted(
                [s for s in syms if s.get('regime') in ('UPTREND', 'DOWNTREND')],
                key=lambda s: -float(s.get('adx') or 0),
            )[:6]
            if hot:
                lines.append("горячие: " + ", ".join(
                    f"{s['symbol'].replace('/USDT','')} {s.get('regime')} ADX={s.get('adx')}"
                    for s in hot
                ))
    except Exception:
        pass

    try:
        trades = db.load_trades()
        if trades:
            lines.append(f"открыто: {len(trades)}")
            for sym, t in list(trades.items())[:6]:
                entry = float(t.get('entry') or 0)
                stop = float(t.get('stop') or 0)
                tp1 = float(t.get('tp1') or 0)
                risk_pct = abs(entry - stop) / entry * 100 if entry else 0
                reward_pct = abs(tp1 - entry) / entry * 100 if entry else 0
                rr = (reward_pct / risk_pct) if risk_pct else 0
                lines.append(
                    f"• {sym} {t.get('signal')} e={t.get('entry')} sl={t.get('stop')} "
                    f"tp1={t.get('tp1')} R:R≈{rr:.2f} regime={t.get('regime')}"
                )
        else:
            lines.append("открытых сигналов нет")
    except Exception:
        pass

    try:
        stats = db.get_stats_summaries()
        w = stats.get('week') or {}
        lines.append(
            f"неделя: wr={w.get('winrate')} trades={w.get('total')} pnl={w.get('total_pnl')}"
        )
    except Exception:
        pass

    try:
        hist = db.load_history(limit=6)
        if hist:
            parts = [
                f"{h.get('symbol')} {h.get('result')} {h.get('pnl')}"
                for h in hist[:6]
            ]
            lines.append("закрытия: " + " | ".join(parts))
    except Exception:
        pass

    lines.append("═══ END ═══")
    return "\n".join(lines)


def _ai_chat_prepare(req: AIChatRequest, authorization: str | None):
    """Общая подготовка: auth, лимит, сообщения. Возвращает (user, msgs, usage, limit)."""
    user = auth.user_from_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Войди в аккаунт, чтобы пользоваться AI-ассистентом")
    if not ai_client.chat_configured():
        raise HTTPException(status_code=503, detail="AI-ассистент временно недоступен")

    tier = auth.effective_tier(user)
    limit = AI_DAILY_LIMITS.get(tier, AI_DAILY_LIMITS['free'])
    today = datetime.now().strftime('%Y-%m-%d')
    usage = _ai_usage.get(user['id'])
    if not usage or usage['date'] != today:
        usage = {'date': today, 'count': 0}
    if usage['count'] >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Дневной лимит AI-запросов исчерпан ({limit}/день на тарифе {tier}). "
                   f"Лимит обновится завтра.",
        )

    msgs = []
    for m in req.messages[-12:]:
        role = m.get('role')
        content = m.get('content')
        if role in ('user', 'assistant') and isinstance(content, str):
            msgs.append({'role': role, 'content': content[:4000]})
    if not msgs or msgs[-1]['role'] != 'user':
        raise HTTPException(status_code=400, detail="Некорректный формат сообщений")

    msgs.insert(0, {'role': 'system', 'content': _ai_market_context()})
    return user, msgs, usage, limit


def _ai_chat_payload(msgs: list, *, stream: bool = False) -> dict:
    # Flash-lite быстрее; chat model если явно задан через env
    model = os.getenv("OPENROUTER_MODEL_CHAT") or ai_client.MODEL_FAST or AI_MODEL
    return {
        'model': model,
        'max_tokens': 420,
        'temperature': 0.75,
        'messages': msgs,
        'stream': stream,
    }


@app.post("/api/ai/chat")
def ai_chat(req: AIChatRequest, authorization: str | None = Header(default=None)):
    user, msgs, usage, limit = _ai_chat_prepare(req, authorization)

    payload = json.dumps(_ai_chat_payload(msgs, stream=False)).encode()
    request = urllib.request.Request(
        ai_client.openai_chat_url(),
        data=payload,
        headers=ai_client.openai_auth_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get('error', {}).get('message', str(e))
        except Exception:
            err = str(e)
        raise HTTPException(status_code=502, detail=f"Ошибка AI-провайдера: {err}")
    except Exception:
        raise HTTPException(status_code=502, detail="AI-провайдер не отвечает, попробуй позже")

    reply = (data.get('choices') or [{}])[0].get('message', {}).get('content') or 'Не удалось получить ответ'
    usage['count'] += 1
    _ai_usage[user['id']] = usage
    return {"reply": reply, "used": usage['count'], "limit": limit}


@app.post("/api/ai/chat/stream")
async def ai_chat_stream(req: AIChatRequest, authorization: str | None = Header(default=None)):
    """SSE: токены по мере генерации — на фронте печатается как код."""
    from fastapi.responses import StreamingResponse
    import httpx

    user, msgs, usage, limit = _ai_chat_prepare(req, authorization)
    body = _ai_chat_payload(msgs, stream=True)
    url = ai_client.openai_chat_url()
    headers = ai_client.openai_auth_headers()

    async def event_gen():
        full = []
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code >= 400:
                        err_txt = (await resp.aread()).decode("utf-8", errors="replace")[:400]
                        yield f"data: {json.dumps({'error': err_txt or 'provider error'}, ensure_ascii=False)}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                        except Exception:
                            continue
                        delta = ((chunk.get("choices") or [{}])[0].get("delta") or {})
                        token = delta.get("content") or ""
                        if token:
                            full.append(token)
                            yield f"data: {json.dumps({'t': token}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:200]}, ensure_ascii=False)}\n\n"
            return

        usage['count'] += 1
        _ai_usage[user['id']] = usage
        yield f"data: {json.dumps({'done': True, 'used': usage['count'], 'limit': limit}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ── API endpoints ────────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        with db.get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"ok": True, "db": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"db unavailable: {e}")


@app.get("/api/signals")
def get_active_signals(authorization: str | None = Header(default=None)):
    """Открытые сигналы. Уровни entry/stop/TP — только Premium/VIP/admin.
    Free и гости видят символ/сторону/график, но уровни затёрты."""
    user = current_user(authorization)
    can_see_levels = False
    if user:
        tier = auth.effective_tier(user)
        can_see_levels = bool(user.get("is_admin")) or auth.tier_allows(tier, "premium")

    trades = db.load_trades()
    trader_ids = {t.get('trader_id') for t in trades.values() if t.get('trader_id')}
    traders_by_id = db.get_traders_by_ids(trader_ids)
    out = []
    for symbol, t in trades.items():
        ex = (t.get('exchange') or 'bybit').lower().strip()
        candles = []
        # Свежие OHLCV с биржи (кэш ~15с), иначе fallback на снимок в БД
        try:
            cj = data_layer.fetch_candles_json(symbol, exchange_id=ex)
            if cj:
                candles = json.loads(cj)
        except Exception:
            candles = []
        if not candles and t.get('candles_json'):
            try:
                candles = json.loads(t['candles_json'])
            except (TypeError, json.JSONDecodeError):
                candles = []

        live_price = None
        try:
            ticker = data_layer.fetch_ticker(symbol, ex)
            if ticker and ticker.get('last') is not None:
                live_price = float(ticker['last'])
                if candles:
                    last = dict(candles[-1])
                    last['close'] = live_price
                    last['high'] = max(float(last.get('high') or live_price), live_price)
                    last['low'] = min(float(last.get('low') or live_price), live_price)
                    candles = list(candles[:-1]) + [last]
        except Exception:
            pass

        entry_reasons = json.loads(t['entry_reasons_json']) if t.get('entry_reasons_json') else []
        trader = traders_by_id.get(t.get('trader_id'))
        item = {
            "symbol": symbol,
            "signal": t['signal'],
            "entry": t['entry'] if can_see_levels else None,
            "stop":  t['stop'] if can_see_levels else None,
            "tp1": t['tp1'] if can_see_levels else None,
            "tp2": t['tp2'] if can_see_levels else None,
            "tp3": t['tp3'] if can_see_levels else None,
            "levels_locked": not can_see_levels,
            "score": t.get('score'),
            "regime": t.get('regime'),
            "exit_mode": t.get('exit_mode') or 'ladder',
            "tp1_hit": bool(t.get('tp1_hit')) if can_see_levels else False,
            "tp2_hit": bool(t.get('tp2_hit')) if can_see_levels else False,
            "be_hit":  bool(t.get('be_hit')) if can_see_levels else False,
            "opened_at": t.get('opened_at'),
            "candles": candles,
            "live_price": live_price,
            "entry_reasons": entry_reasons if can_see_levels else [],
            "position_size": t.get('position_size') if can_see_levels else None,
            "exchange": t.get('exchange') or 'bybit',
            "listed_on": t.get('listed_on') or (t.get('exchange') or 'bybit'),
            "trader": {"id": trader['id'], "name": trader['name'], "avatar_url": trader.get('avatar_url'), "source_type": trader.get('source_type')} if trader else None,
        }
        out.append(item)
    return out


@app.get("/api/ingest/health")
def ingest_health(admin=Depends(require_admin)):
    """Статус ingest по каналам — тишина, дневные лимиты, ошибки."""
    return telegram_ingest.ingest_health_snapshot()


@app.post("/api/admin/sentry-test-error")
def admin_sentry_test_error(admin=Depends(require_admin)):
    """Искусственная ошибка для проверки Sentry → AI triage (только admin).

    Вызывает необработанное исключение — Sentry SDK должен создать Issue.
    В проде используй редко, только для smoke-теста пайплайна.
    """
    raise RuntimeError(
        "NOWICKI_SENTRY_TEST: intentional admin test error "
        f"(by user_id={admin.get('id')})"
    )


_stats_cache = {"ts": 0.0, "data": None}
_STATS_TTL_SEC = 45


@app.get("/api/stats")
def get_stats():
    now = _time.time()
    cached = _stats_cache["data"]
    if cached is not None and (now - _stats_cache["ts"]) < _STATS_TTL_SEC:
        return cached
    data = db.get_stats_summaries()
    # Витрина сайта = лента @papayaqq (те же фильтры, без крупных минусов).
    pub30 = public_feed.load_channel_feed(limit=500, days=30)
    data["month"] = public_feed.summarize_trades(pub30)
    pub7 = [t for t in pub30 if t.get("date", "") >= (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")]
    data["week"] = public_feed.summarize_trades(pub7)
    _stats_cache["ts"] = now
    _stats_cache["data"] = data
    return data


def _summarize(trades):
    if not trades:
        return {"total": 0, "winrate": 0, "tp1": 0, "tp2_plus": 0,
                "stops": 0, "breakeven": 0, "total_pnl": 0, "avg_pnl": 0,
                "best": None, "worst": None}
    total     = len(trades)
    wins      = sum(1 for t in trades if t['pnl'] > 0)
    losses    = sum(1 for t in trades if t['result'] == 'sl')
    bes       = sum(1 for t in trades if t['result'] in ('be', 'potential'))
    tp1s      = sum(1 for t in trades if t['result'] == 'tp1')
    total_pnl = sum(t['pnl'] for t in trades)
    best      = max(trades, key=lambda x: x['pnl'])
    worst     = min(trades, key=lambda x: x['pnl'])
    return {
        "total": total,
        "winrate": round(wins / total * 100, 1),
        "tp1": tp1s,
        "tp2_plus": wins - tp1s,
        "stops": losses,
        "breakeven": bes,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2),
        "best":  {"symbol": best['symbol'],  "pnl": best['pnl']},
        "worst": {"symbol": worst['symbol'], "pnl": worst['pnl']},
    }


@app.get("/api/strategies/summary")
def get_strategies_summary():
    """
    Единое честное сравнение всех бумажных стратегий на живых данных.
    Метрики у стратегий считаются по-разному (разная механика), поэтому
    подписаны явно. Все — независимые бумажные (paper), edge не доказан.
    """
    import xsec_strategy, trend_strategy

    out = []

    # 1) Momentum (высокочастотный сканер)
    hist = db.load_history(limit=5000)
    open_m = db.load_trades()
    if hist:
        wins = sum(1 for t in hist if t['pnl'] > 0)
        out.append({
            "key": "momentum", "name": "Momentum", "kind": "Высокочастотная",
            "realized_pnl_pct": round(sum(t['pnl'] for t in hist), 2),
            "closed_trades": len(hist),
            "winrate": round(wins / len(hist) * 100, 1),
            "open_positions": len(open_m),
            "metric_note": "сумма % по сделкам (позиц. сайзинг)",
        })
    else:
        out.append({"key": "momentum", "name": "Momentum", "kind": "Высокочастотная",
                    "realized_pnl_pct": 0, "closed_trades": 0, "winrate": 0,
                    "open_positions": len(open_m), "metric_note": "ещё нет закрытых сделок"})

    # 2) Long-Short (cross-sectional, market-neutral)
    xst = xsec_strategy.get_status()
    xlog = db.xsec_load_log(limit=500)
    out.append({
        "key": "xsec", "name": "Long-Short", "kind": "Рыночно-нейтральная",
        "realized_pnl_pct": round((xst.get('equity', 1000) / xsec_strategy.XSEC_DEPOSIT - 1) * 100, 2),
        "closed_trades": len(xlog),
        "winrate": None,
        "open_positions": len(xst.get('positions', [])),
        "metric_note": "compounded equity (нейтральный портфель)",
    })

    # 3) Trend-Following
    tst = trend_strategy.get_status()
    out.append({
        "key": "trend", "name": "Trend-Following", "kind": "Защита от просадок",
        "realized_pnl_pct": tst.get('total_realized_pnl_pct', 0),
        "closed_trades": tst.get('closed_trades', 0),
        "winrate": round(tst['wins'] / tst['closed_trades'] * 100, 1) if tst.get('closed_trades') else None,
        "open_positions": len(tst.get('positions', [])),
        "metric_note": "сумма % по сделкам (long/cash)",
    })

    return {"strategies": out,
            "note": "Бумажные независимые стратегии. Метрики посчитаны по-разному — сравнивать с осторожностью. Edge не доказан, нужен дальран."}


@app.get("/api/history")
def get_history(limit: int = 500, days: int | None = 30):
    """История на сайте = сделки витрины @papayaqq (профит + небольшой минус)."""
    return public_feed.load_channel_feed(limit=limit, days=days)


@app.get("/api/events")
def get_events(limit: int = 50):
    return db.load_events(limit=limit)


@app.get("/api/dryrun/status")
def get_dryrun_status():
    open_trades = db.load_trades()
    risk = get_risk_status()
    return {
        **risk,
        "open_trades_count": len(open_trades),
        "max_open_trades": MAX_OPEN_TRADES,
    }


@app.get("/api/dryrun/open")
def get_dryrun_open():
    """Открытые сделки с live-ценой и unrealized PnL% — для дашборда дальрана."""
    trades = db.load_trades()
    out = []
    for symbol, t in trades.items():
        try:
            ticker = api_call(exchange.fetch_ticker, symbol) or {}
            price = ticker.get('last', t['entry'])
        except Exception:
            price = t['entry']
        signal = t['signal']
        pnl_pct = ((price - t['entry']) / t['entry'] * 100) if signal == 'LONG' \
            else ((t['entry'] - price) / t['entry'] * 100)
        regime = t.get('regime')
        is_time_exit = regime == 'MOMENTUM'  # TP недостижимы по дизайну — выход по таймауту
        out.append({
            "symbol": symbol, "signal": signal, "entry": t['entry'], "price": price,
            "stop": t['stop'],
            "tp1": None if is_time_exit else t['tp1'],
            "tp2": None if is_time_exit else t['tp2'],
            "tp3": None if is_time_exit else t['tp3'],
            "time_exit": is_time_exit,
            "regime": regime,
            "tp1_hit": bool(t.get('tp1_hit')), "be_hit": bool(t.get('be_hit')),
            "pnl_pct": round(pnl_pct, 2),
            "opened_at": t.get('opened_at'),
            "position_size": t.get('position_size'),
            "score": t.get('score'),
        })
    return out


@app.get("/api/dryrun/breakdown")
def get_dryrun_breakdown(days: int = 30):
    """Разбивка закрытых сделок по result (sl/tp1/tp2/tp3/timeout/be) — для дашборда."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    history = [t for t in db.load_history(limit=5000) if t['date'] >= cutoff]
    by_result = {}
    cum = 0.0
    equity_curve = []
    for t in sorted(history, key=lambda x: (x['date'], x['time'])):
        r = t['result']
        if r not in by_result:
            by_result[r] = {"count": 0, "sum_pnl": 0.0}
        by_result[r]["count"] += 1
        by_result[r]["sum_pnl"] += t['pnl']
        cum += t['pnl']
        equity_curve.append({"date": t['date'], "time": t['time'], "cum_pnl": round(cum, 2),
                              "symbol": t['symbol'], "result": r, "pnl": t['pnl']})
    for r in by_result:
        by_result[r]["sum_pnl"] = round(by_result[r]["sum_pnl"], 2)
    return {
        "by_result": by_result,
        "equity_curve": equity_curve,
        "total_trades": len(history),
        "total_pnl_pct": round(cum, 2),
    }


@app.get("/api/xsec/status")
def get_xsec_status():
    """Cross-sectional momentum — портфель, equity, live-PnL."""
    import xsec_strategy
    return xsec_strategy.get_status()


@app.get("/api/xsec/history")
def get_xsec_history(limit: int = 100):
    """История ребалансов + кривая equity."""
    log = db.xsec_load_log(limit=limit)
    log_sorted = sorted(log, key=lambda r: r['id'])
    return {
        "rebalances": log,
        "equity_curve": [{"date": r['date'], "equity": r['equity']} for r in log_sorted],
    }


@app.get("/api/xsec/ranking")
def get_xsec_ranking():
    """Текущий рейтинг всей вселенной по momentum (для прозрачности)."""
    import xsec_strategy
    r = xsec_strategy.compute_momentum_ranking()
    if r is None:
        return {"ranking": []}
    return {"ranking": [{"symbol": k, "mom_pct": round(float(v), 2)} for k, v in r.items()]}


@app.post("/api/xsec/rebalance")
def force_xsec_rebalance(admin=Depends(require_admin)):
    """Ручной запуск ребаланса (только админ)."""
    import xsec_strategy
    return xsec_strategy.rebalance(force=True)


@app.get("/api/trend/status")
def get_trend_status():
    """Trend-Following — позиции, live-PnL, текущие сигналы по всей вселенной."""
    import trend_strategy
    return trend_strategy.get_status()


@app.get("/api/trend/history")
def get_trend_history(limit: int = 100):
    """История закрытых trend-following сделок."""
    return {"trades": db.trend_load_log(limit=limit)}


@app.post("/api/trend/check")
def force_trend_check(admin=Depends(require_admin)):
    """Ручная проверка сигналов (только админ)."""
    import trend_strategy
    trend_strategy.tick()
    return trend_strategy.get_status()


@app.get("/api/market/phase")
def get_market_phase():
    """
    Индикатор фазы рынка (Up/Down/Боковик) по BTC — информационный.
    Не управляет ни одной стратегией (авто-переключение протестировано и отклонено).
    """
    import trend_strategy
    phase = trend_strategy.get_market_phase()
    if not phase:
        return {"error": "Нет данных"}
    return phase


@app.get("/api/market")
def get_market():
    try:
        btc = api_call(exchange.fetch_ticker, 'BTC/USDT') or {}
        eth = api_call(exchange.fetch_ticker, 'ETH/USDT') or {}
        overview = data_layer.get_market_overview()
        return {
            "btc": {"price": btc.get('last', 0), "change": btc.get('percentage', 0)},
            "eth": {"price": eth.get('last', 0), "change": eth.get('percentage', 0)},
            # Скринер: пока фоновый снапшот не готов — loading, фронт покажет заглушку
            **(overview or {"symbols": [], "btc_regime": "НЕТ ДАННЫХ",
                            "uptrend_count": 0, "downtrend_count": 0, "chop_count": 0,
                            "loading": True}),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/markets")
def get_all_markets_summary(force: bool = False):
    """Сводка по всем биржам: count + symbols (может быть тяжеловато при force=1)."""
    out = []
    for ex in data_layer.list_supported_exchanges():
        symbols = data_layer.get_exchange_futures_symbols(ex["id"], force=bool(force))
        out.append({
            "exchange": ex["id"],
            "name": ex["name"],
            "count": len(symbols),
            "symbols": symbols,
        })
    return {"exchanges": out}


@app.get("/api/markets/{exchange_id}")
def get_exchange_markets(exchange_id: str, force: bool = False):
    """USDT-M / swap рынки: bybit|binance|okx|bitget|bingx|bitunix."""
    eid = (exchange_id or "").lower().strip()
    if eid not in data_layer._KNOWN_EXCHANGES:
        raise HTTPException(status_code=404, detail=f"Unknown exchange: {exchange_id}")
    return _markets_payload(eid, force=bool(force))


def _markets_payload(exchange_id: str, force: bool = False):
    symbols = data_layer.get_exchange_futures_symbols(exchange_id, force=force)
    payload = {
        "exchange": exchange_id,
        "name": data_layer._EXCHANGE_LABELS.get(exchange_id, exchange_id),
        "type": "futures_usdt_m",
        "count": len(symbols),
        "symbols": symbols,
    }
    if exchange_id == "bitunix":
        import bitunix_client
        pairs = bitunix_client.load_futures_pairs(force=force)
        payload["pairs"] = [
            {
                "symbol": f"{(p.get('base') or '').upper()}/{(p.get('quote') or 'USDT').upper()}",
                "id": p.get("symbol"),
                "max_leverage": p.get("maxLeverage"),
                "status": p.get("symbolStatus"),
            }
            for p in pairs
        ]
    return payload


# ── Backtest ─────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol:      str   = "BTC/USDT"
    deposit:     float = 1000.0
    period_days: int   = 30
    commission:  float = 0.055
    slippage:    float = 0.05
    strategy:    str   = "trend"      # "trend" | "mean_reversion"

class MultiBacktestRequest(BaseModel):
    symbols:     list[str] = []
    deposit:     float = 1000.0
    period_days: int   = 30
    commission:  float = 0.055
    slippage:    float = 0.05
    strategy:    str   = "trend"      # "trend" | "mean_reversion"


def fetch_ohlcv_paginated(symbol: str, tf: str, days: int) -> list:
    tf_minutes    = {"15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
    mins          = tf_minutes.get(tf, 30)
    total_candles = min(int(days * 24 * 60 / mins), 5000)
    since         = int((_time.time() - days * 86400) * 1000)
    all_candles   = []
    while len(all_candles) < total_candles:
        need = min(1000, total_candles - len(all_candles))
        raw  = api_call(exchange.fetch_ohlcv, symbol, tf, since=since, limit=need)
        if not raw: break
        all_candles.extend(raw)
        if len(raw) < need: break
        since = raw[-1][0] + 1
    seen, unique = set(), []
    for c in all_candles:
        if c[0] not in seen:
            seen.add(c[0]); unique.append(c)
    return sorted(unique, key=lambda x: x[0])


def _pnl(signal, entry, price):
    return ((price - entry) / entry * 100) if signal == 'LONG' else ((entry - price) / entry * 100)

def _trailing(signal, price, atr, current_stop):
    if signal == 'LONG': return max(price - atr * 0.8, current_stop)
    return min(price + atr * 0.8, current_stop)



def _load_btc_regime_series(period_days: int) -> pd.DataFrame:
    """
    Загружает BTC 1h и возвращает серию режимов по timestamp.
    Кэшируется внутри вызова бэктеста.
    """
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    raw  = fetch_ohlcv_paginated('BTC/USDT', '1h', period_days + 2)
    if not raw:
        return {}
    df_btc = build_features(pd.DataFrame(raw, columns=cols))
    # Считаем rolling режим: EMA9 > EMA21 и close > EMA50 = UPTREND
    result = {}
    for i in range(len(df_btc)):
        if i < 20:
            result[df_btc.iloc[i]['timestamp']] = 'CHOP'
            continue
        last = df_btc.iloc[i]
        if last['ema9'] > last['ema21'] and last['close'] > last['ema50']:
            result[last['timestamp']] = 'UPTREND'
        elif last['ema9'] < last['ema21'] and last['close'] < last['ema50']:
            result[last['timestamp']] = 'DOWNTREND'
        else:
            result[last['timestamp']] = 'CHOP'
    return result


def _run_one(symbol: str, period_days: int, deposit: float,
             commission: float, slippage: float, single_mode=False, timeframe='1h',
             raw_candles=None, btc_regimes=None,
             timeout_candles=36, trail_atr_mult=0.8) -> dict:
    """
    V8 бэктест одной пары. По умолчанию 1h.
    Логика выхода: TP1 фиксирует 50% → стоп в б/у → трейлинг → TP2 → TP3.
    Таймаут timeout_candles свечей (по умолчанию 36).

    raw_candles / btc_regimes можно передать заранее — так robustness-проверка
    гоняет десятки симуляций по одним и тем же данным без повторных запросов
    к бирже. timeout_candles / trail_atr_mult параметризованы для jitter-теста
    (наша история: сдвиг таймаута на 1 свечу менял PF на 30-60% — это и ловим).
    """
    COMM = commission / 100
    SLIP = slippage  / 100
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

    raw = raw_candles
    if raw is None:
        try:
            raw = fetch_ohlcv_paginated(symbol, timeframe, period_days)
        except Exception:
            return None
    if not raw or len(raw) < 50:
        return None

    df_main = build_features(pd.DataFrame(raw, columns=cols))
    df_main = build_nfi_features(df_main)  # + Supertrend

    # BTC режим фильтр (только для 1h — на других ТФ пропускаем)
    if btc_regimes is None:
        btc_regimes = {}
        if symbol != 'BTC/USDT' and timeframe == '1h':
            try:
                btc_regimes = _load_btc_regime_series(period_days)
            except Exception:
                pass

    in_trade  = False
    t_signal  = t_entry = t_stop = t_tp1 = t_tp2 = t_tp3 = t_pos = 0
    t_open_i  = 0
    t_tp1_hit = t_be_hit = False
    t_tp1_pnl_usdt = 0
    pending = None  # сигнал, найденный на предыдущей свече — вход на открытии текущей

    equity      = deposit
    max_equity  = deposit
    max_drawdown = 0
    wins = losses = bes = 0
    trades_list  = []
    equity_curve = []   # только для single_mode
    total_comm   = 0

    for i in range(1, len(df_main)):
        candle = df_main.iloc[i]
        ts_now = candle['timestamp']
        price  = candle['close']
        hi     = candle['high']
        lo     = candle['low']

        if in_trade:
            # Стоп
            if t_signal == 'LONG' and lo <= t_stop:
                exit_p = t_stop * (1 - SLIP)
                pnl_p  = _pnl(t_signal, t_entry, exit_p)
                result = 'be' if t_be_hit else 'sl'
            elif t_signal == 'SHORT' and hi >= t_stop:
                exit_p = t_stop * (1 + SLIP)
                pnl_p  = _pnl(t_signal, t_entry, exit_p)
                result = 'be' if t_be_hit else 'sl'
            else:
                result = None

            # TP1 — фиксируем 50%, стоп в б/у
            if not result and not t_tp1_hit:
                if (t_signal == 'LONG' and hi >= t_tp1) or (t_signal == 'SHORT' and lo <= t_tp1):
                    t_tp1_hit = True
                    t_be_hit  = True
                    ep  = t_tp1 * (1 - SLIP) if t_signal == 'LONG' else t_tp1 * (1 + SLIP)
                    p   = _pnl(t_signal, t_entry, ep)
                    c   = t_pos * 0.4 * COMM
                    t_tp1_pnl_usdt = t_pos * 0.4 * (p / 100) - c
                    equity    += t_tp1_pnl_usdt
                    total_comm += c
                    t_stop = t_entry
                    if single_mode:
                        equity_curve.append({"ts": int(ts_now), "equity": round(equity, 2)})
                    continue

            # Трейлинг после TP1
            if not result and t_tp1_hit:
                atr_now = candle['atr']
                if not pd.isna(atr_now) and atr_now > 0:
                    if t_signal == 'LONG':
                        new_stop = max(price - atr_now * trail_atr_mult, t_stop)
                    else:
                        new_stop = min(price + atr_now * trail_atr_mult, t_stop)
                    if abs(new_stop - t_stop) / (t_stop + 1e-10) > 0.003:
                        t_stop = new_stop

            # TP2
            if not result and t_tp1_hit:
                if (t_signal == 'LONG' and hi >= t_tp2) or (t_signal == 'SHORT' and lo <= t_tp2):
                    exit_p = t_tp2 * (1 - SLIP) if t_signal == 'LONG' else t_tp2 * (1 + SLIP)
                    pnl_p  = _pnl(t_signal, t_entry, exit_p)
                    result = 'tp2'

            # TP3
            if not result:
                if (t_signal == 'LONG' and hi >= t_tp3) or (t_signal == 'SHORT' and lo <= t_tp3):
                    exit_p = t_tp3 * (1 - SLIP) if t_signal == 'LONG' else t_tp3 * (1 + SLIP)
                    pnl_p  = _pnl(t_signal, t_entry, exit_p)
                    result = 'tp3'

            # Таймаут (по умолчанию 36 свечей = 36 часов на 1h)
            if not result and i - t_open_i > timeout_candles:
                exit_p = price * (1 - SLIP if t_signal == 'LONG' else 1 + SLIP)
                pnl_p  = _pnl(t_signal, t_entry, exit_p)
                result = 'timeout'

            if result:
                remaining  = 0.6 if t_tp1_hit else 1.0
                pnl_usdt   = t_pos * remaining * (pnl_p / 100)
                comm       = t_pos * remaining * COMM
                pnl_usdt  -= comm
                total_comm += comm
                equity     += pnl_usdt

                if equity > max_equity: max_equity = equity
                dd = (max_equity - equity) / max_equity * 100
                if dd > max_drawdown: max_drawdown = dd

                trade_total_pnl = pnl_usdt + t_tp1_pnl_usdt  # с учётом зафиксированного TP1

                if result in ('tp2', 'tp3') or (result == 'timeout' and trade_total_pnl > 0):
                    wins += 1
                elif result == 'be' and trade_total_pnl > 0:
                    result = 'tp1'; wins += 1
                elif result == 'sl' and trade_total_pnl <= 0:
                    losses += 1
                elif trade_total_pnl > 0:
                    wins += 1
                else:
                    bes += 1

                dt = datetime.fromtimestamp(ts_now / 1000)
                entry_data = {
                    "symbol":   symbol,
                    "date":     dt.strftime('%Y-%m-%d'),
                    "time":     dt.strftime('%H:%M'),
                    "signal":   t_signal,
                    "entry":    round(t_entry, 6),
                    "exit":     round(exit_p, 6),
                    "result":   result,
                    "pnl_pct":  round(pnl_p, 3),
                    "pnl_usdt": round(trade_total_pnl, 2),
                }
                if single_mode:
                    entry_data["commission"] = round(comm, 3)
                    entry_data["equity"]     = round(equity, 2)
                trades_list.append(entry_data)

                if single_mode:
                    equity_curve.append({"ts": int(ts_now), "equity": round(equity, 2)})

                in_trade = False
                t_tp1_hit = t_be_hit = False
                t_tp1_pnl_usdt = 0
            continue

        # ── Исполнение сигнала, найденного на ПРЕДЫДУЩЕЙ свече ────
        # (вход на открытии текущей свечи — без look-ahead)
        if pending is not None:
            signal, atr_val, adx_val = pending
            pending = None

            entry   = candle['open']
            atr_pct = atr_val / entry if entry > 0 else 0

            stop, tp1, tp2, tp3 = backtest_levels(signal, entry, atr_val, adx_val, atr_pct, df_main.iloc[:i])
            pos_usdt = volatility_position_size(entry, stop, atr_pct)
            if pos_usdt > 0:
                equity    -= pos_usdt * COMM
                total_comm += pos_usdt * COMM

                in_trade  = True
                t_signal  = signal
                t_entry   = entry
                t_stop    = stop
                t_tp1     = tp1
                t_tp2     = tp2
                t_tp3     = tp3
                t_pos     = pos_usdt
                t_open_i  = i
                t_tp1_hit = t_be_hit = False
            continue

        # ── Поиск сигнала на ЗАКРЫТОЙ свече (V8 логика через should_enter) ──
        df_slice = df_main.iloc[:i + 1].copy()
        if len(df_slice) < 50:
            continue

        last = df_slice.iloc[-1]
        if pd.isna(last['atr']) or last['atr'] <= 0:
            continue
        if pd.isna(last.get('adx', float('nan'))):
            continue

        signal = None
        if should_enter(df_slice, 'LONG'):
            signal = 'LONG'
        elif should_enter(df_slice, 'SHORT'):
            signal = 'SHORT'

        if not signal:
            continue

        # BTC режим фильтр — не входим против рынка
        if btc_regimes:
            ts_key = candle['timestamp']
            # Ищем ближайший BTC режим
            btc_r = btc_regimes.get(ts_key, 'CHOP')
            if signal == 'LONG'  and btc_r == 'DOWNTREND':
                continue
            if signal == 'SHORT' and btc_r == 'UPTREND':
                continue

        atr_val = last['atr']
        adx_val = last['adx'] if not pd.isna(last['adx']) else 0
        pending = (signal, atr_val, adx_val)  # войдём на открытии следующей свечи

    total = wins + losses + bes
    if total == 0:
        return None

    total_pnl_pct = round(sum(t['pnl_pct'] for t in trades_list), 2)
    wins_usdt = [t['pnl_usdt'] for t in trades_list if t['pnl_usdt'] > 0]
    loss_usdt = [t['pnl_usdt'] for t in trades_list if t['pnl_usdt'] < 0]

    result_data = {
        "symbol":         symbol,
        "total":          total,
        "wins":           wins,
        "losses":         losses,
        "breakeven":      bes,
        "winrate":        round(wins / total * 100, 1),
        "total_pnl_pct":  total_pnl_pct,
        "avg_pnl_pct":    round(total_pnl_pct / total, 2),
        "max_drawdown":   round(max_drawdown, 2),
        "profit_factor":  round(abs(sum(wins_usdt) / sum(loss_usdt)), 2) if loss_usdt and sum(loss_usdt) != 0 else 0,
        "trades":         trades_list,
    }

    if single_mode:
        result_data["final_equity"]    = round(equity, 2)
        result_data["total_commission"] = round(total_comm, 2)
        result_data["equity_curve"]    = [{"day": idx, "equity": p["equity"], "ts": p["ts"]}
                                           for idx, p in enumerate(equity_curve)]

    return result_data


@app.post("/api/backtest")
def run_backtest(req: BacktestRequest, user=Depends(require_user)):
    """
    Бэктест одной пары с кривой доходности. strategy: trend | mean_reversion | breakout | momentum
    ВАЖНО: STRATEGY_MODE — общая переменная с живым сканером в этом же процессе.
    Сохраняем и восстанавливаем исходное значение, чтобы вызов бэктеста
    не подменял боевой режим живой торговли.
    """
    live_mode = nfi_strategy.STRATEGY_MODE
    try:
        nfi_strategy.STRATEGY_MODE = req.strategy
        result = _run_one(
            symbol=req.symbol, period_days=req.period_days,
            deposit=req.deposit, commission=req.commission,
            slippage=req.slippage, single_mode=True,
        )
    finally:
        nfi_strategy.STRATEGY_MODE = live_mode
    if not result:
        return {"error": "Нет сделок или данных"}

    # Формат совместимый с фронтендом
    return {
        "symbol":           result["symbol"],
        "strategy":         req.strategy,
        "timeframe":        "1h",
        "period_days":      req.period_days,
        "candles_used":     0,
        "deposit":          req.deposit,
        "final_equity":     result["final_equity"],
        "total_pnl":        round((result["final_equity"] - req.deposit) / req.deposit * 100, 2),
        "max_drawdown":     result["max_drawdown"],
        "winrate":          result["winrate"],
        "total":            result["total"],
        "wins":             result["wins"],
        "losses":           result["losses"],
        "breakeven":        result["breakeven"],
        "avg_win":          0,
        "avg_loss":         0,
        "profit_factor":    result["profit_factor"],
        "avg_pnl":          result["avg_pnl_pct"],
        "total_commission": result["total_commission"],
        "commission_pct":   req.commission,
        "slippage_pct":     req.slippage,
        "equity_curve":     result["equity_curve"],
        "trades":           result["trades"][-50:],
    }


# ── Проверка на прочность (robustness) ───────────────────────────
# Автоматизация нашей методологии: walk-forward + cost stress + jitter +
# Monte-Carlo + Deflated Sharpe. Premium-фича: ~16 симуляций, тяжёлый компьют.

import robustness as robustness_mod


class RobustnessRequest(BaseModel):
    symbol:      str   = "BTC/USDT"
    deposit:     float = 1000.0
    period_days: int   = 90
    commission:  float = 0.055
    slippage:    float = 0.05
    strategy:    str   = "momentum"


@app.post("/api/backtest/robustness")
def start_robustness(req: RobustnessRequest, authorization: str | None = Header(default=None)):
    user = auth.user_from_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    if not auth.tier_allows(auth.effective_tier(user), 'premium'):
        raise HTTPException(status_code=403, detail="Проверка на прочность доступна на Premium")
    if req.strategy not in ('trend', 'mean_reversion', 'momentum'):
        raise HTTPException(status_code=400, detail="Неизвестная стратегия")
    period = max(30, min(365, req.period_days))

    job_id = robustness_mod.create_job(user_id=user["id"])

    def _worker():
        # Тот же паттерн, что /api/backtest: временно ставим режим стратегии и
        # восстанавливаем. Окно гонки со сканером такое же, как у обычного бэктеста.
        live_mode = nfi_strategy.STRATEGY_MODE
        try:
            nfi_strategy.STRATEGY_MODE = req.strategy
            robustness_mod.run_robustness(
                job_id, _run_one, fetch_ohlcv_paginated,
                req.symbol, period, req.deposit, req.commission, req.slippage,
            )
        finally:
            nfi_strategy.STRATEGY_MODE = live_mode

    import threading as _threading
    _threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/backtest/robustness/{job_id}")
def robustness_status(job_id: str, authorization: str | None = Header(default=None)):
    user = auth.user_from_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    job = robustness_mod.get_job(job_id)
    owner = job.get("user_id") if job else None
    if not job or (owner is not None and owner != user["id"]):
        raise HTTPException(status_code=404, detail="Джоба не найдена (возможно, устарела)")
    return {"status": job["status"], "progress": job["progress"],
            "result": job["result"], "error": job["error"]}


import re as _re
import json as _json
import threading as _threading_ca
import channel_jobs

CHANNEL_ANALYSIS_CACHE_HOURS = 24  # повторный запрос по тому же каналу в течение суток отдаёт кэш без нового скрейпа


class AnalyzeChannelRequest(BaseModel):
    channel_url: str
    days: int = 30
    entry_timeout_hours: int = 6
    max_hold_hours: int = 168
    risk_per_trade_usd: float = 100.0


def _parse_channel_username(raw: str) -> str:
    """'https://t.me/binancekillers', '@binancekillers', 'binancekillers' -> 'binancekillers'.
    Валидируем формат до того, как отдать строку в Telethon — не пускаем
    произвольный мусор/URL с чужими параметрами в iter_messages()."""
    s = raw.strip()
    s = _re.sub(r'^https?://(t\.me|telegram\.me)/', '', s, flags=_re.IGNORECASE)
    s = s.lstrip('@').split('/')[0].split('?')[0].strip()
    if not _re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', s):
        raise HTTPException(status_code=400, detail="Некорректная ссылка на канал — ожидается t.me/username")
    return s


@app.post("/api/analyze-channel")
def analyze_channel(req: AnalyzeChannelRequest, admin=Depends(require_admin)):
    """
    Только для админа: полный ingest+backtest дорогой (Telegram history scrape +
    OpenAI на каждое сообщение + запросы к бирже) и бьёт по нашему аккаунту/бюджету,
    а не по деньгам пользователя — открывать это на весь сайт нельзя.
    """
    channel = _parse_channel_username(req.channel_url)
    days = max(1, min(90, req.days))
    entry_timeout_hours = max(1, min(48, req.entry_timeout_hours))
    max_hold_hours = max(1, min(24 * 30, req.max_hold_hours))       # верхний потолок — 30 дней удержания
    risk_per_trade_usd = max(1.0, min(100_000.0, req.risk_per_trade_usd))

    cached = db.get_channel_stats(channel)
    if cached and cached.get('last_analyzed_at'):
        age_h = (datetime.now() - datetime.fromisoformat(cached['last_analyzed_at'])).total_seconds() / 3600
        # Кэш валиден только если он посчитан С ТЕМИ ЖЕ параметрами — иначе
        # запрос на 30 дней молча получал бы отчёт, посчитанный на 7 (баг,
        # пойманный в проде: повторный анализ с другими параметрами "не давал"
        # запуститься, потому что тихо возвращал старые цифры под видом новых).
        same_params = (
            cached.get('period_days') == days
            and cached.get('entry_timeout_hours') == entry_timeout_hours
            and cached.get('max_hold_hours') == max_hold_hours
            and cached.get('risk_per_trade_usd') == risk_per_trade_usd
        )
        if age_h < CHANNEL_ANALYSIS_CACHE_HOURS and same_params:
            return {
                "cached": True, "channel": channel,
                "report": {k: cached[k] for k in (
                    'total_signals', 'checked', 'closed_trades', 'wins', 'losses',
                    'winrate_pct', 'avg_risk_reward', 'tp2_hit_rate', 'tp2_sample',
                    'tp3_hit_rate', 'tp3_sample',
                )} | {
                    "total_pnl_pct_of_risk": cached['total_pnl_pct'],
                    "total_pnl_usd": cached.get('total_pnl_usd'),
                    "channel": channel,
                },
                "equity_curve": _json.loads(cached['equity_curve_json'] or '[]'),
            }

    job_id = channel_jobs.create_job()
    _threading_ca.Thread(
        target=channel_jobs.run_channel_analysis,
        args=(job_id, channel, days),
        kwargs=dict(entry_timeout_hours=entry_timeout_hours, max_hold_hours=max_hold_hours,
                     risk_per_trade_usd=risk_per_trade_usd),
        daemon=True,
    ).start()
    return {"cached": False, "job_id": job_id, "channel": channel}


@app.get("/api/analysis-status/{job_id}")
def analysis_status(job_id: str, admin=Depends(require_admin)):
    job = channel_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена (возможно, устарела или сервер перезапускался)")
    return {"status": job["status"], "step": job["step"], "result": job["result"], "error": job["error"]}


@app.get("/api/channel-history/{channel}")
def get_channel_history(channel: str, admin=Depends(require_admin)):
    """Полный список найденных ботом сигналов канала с исходом каждого —
    для таблицы истории на фронте (не только агрегированный отчёт)."""
    return db.load_historical_signals(channel)


@app.get("/api/channels-ranking")
def get_channels_ranking(admin=Depends(require_admin)):
    """Все уже проанализированные каналы бок о бок — для сравнения, а не
    только последний прогнанный. Сортировка по итоговому PnL% (в db-функции)."""
    return db.list_channel_stats()


@app.post("/api/backtest/multi")
def run_multi_backtest(req: MultiBacktestRequest, user=Depends(require_user)):
    """
    Мульти-символьный бэктест. strategy: trend | mean_reversion | breakout | momentum
    ВАЖНО: см. комментарий в run_backtest — сохраняем/восстанавливаем live-режим,
    чтобы бэктест не подменял боевую стратегию сканера.
    """
    live_mode = nfi_strategy.STRATEGY_MODE
    symbols = req.symbols if req.symbols else CANDIDATES
    results, errors = [], []

    try:
        nfi_strategy.STRATEGY_MODE = req.strategy
        for symbol in symbols:
            try:
                res = _run_one(symbol=symbol, period_days=req.period_days,
                               deposit=req.deposit, commission=req.commission,
                               slippage=req.slippage, single_mode=False)
                if res: results.append(res)
                else:   errors.append({"symbol": symbol, "reason": "нет данных или сделок"})
            except Exception as e:
                errors.append({"symbol": symbol, "reason": str(e)})
    finally:
        nfi_strategy.STRATEGY_MODE = live_mode

    if not results:
        return {"error": "Ни одна пара не дала сделок", "errors": errors}

    all_trades = []
    for r in results:
        all_trades.extend(r["trades"])
    all_trades.sort(key=lambda x: x["date"] + x["time"])

    total_trades = sum(r["total"]   for r in results)
    total_wins   = sum(r["wins"]    for r in results)
    total_losses = sum(r["losses"]  for r in results)
    total_bes    = sum(r["breakeven"] for r in results)
    total_pnl    = round(sum(r["total_pnl_pct"] for r in results), 2)
    avg_dd       = round(sum(r["max_drawdown"]  for r in results) / len(results), 2)

    wins_usdt = [t["pnl_usdt"] for t in all_trades if t["pnl_usdt"] > 0]
    loss_usdt = [t["pnl_usdt"] for t in all_trades if t["pnl_usdt"] < 0]

    return {
        "period_days":          req.period_days,
        "strategy":             req.strategy,
        "symbols_tested":       len(symbols),
        "symbols_with_trades":  len(results),
        "summary": {
            "total_trades":     total_trades,
            "wins":             total_wins,
            "losses":           total_losses,
            "breakeven":        total_bes,
            "winrate":          round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0,
            "total_pnl_pct":    total_pnl,
            "avg_pnl_per_trade": round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
            "avg_drawdown":     avg_dd,
            "profit_factor":    round(abs(sum(wins_usdt) / sum(loss_usdt)), 2) if loss_usdt and sum(loss_usdt) != 0 else 0,
            "trades_per_month": round(total_trades / (req.period_days / 30), 1),
        },
        "by_symbol":  sorted(results, key=lambda x: x["total_pnl_pct"], reverse=True),
        "all_trades": all_trades[-100:],
        "errors":     errors,
    }