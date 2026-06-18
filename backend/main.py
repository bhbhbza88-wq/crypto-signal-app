"""
FastAPI backend — отдаёт активные сигналы, историю сделок и статистику фронтенду.
Запуск: uvicorn main:app --reload --port 8000
"""

import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import database as db
from scanner import start_background_scanner
from signal_engine import get_market_overview


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
