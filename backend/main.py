"""
FastAPI backend — отдаёт активные сигналы, историю сделок и статистику фронтенду.
Запуск: uvicorn main:app --reload --port 8000
"""

import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
from scanner import start_background_scanner
from signal_engine import get_market_overview, get_mults, calc_levels, calc_position, entry_conditions
from data_layer import exchange, api_call, build_features, detect_regime
import pandas as pd


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    start_background_scanner()
    yield


app = FastAPI(title="Crypto Signal App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/signals")
def get_active_signals():
    """Текущие открытые сделки (активные сигналы)."""
    trades = db.load_trades()
    out = []
    for symbol, t in trades.items():
        candles = json.loads(t['candles_json']) if t.get('candles_json') else []
        entry_reasons = json.loads(t['entry_reasons_json']) if t.get('entry_reasons_json') else []
        out.append({
            "symbol": symbol,
            "signal": t['signal'],
            "entry": t['entry'],
            "stop": t['stop'],
            "tp1": t['tp1'], "tp2": t['tp2'], "tp3": t['tp3'],
            "score": t.get('score'),
            "regime": t.get('regime'),
            "tp1_hit": bool(t.get('tp1_hit')),
            "tp2_hit": bool(t.get('tp2_hit')),
            "be_hit": bool(t.get('be_hit')),
            "opened_at": t.get('opened_at'),
            "candles": candles,
            "entry_reasons": entry_reasons,
            "position_size": t.get('position_size'),
        })
    return out


@app.get("/api/market")
def get_market():
    """Состояние рынка: режим BTC + heatmap всех отслеживаемых монет."""
    return get_market_overview()


@app.get("/api/history")
def get_history(limit: int = 100):
    return db.load_history(limit=limit)


@app.get("/api/events")
def get_events(limit: int = 50):
    return db.load_events(limit=limit)


def summarize(trades):
    if not trades:
        return {
            "total": 0, "winrate": 0, "tp1": 0, "tp2_plus": 0,
            "stops": 0, "breakeven": 0, "total_pnl": 0, "avg_pnl": 0,
            "best": None, "worst": None,
        }
    total = len(trades)
    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['result'] == 'sl')
    bes = sum(1 for t in trades if t['result'] in ('be', 'potential'))
    tp1s = sum(1 for t in trades if t['result'] == 'tp1')
    total_pnl = sum(t['pnl'] for t in trades)
    best = max(trades, key=lambda x: x['pnl'])
    worst = min(trades, key=lambda x: x['pnl'])
    return {
        "total": total,
        "winrate": round(wins / total * 100, 1),
        "tp1": tp1s,
        "tp2_plus": wins - tp1s,
        "stops": losses,
        "breakeven": bes,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2),
        "best": {"symbol": best['symbol'], "pnl": best['pnl']},
        "worst": {"symbol": worst['symbol'], "pnl": worst['pnl']},
    }


@app.get("/api/stats")
def get_stats():
    """Статистика за три периода: сегодня, неделя, всё время."""
    history = db.load_history(limit=5000)
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    week_ago = now - timedelta(days=7)

    today_trades = [t for t in history if t['date'] == today_str]
    week_trades = [t for t in history if datetime.strptime(t['date'], '%Y-%m-%d') >= week_ago]

    return {
        "today": summarize(today_trades),
        "week": summarize(week_trades),
        "all_time": summarize(history),
    }




# ─── BACKTEST ────────────────────────────────────────────────────────────────

import time as _time

from signal_engine import (
    get_mults, entry_conditions,
    detect_trend_stable, mtf_confirms, volume_healthy,
    is_overextended, detect_volume_climax,
    detect_ema_cross_fresh, detect_pullback, calc_score,
    ADX_MIN, SCORE_MIN,
)


class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    deposit: float = 1000.0
    period_days: int = 30
    commission: float = 0.055
    slippage: float = 0.05
    scanner_mode: bool = False  # True = режим сканера: 30m основной, 1h+4h подтверждение


def fetch_ohlcv_paginated(symbol: str, tf: str, days: int) -> list:
    tf_minutes = {"15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
    mins = tf_minutes.get(tf, 60)
    total_candles = min(int(days * 24 * 60 / mins), 5000)
    since = int((_time.time() - days * 86400) * 1000)
    all_candles = []
    while len(all_candles) < total_candles:
        need = min(1000, total_candles - len(all_candles))
        raw = api_call(exchange.fetch_ohlcv, symbol, tf, since=since, limit=need)
        if not raw:
            break
        all_candles.extend(raw)
        if len(raw) < need:
            break
        since = raw[-1][0] + 1
    seen = set()
    unique = []
    for c in all_candles:
        if c[0] not in seen:
            seen.add(c[0])
            unique.append(c)
    return sorted(unique, key=lambda x: x[0])


def _pnl(signal, entry, price):
    return ((price - entry) / entry * 100) if signal == 'LONG' else ((entry - price) / entry * 100)


def _check_potential_loss(df_slice, signal, entry, price):
    """Точная копия логики check_potential_loss из tracker.py (на свечах)."""
    pnl = _pnl(signal, entry, price)
    if pnl > 0.3 or abs(price - entry) / entry >= 0.015:
        return False
    last = df_slice.iloc[-1]
    weak = 0
    if last['volume'] < last['vol_avg']:
        weak += 1
    if last['vol_trend'] < 0.70:
        weak += 1
    if signal == 'LONG':
        if last['ema9'] < last['ema21']:
            weak += 1
        if last['rsi'] < 45:
            weak += 1
        if last['close'] < last['ema50']:
            weak += 1
    else:
        if last['ema9'] > last['ema21']:
            weak += 1
        if last['rsi'] > 55:
            weak += 1
        if last['close'] > last['ema50']:
            weak += 1
    return weak >= 3


def _calc_trailing_stop(signal, price, atr, current_stop):
    """Точная копия calc_trailing_stop из tracker.py."""
    if signal == 'LONG':
        return max(price - atr * 0.8, current_stop)
    else:
        return min(price + atr * 0.8, current_stop)


@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    """
    Точный бэктест — использует ровно ту же логику что живой сканер и трекер:
    - Все фильтры входа из generate_signal()
    - check_potential_loss() из tracker.py
    - Trailing stop до TP1 (70% пути → стоп в +0.3%)
    - Частичная фиксация 50% на TP1, стоп в б/у
    - Trailing stop после TP1 (ATR * 0.8)
    - Комиссии Bybit + проскальзывание
    """
    tf_map = {"15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h"}
    tf = "1h" if req.scanner_mode else tf_map.get(req.timeframe, "1h")
    tf_1h  = {"15m": "1h",  "30m": "1h",  "1h": "4h", "4h": "1d"}
    tf_4h  = {"15m": "4h",  "30m": "4h",  "1h": "4h", "4h": "1d"}
    # В режиме сканера: основной 1h, подтверждение 4h (второй уровень — тоже 4h)
    tf_higher = "4h" if req.scanner_mode else tf_1h[tf]
    tf_top    = "4h" if req.scanner_mode else tf_4h[tf]

    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    higher_days = max(req.period_days + 10, 40)

    raw_main = fetch_ohlcv_paginated(req.symbol, tf, req.period_days)
    raw_1h   = fetch_ohlcv_paginated(req.symbol, tf_higher, higher_days)
    raw_4h   = fetch_ohlcv_paginated(req.symbol, tf_top, higher_days)

    if not raw_main or not raw_1h or not raw_4h:
        raise HTTPException(status_code=502, detail="Не удалось загрузить данные с Bybit")

    df_main = build_features(pd.DataFrame(raw_main, columns=cols))
    df_1h   = build_features(pd.DataFrame(raw_1h,   columns=cols))
    df_4h   = build_features(pd.DataFrame(raw_4h,   columns=cols))

    if len(df_main) < 80:
        raise HTTPException(status_code=400, detail="Недостаточно исторических данных")

    COMM     = req.commission / 100
    SLIP     = req.slippage / 100

    equity         = req.deposit
    max_equity     = req.deposit
    max_drawdown   = 0.0
    wins = losses = bes = 0
    total_comm     = 0.0
    trades_list    = []
    equity_curve   = [{"ts": int(df_main.iloc[0]['timestamp']), "equity": round(equity, 2)}]

    # Состояние открытой позиции
    in_trade        = False
    t_signal        = None
    t_entry         = None
    t_stop          = None
    t_tp1           = None
    t_tp2           = None
    t_tp3           = None
    t_pos           = None
    t_open_i        = None
    t_tp1_hit       = False
    t_be_hit        = False
    t_pre_trail     = False
    t_potential_warned = False

    WARMUP = 60

    for i in range(WARMUP, len(df_main) - 1):
        candle = df_main.iloc[i]
        next_c = df_main.iloc[i + 1]
        ts_now = candle['timestamp']

        # ── УПРАВЛЕНИЕ ОТКРЫТОЙ ПОЗИЦИЕЙ ──────────────────────────────
        if in_trade:
            price  = next_c['close']
            hi     = next_c['high']
            lo     = next_c['low']
            df_now = df_main.iloc[:i + 1]
            result = None
            pnl_p  = 0.0
            exit_p = price

            # 1. Потеря потенциала (до TP1)
            if not t_tp1_hit and not t_potential_warned:
                if _check_potential_loss(df_now, t_signal, t_entry, price):
                    t_potential_warned = True
                    pnl_p  = _pnl(t_signal, t_entry, price * (1 - SLIP if t_signal == 'LONG' else 1 + SLIP))
                    exit_p = price * (1 - SLIP if t_signal == 'LONG' else 1 + SLIP)
                    result = 'potential'

            # 2. Trailing stop до TP1 (70% пути)
            if not result and not t_tp1_hit and not t_pre_trail:
                dist_total = abs(t_tp1 - t_entry)
                dist_done  = abs(price - t_entry)
                if dist_total > 0 and dist_done / dist_total >= 0.70:
                    if t_signal == 'LONG':
                        new_stop = t_entry * 1.003
                        if new_stop > t_stop:
                            t_stop    = new_stop
                            t_be_hit  = True
                            t_pre_trail = True
                    else:
                        new_stop = t_entry * 0.997
                        if new_stop < t_stop:
                            t_stop    = new_stop
                            t_be_hit  = True
                            t_pre_trail = True

            # 3. Стоп
            if not result:
                if t_signal == 'LONG' and lo <= t_stop:
                    exit_p = t_stop * (1 - SLIP)
                    pnl_p  = _pnl(t_signal, t_entry, exit_p)
                    result = 'be' if t_be_hit else 'sl'
                elif t_signal == 'SHORT' and hi >= t_stop:
                    exit_p = t_stop * (1 + SLIP)
                    pnl_p  = _pnl(t_signal, t_entry, exit_p)
                    result = 'be' if t_be_hit else 'sl'

            # 4. TP1 — частичная фиксация 50%
            if not result and not t_tp1_hit:
                if (t_signal == 'LONG' and hi >= t_tp1) or (t_signal == 'SHORT' and lo <= t_tp1):
                    t_tp1_hit = True
                    t_be_hit  = True
                    ep = t_tp1 * (1 - SLIP) if t_signal == 'LONG' else t_tp1 * (1 + SLIP)
                    p  = _pnl(t_signal, t_entry, ep)
                    c  = t_pos * 0.5 * COMM * 2
                    equity += t_pos * 0.5 * (p / 100) - c
                    total_comm += c
                    t_stop = t_entry  # стоп в б/у
                    equity_curve.append({"ts": int(ts_now), "equity": round(equity, 2)})
                    continue

            # 5. Trailing stop после TP1
            if not result and t_tp1_hit:
                atr_now = candle['atr']
                if not pd.isna(atr_now) and atr_now > 0:
                    new_stop = _calc_trailing_stop(t_signal, price, atr_now, t_stop)
                    if abs(new_stop - t_stop) / (t_stop + 1e-10) > 0.003:
                        t_stop = new_stop

            # 6. TP2
            if not result and t_tp1_hit:
                if (t_signal == 'LONG' and hi >= t_tp2) or (t_signal == 'SHORT' and lo <= t_tp2):
                    exit_p = t_tp2 * (1 - SLIP) if t_signal == 'LONG' else t_tp2 * (1 + SLIP)
                    pnl_p  = _pnl(t_signal, t_entry, exit_p)
                    result = 'tp2'

            # 7. TP3
            if not result:
                if (t_signal == 'LONG' and hi >= t_tp3) or (t_signal == 'SHORT' and lo <= t_tp3):
                    exit_p = t_tp3 * (1 - SLIP) if t_signal == 'LONG' else t_tp3 * (1 + SLIP)
                    pnl_p  = _pnl(t_signal, t_entry, exit_p)
                    result = 'tp3'

            # 8. Таймаут (48 баров)
            if not result and i - t_open_i > 48:
                exit_p = price * (1 - SLIP if t_signal == 'LONG' else 1 + SLIP)
                pnl_p  = _pnl(t_signal, t_entry, exit_p)
                result = 'timeout'

            if result:
                # Закрываем оставшиеся 50% (или 100% если TP1 не был достигнут)
                remaining = 0.5 if t_tp1_hit else 1.0
                pnl_usdt  = t_pos * remaining * (pnl_p / 100)
                comm      = t_pos * remaining * COMM * 2
                pnl_usdt -= comm
                total_comm += comm
                equity    += pnl_usdt

                if equity > max_equity:
                    max_equity = equity
                dd = (max_equity - equity) / max_equity * 100
                if dd > max_drawdown:
                    max_drawdown = dd

                if result in ('tp1', 'tp2', 'tp3') or (result == 'timeout' and pnl_usdt > 0):
                    wins += 1
                elif result in ('sl',):
                    losses += 1
                else:
                    bes += 1

                trades_list.append({
                    "i": i, "ts": int(ts_now),
                    "signal": t_signal,
                    "entry": round(t_entry, 6),
                    "exit": round(exit_p, 6),
                    "result": result,
                    "pnl_pct": round(pnl_p, 3),
                    "pnl_usdt": round(pnl_usdt, 2),
                    "commission": round(comm, 3),
                    "equity": round(equity, 2),
                })
                equity_curve.append({"ts": int(next_c['timestamp']), "equity": round(equity, 2)})

                in_trade = False
                t_tp1_hit = t_be_hit = t_pre_trail = t_potential_warned = False
            continue

        # ── ПОИСК ВХОДА (точная логика generate_signal) ───────────────
        df_slice   = df_main.iloc[:i + 1].copy()
        df_1h_sl   = df_1h[df_1h['timestamp'] <= ts_now].copy()
        df_4h_sl   = df_4h[df_4h['timestamp'] <= ts_now].copy()

        if len(df_1h_sl) < 20 or len(df_4h_sl) < 20:
            continue

        regime, adx_1h = detect_regime(df_1h_sl)
        if regime in ('FLAT', 'CHOP'):
            continue

        last     = df_slice.iloc[-1]
        adx_30m  = last['adx'] if not pd.isna(last['adx']) else 0
        if adx_30m < ADX_MIN or pd.isna(last['atr']) or last['atr'] <= 0:
            continue

        signal = None
        if entry_conditions(df_slice, 'LONG') and regime == 'UPTREND':
            signal = 'LONG'
        elif entry_conditions(df_slice, 'SHORT') and regime == 'DOWNTREND':
            signal = 'SHORT'
        if not signal:
            continue

        if not detect_trend_stable(df_slice, signal):
            continue
        if not mtf_confirms(df_4h_sl, df_1h_sl, signal):
            continue
        if not volume_healthy(df_slice):
            continue
        if is_overextended(df_slice, signal):
            continue
        if detect_volume_climax(df_slice):
            continue

        fresh_cross   = detect_ema_cross_fresh(df_slice, signal, max_bars=5)
        has_pullback, _ = detect_pullback(df_slice, signal)
        if not fresh_cross and not has_pullback:
            continue

        score = calc_score(df_slice, df_1h_sl, regime, adx_1h, signal)
        if score < SCORE_MIN:
            continue

        # Вход с проскальзыванием
        raw_e  = last['close']
        entry  = raw_e * (1 + SLIP) if signal == 'LONG' else raw_e * (1 - SLIP)
        atr    = last['atr']
        atr_1h = df_1h_sl.iloc[-1]['atr'] if not pd.isna(df_1h_sl.iloc[-1]['atr']) else atr
        atr_p  = atr / entry if entry > 0 else 0
        sl_m, tp1_m, tp2_m, tp3_m = get_mults(adx_30m, atr_p)

        # Точный расчёт уровней как в scanner.py (с atr_1h)
        atr_blended = atr * 0.35 + atr_1h * 0.65
        d = atr_blended * sl_m
        if signal == 'LONG':
            stop = entry - d
            tp1  = entry + atr_blended * tp1_m
            tp2  = entry + atr_blended * tp2_m
            tp3  = entry + atr_blended * tp3_m
        else:
            stop = entry + d
            tp1  = entry - atr_blended * tp1_m
            tp2  = entry - atr_blended * tp2_m
            tp3  = entry - atr_blended * tp3_m

        risk_usdt = req.deposit * 1.5 / 100
        sl_dist   = abs(entry - stop)
        pos_usdt  = (risk_usdt / sl_dist * entry) if sl_dist > 0 else 0
        pos_usdt  = min(pos_usdt, equity * 0.3)
        if pos_usdt <= 0:
            continue

        # Комиссия за вход
        ec = pos_usdt * COMM
        equity     -= ec
        total_comm += ec

        in_trade  = True
        t_signal  = signal
        t_entry   = entry
        t_stop    = stop
        t_tp1     = tp1
        t_tp2     = tp2
        t_tp3     = tp3
        t_pos     = pos_usdt
        t_open_i  = i
        t_tp1_hit = t_be_hit = t_pre_trail = t_potential_warned = False

    # ── ИТОГИ ─────────────────────────────────────────────────────────
    total    = wins + losses + bes
    winrate  = round(wins / total * 100, 1) if total > 0 else 0
    total_pnl = round((equity - req.deposit) / req.deposit * 100, 2)

    wins_usdt = [t['pnl_usdt'] for t in trades_list if t['pnl_usdt'] > 0]
    loss_usdt = [t['pnl_usdt'] for t in trades_list if t['pnl_usdt'] < 0]
    avg_win   = round(sum(wins_usdt) / len(wins_usdt), 2) if wins_usdt else 0
    avg_loss  = round(sum(loss_usdt) / len(loss_usdt), 2) if loss_usdt else 0
    pf        = round(abs(sum(wins_usdt) / sum(loss_usdt)), 2) if loss_usdt and sum(loss_usdt) != 0 else 0
    avg_pnl   = round(sum(t['pnl_pct'] for t in trades_list) / total, 2) if total > 0 else 0

    eq_curve  = [{"day": idx, "equity": p["equity"], "ts": p["ts"]} for idx, p in enumerate(equity_curve)]

    trades_out = []
    for t in trades_list[-50:]:
        dt = datetime.fromtimestamp(t['ts'] / 1000)
        trades_out.append({
            "id": t["i"], "date": dt.strftime('%Y-%m-%d'), "time": dt.strftime('%H:%M'),
            "signal": t["signal"], "entry": t["entry"],
            "result": t["result"], "pnl_pct": t["pnl_pct"],
            "pnl_usdt": t["pnl_usdt"], "commission": t["commission"],
        })

    return {
        "symbol": req.symbol, "timeframe": tf,
        "scanner_mode": req.scanner_mode,
        "period_days": req.period_days, "candles_used": len(df_main),
        "deposit": req.deposit, "final_equity": round(equity, 2),
        "total_pnl": total_pnl, "max_drawdown": round(max_drawdown, 2),
        "winrate": winrate, "total": total,
        "wins": wins, "losses": losses, "breakeven": bes,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "profit_factor": pf, "avg_pnl": avg_pnl,
        "total_commission": round(total_comm, 2),
        "commission_pct": req.commission, "slippage_pct": req.slippage,
        "equity_curve": eq_curve, "trades": trades_out,
    }