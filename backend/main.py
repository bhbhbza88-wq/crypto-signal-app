"""
FastAPI backend — отдаёт активные сигналы, историю сделок и статистику фронтенду.
Бэктест использует NFI стратегию (EWO + BB).
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
from data_layer import exchange, api_call, build_features, detect_regime, get_active_symbols
from nfi_strategy import (
    build_nfi_features, should_enter, calc_ewo, calc_bollinger_bands,
    get_mults, calc_levels, calc_position_size
)
import pandas as pd
import time as _time


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
        "today": _summarize(today_trades),
        "week": _summarize(week_trades),
        "all_time": _summarize(history),
    }


def _summarize(trades):
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


# ─── BACKTEST ────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    deposit: float = 1000.0
    period_days: int = 30
    commission: float = 0.055
    slippage: float = 0.05


def fetch_ohlcv_paginated(symbol: str, tf: str, days: int) -> list:
    """Загружает OHLCV данные с Bybit."""
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


def _calc_trailing_stop(signal, price, atr, current_stop):
    """Трейлинг стоп."""
    if signal == 'LONG':
        return max(price - atr * 0.8, current_stop)
    else:
        return min(price + atr * 0.8, current_stop)


@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    """
    NFI-бэктест: EWO + BB логика на 30m таймфрейме.
    Ровно как живая стратегия в scanner.py.
    """
    # Используем 30m для NFI
    tf = "30m"
    COMM = req.commission / 100
    SLIP = req.slippage / 100
    DEPOSIT = req.deposit
    
    try:
        raw = fetch_ohlcv_paginated(req.symbol, tf, req.period_days)
        if not raw or len(raw) < 50:
            return {"error": "Недостаточно данных"}
    except Exception as e:
        return {"error": str(e)}
    
    # Подготавливаем данные
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df_raw = pd.DataFrame(raw, columns=cols)
    df_main = build_features(df_raw)
    df_main = build_nfi_features(df_main)
    
    in_trade = False
    t_signal = t_entry = t_stop = t_tp1 = t_tp2 = t_tp3 = t_pos = 0
    t_open_i = 0
    t_tp1_hit = t_be_hit = False
    
    equity = DEPOSIT
    max_equity = DEPOSIT
    max_drawdown = 0
    wins = losses = bes = 0
    trades_list = []
    equity_curve = []
    total_comm = 0
    
    # Основной цикл бэктеста
    for i in range(1, len(df_main)):
        candle = df_main.iloc[i]
        ts_now = candle['timestamp']
        price = candle['close']
        hi = candle['high']
        lo = candle['low']
        
        # Если в сделке — проверяем выход
        if in_trade:
            # 1. Стоп
            if t_signal == 'LONG' and lo <= t_stop:
                exit_p = t_stop * (1 - SLIP)
                pnl_p = _pnl(t_signal, t_entry, exit_p)
                result = 'be' if t_be_hit else 'sl'
            elif t_signal == 'SHORT' and hi >= t_stop:
                exit_p = t_stop * (1 + SLIP)
                pnl_p = _pnl(t_signal, t_entry, exit_p)
                result = 'be' if t_be_hit else 'sl'
            else:
                result = None
            
            # 2. TP1 — фиксируем 70%, стоп в б/у
            if not result and not t_tp1_hit:
                if (t_signal == 'LONG' and hi >= t_tp1) or (t_signal == 'SHORT' and lo <= t_tp1):
                    t_tp1_hit = True
                    t_be_hit = True
                    ep = t_tp1 * (1 - SLIP) if t_signal == 'LONG' else t_tp1 * (1 + SLIP)
                    p = _pnl(t_signal, t_entry, ep)
                    c = t_pos * 0.7 * COMM * 2
                    equity += t_pos * 0.7 * (p / 100) - c
                    total_comm += c
                    t_stop = t_entry
                    equity_curve.append({"ts": int(ts_now), "equity": round(equity, 2)})
                    continue
            
            # 3. Трейлинг стоп после TP1
            if not result and t_tp1_hit:
                atr_now = candle['atr']
                if not pd.isna(atr_now) and atr_now > 0:
                    new_stop = _calc_trailing_stop(t_signal, price, atr_now, t_stop)
                    if abs(new_stop - t_stop) / (t_stop + 1e-10) > 0.003:
                        t_stop = new_stop
            
            # 4. TP2
            if not result and t_tp1_hit:
                if (t_signal == 'LONG' and hi >= t_tp2) or (t_signal == 'SHORT' and lo <= t_tp2):
                    exit_p = t_tp2 * (1 - SLIP) if t_signal == 'LONG' else t_tp2 * (1 + SLIP)
                    pnl_p = _pnl(t_signal, t_entry, exit_p)
                    result = 'tp2'
            
            # 5. TP3
            if not result:
                if (t_signal == 'LONG' and hi >= t_tp3) or (t_signal == 'SHORT' and lo <= t_tp3):
                    exit_p = t_tp3 * (1 - SLIP) if t_signal == 'LONG' else t_tp3 * (1 + SLIP)
                    pnl_p = _pnl(t_signal, t_entry, exit_p)
                    result = 'tp3'
            
            # 6. Таймаут (48 свечей)
            if not result and i - t_open_i > 48:
                exit_p = price * (1 - SLIP if t_signal == 'LONG' else 1 + SLIP)
                pnl_p = _pnl(t_signal, t_entry, exit_p)
                result = 'timeout'
            
            if result:
                remaining = 0.3 if t_tp1_hit else 1.0
                pnl_usdt = t_pos * remaining * (pnl_p / 100)
                comm = t_pos * remaining * COMM * 2
                pnl_usdt -= comm
                total_comm += comm
                equity += pnl_usdt
                
                if equity > max_equity:
                    max_equity = equity
                dd = (max_equity - equity) / max_equity * 100
                if dd > max_drawdown:
                    max_drawdown = dd
                
                if result in ('tp1', 'tp2', 'tp3') or (result == 'timeout' and pnl_usdt > 0):
                    wins += 1
                elif result == 'be' and pnl_usdt > 0:
                    result = 'tp1'
                    wins += 1
                elif result == 'sl':
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
                equity_curve.append({"ts": int(ts_now), "equity": round(equity, 2)})
                
                in_trade = False
                t_tp1_hit = t_be_hit = False
            continue
        
        # ── ПОИСК ВХОДА (NFI логика) ───────────────────────────────────────
        df_slice = df_main.iloc[:i + 1].copy()
        
        if len(df_slice) < 50:
            continue
        
        last = df_slice.iloc[-1]
        
        # NFI условия входа
        signal = None
        if should_enter(df_slice, 'LONG'):
            signal = 'LONG'
        elif should_enter(df_slice, 'SHORT'):
            signal = 'SHORT'
        
        if not signal:
            continue
        
        # Базовые проверки
        if pd.isna(last['atr']) or last['atr'] <= 0:
            continue
        
        # Расчёт уровней (из nfi_strategy)
        entry = last['close']
        atr = last['atr']
        atr_pct = atr / entry if entry > 0 else 0
        
        sl_m, tp1_m, tp2_m = get_mults(atr_pct)
        stop, tp1, tp2 = calc_levels(signal, entry, atr, sl_m, tp1_m, tp2_m)
        tp3 = tp2 * 1.5  # Дополнительный уровень
        
        pos_usdt = calc_position_size(entry, stop)
        if pos_usdt <= 0:
            continue
        
        # Комиссия за вход
        ec = pos_usdt * COMM
        equity -= ec
        total_comm += ec
        
        in_trade = True
        t_signal = signal
        t_entry = entry
        t_stop = stop
        t_tp1 = tp1
        t_tp2 = tp2
        t_tp3 = tp3
        t_pos = pos_usdt
        t_open_i = i
        t_tp1_hit = t_be_hit = False
    
    # ── ИТОГИ ─────────────────────────────────────────────────────────
    total = wins + losses + bes
    winrate = round(wins / total * 100, 1) if total > 0 else 0
    total_pnl = round((equity - req.deposit) / req.deposit * 100, 2)
    
    wins_usdt = [t['pnl_usdt'] for t in trades_list if t['pnl_usdt'] > 0]
    loss_usdt = [t['pnl_usdt'] for t in trades_list if t['pnl_usdt'] < 0]
    avg_win = round(sum(wins_usdt) / len(wins_usdt), 2) if wins_usdt else 0
    avg_loss = round(sum(loss_usdt) / len(loss_usdt), 2) if loss_usdt else 0
    pf = round(abs(sum(wins_usdt) / sum(loss_usdt)), 2) if loss_usdt and sum(loss_usdt) != 0 else 0
    avg_pnl = round(sum(t['pnl_pct'] for t in trades_list) / total, 2) if total > 0 else 0
    
    eq_curve = [{"day": idx, "equity": p["equity"], "ts": p["ts"]} for idx, p in enumerate(equity_curve)]
    
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