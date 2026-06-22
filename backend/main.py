"""
FastAPI backend — V8 стратегия.
Бэктест использует should_enter() + get_mults() + calc_levels() из nfi_strategy (V8).
"""

import json
import pandas as pd
import time as _time
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
from scanner import start_background_scanner, MAX_OPEN_TRADES
from data_layer import exchange, api_call, build_features, detect_regime, get_active_symbols, CANDIDATES
import nfi_strategy
from nfi_strategy import (
    build_nfi_features, should_enter,
    get_mults, calc_levels, calc_position_size, volatility_position_size,
    backtest_levels, ADX_MIN, get_risk_status
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    start_background_scanner()
    yield


app = FastAPI(title="Crypto Signal App V8", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── API endpoints ────────────────────────────────────────────────

@app.get("/api/signals")
def get_active_signals():
    trades = db.load_trades()
    out = []
    for symbol, t in trades.items():
        candles       = json.loads(t['candles_json'])       if t.get('candles_json')       else []
        entry_reasons = json.loads(t['entry_reasons_json']) if t.get('entry_reasons_json') else []
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


@app.get("/api/market")
def get_market():
    try:
        btc = api_call(exchange.fetch_ticker, 'BTC/USDT') or {}
        eth = api_call(exchange.fetch_ticker, 'ETH/USDT') or {}
        return {
            "btc": {"price": btc.get('last', 0), "change": btc.get('percentage', 0)},
            "eth": {"price": eth.get('last', 0), "change": eth.get('percentage', 0)},
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
             commission: float, slippage: float, single_mode=False, timeframe='1h') -> dict:
    """
    V8 бэктест одной пары. По умолчанию 1h.
    Логика выхода: TP1 фиксирует 50% → стоп в б/у → трейлинг → TP2 → TP3.
    Таймаут 36 свечей.
    """
    COMM = commission / 100
    SLIP = slippage  / 100
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

    try:
        raw = fetch_ohlcv_paginated(symbol, timeframe, period_days)
        if not raw or len(raw) < 50:
            return None
    except Exception:
        return None

    df_main = build_features(pd.DataFrame(raw, columns=cols))
    df_main = build_nfi_features(df_main)  # + Supertrend

    # BTC режим фильтр (только для 1h — на других ТФ пропускаем)
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
                    new_stop = _trailing(t_signal, price, atr_now, t_stop)
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

            # Таймаут 72 свечи (36 часов)
            if not result and i - t_open_i > 36:
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