"""
Database — SQLite хранилище для открытых сделок и истории.
Заменяет open_trades.json / trades_history.json из бота.
"""

import sqlite3
import json
import threading
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "trading_app.db"
_lock = threading.Lock()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS open_trades (
                symbol TEXT PRIMARY KEY,
                signal TEXT NOT NULL,
                entry REAL NOT NULL,
                stop REAL NOT NULL,
                tp1 REAL NOT NULL,
                tp2 REAL NOT NULL,
                tp3 REAL NOT NULL,
                score INTEGER,
                regime TEXT,
                tp1_hit INTEGER DEFAULT 0,
                tp2_hit INTEGER DEFAULT 0,
                be_hit INTEGER DEFAULT 0,
                potential_warned INTEGER DEFAULT 0,
                pre_tp1_trail INTEGER DEFAULT 0,
                opened_at TEXT,
                candles_json TEXT,
                entry_reasons_json TEXT,
                position_size REAL
            )
        """)
        # Миграция: добавляем колонки если их нет (для старых БД)
        existing = [r[1] for r in conn.execute("PRAGMA table_info(open_trades)").fetchall()]
        for col, typedef in [
            ("pre_tp1_trail", "INTEGER DEFAULT 0"),
            ("position_size", "REAL"),
            ("candles_json", "TEXT"),
            ("entry_reasons_json", "TEXT"),
            ("dca_done", "INTEGER DEFAULT 0"),
        ]:
            if col not in existing:
                conn.execute(f"ALTER TABLE open_trades ADD COLUMN {col} {typedef}")
                print(f"✅ Миграция: добавлена колонка {col}")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, time TEXT,
                symbol TEXT, signal TEXT,
                entry REAL, result TEXT, pnl REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, kind TEXT, message TEXT,
                created_at TEXT
            )
        """)


# ── Open trades ──────────────────────────────────────────
def load_trades():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM open_trades").fetchall()
        return {r['symbol']: dict(r) for r in rows}


def get_trade(symbol):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM open_trades WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row else None


def upsert_trade(symbol, trade: dict):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO open_trades
                (symbol, signal, entry, stop, tp1, tp2, tp3, score, regime,
                 tp1_hit, tp2_hit, be_hit, potential_warned, pre_tp1_trail,
                 opened_at, candles_json, entry_reasons_json, position_size)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                signal=excluded.signal, entry=excluded.entry, stop=excluded.stop,
                tp1=excluded.tp1, tp2=excluded.tp2, tp3=excluded.tp3,
                score=excluded.score, regime=excluded.regime,
                tp1_hit=excluded.tp1_hit, tp2_hit=excluded.tp2_hit,
                be_hit=excluded.be_hit, potential_warned=excluded.potential_warned,
                pre_tp1_trail=excluded.pre_tp1_trail,
                candles_json=excluded.candles_json,
                entry_reasons_json=excluded.entry_reasons_json,
                position_size=excluded.position_size
        """, (
            symbol, trade['signal'], trade['entry'], trade['stop'],
            trade['tp1'], trade['tp2'], trade['tp3'],
            trade.get('score'), trade.get('regime'),
            int(trade.get('tp1_hit', False)), int(trade.get('tp2_hit', False)),
            int(trade.get('be_hit', False)), int(trade.get('potential_warned', False)),
            int(trade.get('pre_tp1_trail', False)),
            trade.get('opened_at', datetime.now().isoformat()),
            trade.get('candles_json'),
            trade.get('entry_reasons_json'),
            trade.get('position_size'),
        ))


def remove_trade(symbol):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM open_trades WHERE symbol=?", (symbol,))


# ── History ──────────────────────────────────────────────
def add_to_history(symbol, signal, entry, result, pnl):
    now = datetime.now()
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO history (date, time, symbol, signal, entry, result, pnl)
            VALUES (?,?,?,?,?,?,?)
        """, (
            now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
            symbol, signal, entry, result, round(pnl, 2),
        ))
    print(f"📝 {symbol} {result} {pnl:+.1f}%")


def load_history(limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def history_for_date(date_str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM history WHERE date=? ORDER BY id", (date_str,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Events (заменяет уведомления, которые раньше шли в TG) ─
def add_event(symbol, kind, message):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO events (symbol, kind, message, created_at)
            VALUES (?,?,?,?)
        """, (symbol, kind, message, datetime.now().isoformat()))


def load_events(limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]