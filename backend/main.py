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
from signal_engine import get_market_overview, get_mults, calc_levels, calc_position
from data_layer import exchange, api_call, build_features, detect_regime, entry_conditions
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

class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    deposit: float = 1000.0
    limit: int = 500  # количество свечей истории


@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    """
    Реальный бэктест: скачивает исторические свечи с Bybit,
    прогоняет стратегию сканера, симулирует TP/SL на следующих барах.
    """
    # Маппинг таймфреймов для запроса 4h и 1h данных
    tf_map = {"15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d"}
    tf = tf_map.get(req.timeframe, "1h")

    # Нужно больше свечей для 4h и 1h подтверждений
    limit_main = max(req.limit, 300)

    # Скачиваем три таймфрейма (как в живом сканере)
    tf_higher = {"15m": "1h", "30m": "1h", "1h": "4h", "4h": "1d", "1d": "1d"}
    tf_top     = {"15m": "4h", "30m": "4h", "1h": "4h", "4h": "1d", "1d": "1d"}

    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

    raw_main = api_call(exchange.fetch_ohlcv, req.symbol, tf, limit=limit_main)
    raw_1h   = api_call(exchange.fetch_ohlcv, req.symbol, tf_higher[tf], limit=300)
    raw_4h   = api_call(exchange.fetch_ohlcv, req.symbol, tf_top[tf], limit=200)

    if not raw_main or not raw_1h or not raw_4h:
        raise HTTPException(status_code=502, detail="Не удалось загрузить данные с Bybit")

    df_main = build_features(pd.DataFrame(raw_main, columns=cols))
    df_1h   = build_features(pd.DataFrame(raw_1h,   columns=cols))
    df_4h   = build_features(pd.DataFrame(raw_4h,   columns=cols))

    if len(df_main) < 80:
        raise HTTPException(status_code=400, detail="Недостаточно исторических данных")

    equity = req.deposit
    max_equity = req.deposit
    max_drawdown = 0.0
    wins = losses = bes = 0
    trades_list = []
    equity_curve = [{"ts": int(df_main.iloc[0]['timestamp']), "equity": round(equity, 2)}]

    # Минимум 60 свечей для прогрева индикаторов, затем идём по каждой свече
    WARMUP = 60
    in_trade = False
    trade_signal = None
    trade_entry = None
    trade_stop = None
    trade_tp1 = None
    trade_tp2 = None
    trade_tp3 = None
    trade_pos_usdt = None
    trade_open_i = None
    trade_tp1_hit = False

    for i in range(WARMUP, len(df_main) - 1):
        candle = df_main.iloc[i]
        next_c = df_main.iloc[i + 1]

        # ── Если есть открытая позиция — проверяем TP/SL ──
        if in_trade:
            hi = next_c['high']
            lo = next_c['low']
            close_next = next_c['close']
            result = None
            pnl_pct = 0.0

            if trade_signal == 'LONG':
                if lo <= trade_stop:
                    # Стоп
                    exit_price = trade_stop
                    pnl_pct = (exit_price - trade_entry) / trade_entry * 100
                    result = 'sl'
                elif not trade_tp1_hit and hi >= trade_tp1:
                    trade_tp1_hit = True
                    # Частичная фиксация на TP1 (50%), стоп в б/у
                    pnl_pct_partial = (trade_tp1 - trade_entry) / trade_entry * 100
                    equity += trade_pos_usdt * 0.5 * (pnl_pct_partial / 100)
                    trade_stop = trade_entry  # стоп в б/у
                    continue
                elif trade_tp1_hit and hi >= trade_tp2:
                    exit_price = trade_tp2
                    pnl_pct = (exit_price - trade_entry) / trade_entry * 100
                    result = 'tp2'
                elif i - trade_open_i > 48:
                    # Таймаут — закрываем по текущей цене
                    pnl_pct = (close_next - trade_entry) / trade_entry * 100
                    result = 'timeout'
            else:  # SHORT
                if hi >= trade_stop:
                    exit_price = trade_stop
                    pnl_pct = (trade_entry - exit_price) / trade_entry * 100
                    result = 'sl'
                elif not trade_tp1_hit and lo <= trade_tp1:
                    trade_tp1_hit = True
                    pnl_pct_partial = (trade_entry - trade_tp1) / trade_entry * 100
                    equity += trade_pos_usdt * 0.5 * (pnl_pct_partial / 100)
                    trade_stop = trade_entry
                    continue
                elif trade_tp1_hit and lo <= trade_tp2:
                    exit_price = trade_tp2
                    pnl_pct = (trade_entry - exit_price) / trade_entry * 100
                    result = 'tp2'
                elif i - trade_open_i > 48:
                    pnl_pct = (trade_entry - close_next) / trade_entry * 100
                    result = 'timeout'

            if result:
                pnl_usdt = trade_pos_usdt * (pnl_pct / 100)
                equity += pnl_usdt
                if equity > max_equity:
                    max_equity = equity
                dd = (max_equity - equity) / max_equity * 100
                if dd > max_drawdown:
                    max_drawdown = dd

                if result in ('tp1', 'tp2', 'tp3') or (result == 'timeout' and pnl_pct > 0):
                    wins += 1
                elif result == 'sl':
                    losses += 1
                else:
                    bes += 1

                trades_list.append({
                    "i": i,
                    "ts": int(candle['timestamp']),
                    "symbol": req.symbol,
                    "signal": trade_signal,
                    "entry": round(trade_entry, 6),
                    "exit": round(close_next, 6),
                    "result": result,
                    "pnl_pct": round(pnl_pct, 3),
                    "pnl_usdt": round(pnl_usdt, 2),
                    "equity": round(equity, 2),
                })
                equity_curve.append({"ts": int(next_c['timestamp']), "equity": round(equity, 2)})

                in_trade = False
                trade_tp1_hit = False
            continue

        # ── Нет позиции — проверяем условия входа ──
        df_slice = df_main.iloc[:i + 1].copy()

        # Синхронизируем 1h и 4h по времени
        ts_now = candle['timestamp']
        df_1h_slice = df_1h[df_1h['timestamp'] <= ts_now].copy()
        df_4h_slice = df_4h[df_4h['timestamp'] <= ts_now].copy()

        if len(df_1h_slice) < 20 or len(df_4h_slice) < 20:
            continue

        regime, adx_1h = detect_regime(df_1h_slice)
        if regime in ('FLAT', 'CHOP'):
            continue

        last = df_slice.iloc[-1]
        adx_30m = last['adx'] if not pd.isna(last['adx']) else 0
        if adx_30m < 23 or pd.isna(last['atr']) or last['atr'] <= 0:
            continue

        signal = None
        if entry_conditions(df_slice, 'LONG') and regime == 'UPTREND':
            signal = 'LONG'
        elif entry_conditions(df_slice, 'SHORT') and regime == 'DOWNTREND':
            signal = 'SHORT'
        if not signal:
            continue

        # Мультитаймфрейм подтверждение
        l4 = df_4h_slice.iloc[-1]
        l1 = df_1h_slice.iloc[-1]
        if signal == 'LONG':
            if not (l4['ema9'] > l4['ema21'] and l1['ema9'] > l1['ema21']):
                continue
        else:
            if not (l4['ema9'] < l4['ema21'] and l1['ema9'] < l1['ema21']):
                continue

        # Открываем позицию
        entry = last['close']
        atr = last['atr']
        atr_pct = atr / entry if entry > 0 else 0
        sl_m, tp1_m, tp2_m, tp3_m = get_mults(adx_30m, atr_pct)

        # Упрощённый расчёт уровней (без 1h ATR для скорости)
        d = atr * sl_m
        if signal == 'LONG':
            stop = entry - d
            tp1  = entry + atr * tp1_m
            tp2  = entry + atr * tp2_m
        else:
            stop = entry + d
            tp1  = entry - atr * tp1_m
            tp2  = entry - atr * tp2_m

        risk_usdt = req.deposit * 1.5 / 100
        sl_dist = abs(entry - stop)
        pos_usdt = (risk_usdt / sl_dist * entry) if sl_dist > 0 else 0
        pos_usdt = min(pos_usdt, equity * 0.3)  # не более 30% баланса

        if pos_usdt <= 0:
            continue

        in_trade = True
        trade_signal = signal
        trade_entry = entry
        trade_stop = stop
        trade_tp1 = tp1
        trade_tp2 = tp2
        trade_pos_usdt = pos_usdt
        trade_open_i = i
        trade_tp1_hit = False

    # Итоговая статистика
    total = wins + losses + bes
    winrate = round(wins / total * 100, 1) if total > 0 else 0
    total_pnl = round((equity - req.deposit) / req.deposit * 100, 2)
    avg_pnl = round(
        sum(t['pnl_pct'] for t in trades_list) / total, 2
    ) if total > 0 else 0

    wins_pnl = [t['pnl_pct'] for t in trades_list if t['pnl_pct'] > 0]
    loss_pnl = [t['pnl_pct'] for t in trades_list if t['pnl_pct'] < 0]
    avg_win  = round(sum(wins_pnl) / len(wins_pnl), 2) if wins_pnl else 0
    avg_loss = round(sum(loss_pnl) / len(loss_pnl), 2) if loss_pnl else 0
    profit_factor = round(
        abs(sum(wins_pnl) / sum(loss_pnl)), 2
    ) if loss_pnl and sum(loss_pnl) != 0 else 0

    # Форматируем кривую для фронтенда (добавляем day-индекс)
    equity_curve_out = [
        {"day": idx, "equity": p["equity"], "ts": p["ts"]}
        for idx, p in enumerate(equity_curve)
    ]

    # Последние 30 сделок для таблицы
    trades_out = []
    for t in trades_list[-30:]:
        dt = datetime.fromtimestamp(t['ts'] / 1000)
        trades_out.append({
            "id": t["i"],
            "date": dt.strftime('%Y-%m-%d'),
            "time": dt.strftime('%H:%M'),
            "signal": t["signal"],
            "entry": t["entry"],
            "result": t["result"],
            "pnl_pct": t["pnl_pct"],
            "pnl_usdt": t["pnl_usdt"],
        })

    return {
        "symbol": req.symbol,
        "timeframe": tf,
        "candles_used": len(df_main),
        "deposit": req.deposit,
        "final_equity": round(equity, 2),
        "total_pnl": total_pnl,
        "max_drawdown": round(max_drawdown, 2),
        "winrate": winrate,
        "total": total,
        "wins": wins,
        "losses": losses,
        "breakeven": bes,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "avg_pnl": avg_pnl,
        "equity_curve": equity_curve_out,
        "trades": trades_out,
    }
