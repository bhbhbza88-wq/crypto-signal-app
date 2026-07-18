"""
FastAPI backend — V8 стратегия.
Бэктест использует should_enter() + get_mults() + calc_levels() из nfi_strategy (V8).
"""

import os
import json
import hmac
import asyncio
import urllib.request
import urllib.error
import pandas as pd
import time as _time
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
import auth
import telegram_bot
from scanner import start_background_scanner, MAX_OPEN_TRADES
import data_layer
from data_layer import exchange, api_call, build_features, detect_regime, get_active_symbols, CANDIDATES
import nfi_strategy
from nfi_strategy import (
    build_nfi_features, should_enter,
    get_mults, calc_levels, calc_position_size, volatility_position_size,
    backtest_levels, ADX_MIN, get_risk_status
)
from signal_ingest import normalize_symbol, open_signal
import telegram_ingest


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    start_background_scanner()
    if telegram_ingest.is_configured():
        asyncio.create_task(telegram_ingest.run())
    asyncio.create_task(telegram_bot.set_webhook())
    yield


app = FastAPI(title="Crypto Signal App V8", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.post("/api/telegram-webhook")
async def telegram_webhook(request: Request,
                            x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    """Вебхук бота: /start, /help, /premium, /status и callback-кнопки.
    secret_token проверяем, чтобы принимать только запросы от Telegram."""
    if telegram_bot.WEBHOOK_SECRET and x_telegram_bot_api_secret_token != telegram_bot.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    update = await request.json()
    await telegram_bot.handle_update(update)
    return {"ok": True}


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


class TradingViewWebhook(BaseModel):
    ticker: str
    action: str            # "buy" | "sell"
    price: float
    indicator_name: str
    secret: str


TRADINGVIEW_SECRET = os.getenv("TRADINGVIEW_SECRET", "")


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


@app.post("/api/auth/register")
def auth_register(req: AuthRequest):
    user, token = auth.register(req.email, req.password)
    if not user:
        raise HTTPException(status_code=400, detail=token)  # token=сообщение об ошибке
    return {"token": token, "user": auth.public_user(user)}


@app.post("/api/auth/login")
def auth_login(req: AuthRequest):
    user, token = auth.login(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail=token)
    return {"token": token, "user": auth.public_user(user)}


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
def billing_upgrade(req: UpgradeRequest, authorization: str | None = Header(default=None)):
    """
    ЗАГЛУШКА оплаты: пока просто меняет тариф (для теста гейтинга).
    Реальную оплату подключим отдельным шагом (Этап 1.5).
    """
    user = auth.user_from_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    if req.tier not in ('free', 'premium', 'vip'):
        raise HTTPException(status_code=400, detail="Неизвестный тариф")
    db.set_user_tier(user['id'], req.tier)
    return {"ok": True, "tier": req.tier, "note": "ЗАГЛУШКА — реальная оплата будет позже"}


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
    background_tasks.add_task(telegram_bot.notify_manual_signal, {
        "symbol": symbol, "signal": signal,
        "entry": req.entry, "stop": req.stop,
        "tp1": req.tp1, "tp2": req.tp2, "tp3": req.tp3,
    }, trader['name'])
    return {"ok": True, "symbol": symbol, "trader": trader['name']}


# ── Вебхуки TradingView ────────────────────────────────────────────
# Расчёт SL/TP на вебхуке — заглушка 1:3 (стоп 2%, тейк 6%). Как и ручные
# сигналы, дальше сделку ведёт tracker.py по цене Bybit — никакой отдельной
# логики TP/SL для вебхуков не нужно, она уже общая для всех open_trades.
TV_SL_PCT = 0.02
TV_TP_PCT = 0.06


@app.post("/api/webhooks/tradingview")
def tradingview_webhook(req: TradingViewWebhook, background_tasks: BackgroundTasks):
    if not TRADINGVIEW_SECRET or not hmac.compare_digest(req.secret, TRADINGVIEW_SECRET):
        raise HTTPException(status_code=401, detail="Неверный секрет")

    action = req.action.lower().strip()
    if action not in ('buy', 'sell'):
        raise HTTPException(status_code=400, detail="action должен быть buy или sell")
    signal = 'LONG' if action == 'buy' else 'SHORT'

    if req.price <= 0:
        raise HTTPException(status_code=400, detail="price должен быть положительным")

    entry = req.price
    if signal == 'LONG':
        stop = entry * (1 - TV_SL_PCT)
        tp1, tp2, tp3 = entry * 1.02, entry * 1.04, entry * (1 + TV_TP_PCT)
    else:
        stop = entry * (1 + TV_SL_PCT)
        tp1, tp2, tp3 = entry * 0.98, entry * 0.96, entry * (1 - TV_TP_PCT)

    trader_id = db.get_or_create_trader(req.indicator_name)
    trader = db.get_trader(trader_id)

    symbol, err = open_signal(
        req.ticker, signal, entry, stop, tp1, tp2, tp3,
        trader_id=trader_id, regime="tradingview",
        reasons=[f"TradingView: {req.indicator_name}"],
    )
    if err == 'already_open':
        raise HTTPException(status_code=409, detail=f"По {normalize_symbol(req.ticker)} уже есть открытая позиция")
    if err == 'invalid_levels':
        raise HTTPException(status_code=400, detail="Некорректные уровни TP/SL")

    db.add_event(symbol, 'tradingview_signal',
                 f"{req.indicator_name}: {signal} {symbol} @ {entry}")

    background_tasks.add_task(telegram_bot.notify_manual_signal, {
        "symbol": symbol, "signal": signal,
        "entry": entry, "stop": stop,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
    }, f"TradingView · {trader['name']}")

    return {"ok": True, "symbol": symbol, "signal": signal, "trader": trader['name']}


# ── AI Ассистент (серверный ключ) ────────────────────────────────
# Ключ живёт в env OPENAI_API_KEY (как и телеграм-токен — никогда в коде).
# Лимиты в памяти процесса: при рестарте сбрасываются — для Этапа 1 достаточно.

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = "gpt-4o-mini"
AI_DAILY_LIMITS = {'free': 5, 'premium': 50, 'vip': 200}
_ai_usage: dict[int, dict] = {}   # user_id -> {'date': 'YYYY-MM-DD', 'count': int}

class AIChatRequest(BaseModel):
    messages: list[dict]


def _ai_market_context() -> str:
    """Собирает актуальное состояние платформы для системного промпта AI.
    Всё — реальные данные (цены, скринер, сигналы, фаза), чтобы ассистент
    отвечал по факту, а не общими словами. Каждый блок в своём try — если
    что-то недоступно, остальное всё равно попадёт в контекст."""
    lines = [
        # ── ПЕРСОНА: бывалый крипто-трейдер-наставник, а не безликий чат-бот ──
        "Ты — Ник, крипто-наставник платформы NOWICKI. Ты бывалый трейдер, прошёл не один цикл: "
        "эйфорию 2021-го, кровавый 2022-й с крахами LUNA и FTX, видел тысячи ликвидаций и знаешь цену жадности. "
        "За плечами — тысячи часов у графиков.",
        "ХАРАКТЕР И ТОН: уверенный, прямой, без воды. Говоришь по-простому, на языке трейдера "
        "(лонг/шорт, набрать позу, поставить стоп, боковик, ловить падающий нож, откуп, слить депозит, зафиксить). "
        "Ты спокойный наставник со стержнем, а не восторженный инфоцыган и не сухой робот. "
        "Немного характера и трейдерского юмора уместно, но по делу.",
        "ЖЕЛЕЗНЫЕ ПРИНЦИПЫ (не нарушай): никаких обещаний прибыли и «иксов»; всегда напоминаешь про стоп и риск; "
        "не даёшь персональных инвест-советов и НЕ гадаешь будущую цену — только текущая картина и трезвая аналитика; "
        "если данных нет — прямо говоришь, а не выдумываешь. Честность важнее красивого ответа — это стиль NOWICKI.",
        "ФОРМАТ: отвечай кратко и по делу, на русском. Не растекайся, не читай лекций без запроса. "
        "Опирайся на ДАННЫЕ НИЖЕ — это реальное состояние платформы прямо сейчас.",
    ]

    try:
        btc = api_call(exchange.fetch_ticker, 'BTC/USDT') or {}
        eth = api_call(exchange.fetch_ticker, 'ETH/USDT') or {}
        lines.append(f"ЦЕНЫ (24ч): BTC ${btc.get('last')} ({btc.get('percentage')}%), "
                     f"ETH ${eth.get('last')} ({eth.get('percentage')}%).")
    except Exception:
        pass

    try:
        ov = data_layer.get_market_overview()
        if ov and ov.get('symbols'):
            syms = ov['symbols']
            lines.append(f"СКРИНЕР (режим BTC: {ov.get('btc_regime')}): в аптренде "
                         f"{ov.get('uptrend_count')}, в даунтренде {ov.get('downtrend_count')}, "
                         f"без тренда {ov.get('chop_count')}.")
            up = sorted([s for s in syms if s['regime'] == 'UPTREND'], key=lambda s: -s['adx'])[:6]
            dn = sorted([s for s in syms if s['regime'] == 'DOWNTREND'], key=lambda s: -s['adx'])[:6]
            if up:
                lines.append("Сильнейший аптренд (по ADX): " +
                             ", ".join(f"{s['symbol'].replace('/USDT','')} ADX {s['adx']}" for s in up))
            if dn:
                lines.append("Сильнейший даунтренд: " +
                             ", ".join(f"{s['symbol'].replace('/USDT','')} ADX {s['adx']}" for s in dn))
            # полный список — чтобы можно было ответить про любую монету
            lines.append("Все монеты (символ:режим:ADX): " +
                         "; ".join(f"{s['symbol'].replace('/USDT','')}:{s['regime']}:{s['adx']}" for s in syms))
    except Exception:
        pass

    try:
        import trend_strategy
        ph = trend_strategy.get_market_phase()
        if ph:
            lines.append(f"ФАЗА РЫНКА (BTC, информационно, не торгует): {ph.get('phase')}, "
                         f"моментум 60д {ph.get('momentum_60d_pct')}%.")
    except Exception:
        pass

    try:
        trades = db.load_trades()
        if trades:
            parts = []
            for sym, t in list(trades.items())[:8]:
                parts.append(f"{sym.replace('/USDT','')} {t['signal']} вход {t['entry']} "
                             f"стоп {t['stop']} TP1 {t['tp1']} (score {t.get('score')})")
            lines.append("АКТИВНЫЕ СИГНАЛЫ СКАНЕРА: " + "; ".join(parts))
        else:
            lines.append("АКТИВНЫХ СИГНАЛОВ СКАНЕРА СЕЙЧАС НЕТ (сканер ищет сетапы каждые 2 минуты).")
    except Exception:
        pass

    return "\n".join(lines)


@app.post("/api/ai/chat")
def ai_chat(req: AIChatRequest, authorization: str | None = Header(default=None)):
    user = auth.user_from_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Войди в аккаунт, чтобы пользоваться AI-ассистентом")
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="AI-ассистент временно недоступен")

    tier = auth.effective_tier(user)
    limit = AI_DAILY_LIMITS.get(tier, AI_DAILY_LIMITS['free'])
    today = datetime.now().strftime('%Y-%m-%d')
    usage = _ai_usage.get(user['id'])
    if not usage or usage['date'] != today:
        usage = {'date': today, 'count': 0}
    if usage['count'] >= limit:
        raise HTTPException(status_code=429,
                            detail=f"Дневной лимит AI-запросов исчерпан ({limit}/день на тарифе {tier}). "
                                   f"Лимит обновится завтра.")

    # Санитизация: берём только user/assistant из клиента (клиентский system
    # игнорируем — свой системный контекст строим на сервере из реальных данных).
    msgs = []
    for m in req.messages[-20:]:
        role = m.get('role')
        content = m.get('content')
        if role in ('user', 'assistant') and isinstance(content, str):
            msgs.append({'role': role, 'content': content[:6000]})
    if not msgs or msgs[-1]['role'] != 'user':
        raise HTTPException(status_code=400, detail="Некорректный формат сообщений")

    # Серверный системный промпт с актуальным состоянием платформы
    msgs.insert(0, {'role': 'system', 'content': _ai_market_context()})

    payload = json.dumps({'model': AI_MODEL, 'max_tokens': 800, 'messages': msgs}).encode()
    request = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=payload,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {OPENAI_API_KEY}'},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
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


# ── API endpoints ────────────────────────────────────────────────

@app.get("/api/signals")
def get_active_signals():
    trades = db.load_trades()
    traders_by_id = {t['id']: t for t in db.list_traders(only_active=False)}
    out = []
    for symbol, t in trades.items():
        candles = []
        if t.get('candles_json'):
            try:
                candles = json.loads(t['candles_json'])
            except (TypeError, json.JSONDecodeError):
                candles = []
        # Telegram-импорт раньше не писал свечи — догружаем с Bybit и сохраняем
        if not candles:
            try:
                import data_layer
                cj = data_layer.fetch_candles_json(symbol)
                if cj:
                    candles = json.loads(cj)
                    t['candles_json'] = cj
                    db.upsert_trade(symbol, t)
            except Exception as e:
                print(f"[api/signals] candles backfill {symbol}: {e}")
        entry_reasons = json.loads(t['entry_reasons_json']) if t.get('entry_reasons_json') else []
        trader = traders_by_id.get(t.get('trader_id'))
        out.append({
            "symbol": symbol,
            "signal": t['signal'],
            "entry": t['entry'],
            "stop":  t['stop'],
            "tp1": t['tp1'], "tp2": t['tp2'], "tp3": t['tp3'],
            "score": t.get('score'),
            "regime": t.get('regime'),
            "tp1_hit": bool(t.get('tp1_hit')),
            "tp2_hit": bool(t.get('tp2_hit')),
            "be_hit":  bool(t.get('be_hit')),
            "opened_at": t.get('opened_at'),
            "candles": candles,
            "entry_reasons": entry_reasons,
            "position_size": t.get('position_size'),
            "trader": {"id": trader['id'], "name": trader['name'], "avatar_url": trader.get('avatar_url'), "source_type": trader.get('source_type')} if trader else None,
        })
    return out


@app.get("/api/stats")
def get_stats():
    history   = db.load_history(limit=5000)
    now       = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    week_ago  = now - timedelta(days=7)
    return {
        "today":    _summarize([t for t in history if t['date'] == today_str]),
        "week":     _summarize([t for t in history if datetime.strptime(t['date'], '%Y-%m-%d') >= week_ago]),
        "all_time": _summarize(history),
    }


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
def get_history(limit: int = 100):
    return db.load_history(limit=limit)


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
def force_xsec_rebalance():
    """Ручной запуск ребаланса (для теста)."""
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
def force_trend_check():
    """Ручная проверка сигналов (для теста)."""
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
def run_backtest(req: BacktestRequest):
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

    job_id = robustness_mod.create_job()

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
    if not job:
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
def run_multi_backtest(req: MultiBacktestRequest):
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