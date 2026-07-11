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
            ("trader_id", "INTEGER"),
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
        hist_cols = [r[1] for r in conn.execute("PRAGMA table_info(history)").fetchall()]
        if 'trader_id' not in hist_cols:
            conn.execute("ALTER TABLE history ADD COLUMN trader_id INTEGER")
            print("✅ Миграция: добавлена колонка trader_id в history")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, kind TEXT, message TEXT,
                created_at TEXT
            )
        """)
        # ── Cross-sectional momentum (отдельная стратегия) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS xsec_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                equity REAL,
                last_rebalance_ts INTEGER,
                positions_json TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS xsec_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER,
                date TEXT,
                equity REAL,
                period_return_pct REAL,
                longs_json TEXT,
                shorts_json TEXT
            )
        """)
        # ── Trend-Following (отдельная стратегия) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trend_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_check_ts INTEGER,
                positions_json TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trend_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER,
                date TEXT,
                symbol TEXT,
                entry REAL,
                exit REAL,
                pnl_pct REAL
            )
        """)
        # ── Пользователи и сессии (монетизация) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT,
                expires_at TEXT
            )
        """)
        # Миграция: free-триал Premium при регистрации (колонка могла отсутствовать)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if 'trial_ends_at' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN trial_ends_at TEXT")
        if 'is_admin' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")

        # ── Трейдеры (авторы сигналов) ────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                avatar_url TEXT,
                bio TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
        trader_cols = [r[1] for r in conn.execute("PRAGMA table_info(traders)").fetchall()]
        if 'source_url' not in trader_cols:
            conn.execute("ALTER TABLE traders ADD COLUMN source_url TEXT")
        if 'source_type' not in trader_cols:
            conn.execute("ALTER TABLE traders ADD COLUMN source_type TEXT DEFAULT 'manual'")
            print("✅ Миграция: добавлены колонки source_url, source_type в traders")


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
                 opened_at, candles_json, entry_reasons_json, position_size, trader_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                signal=excluded.signal, entry=excluded.entry, stop=excluded.stop,
                tp1=excluded.tp1, tp2=excluded.tp2, tp3=excluded.tp3,
                score=excluded.score, regime=excluded.regime,
                tp1_hit=excluded.tp1_hit, tp2_hit=excluded.tp2_hit,
                be_hit=excluded.be_hit, potential_warned=excluded.potential_warned,
                pre_tp1_trail=excluded.pre_tp1_trail,
                candles_json=excluded.candles_json,
                entry_reasons_json=excluded.entry_reasons_json,
                position_size=excluded.position_size,
                trader_id=excluded.trader_id
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
            trade.get('trader_id'),
        ))


def remove_trade(symbol):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM open_trades WHERE symbol=?", (symbol,))


# ── History ──────────────────────────────────────────────
def add_to_history(symbol, signal, entry, result, pnl, trader_id=None):
    now = datetime.now()
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO history (date, time, symbol, signal, entry, result, pnl, trader_id)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
            symbol, signal, entry, result, round(pnl, 2), trader_id,
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


# ── Cross-sectional momentum state ────────────────────────
def xsec_get_state():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM xsec_state WHERE id=1").fetchone()
        return dict(row) if row else None


def xsec_save_state(equity, last_rebalance_ts, positions_json):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO xsec_state (id, equity, last_rebalance_ts, positions_json)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                equity=excluded.equity,
                last_rebalance_ts=excluded.last_rebalance_ts,
                positions_json=excluded.positions_json
        """, (equity, last_rebalance_ts, positions_json))


def xsec_add_log(ts, equity, period_return_pct, longs_json, shorts_json):
    dt = datetime.fromtimestamp(ts / 1000) if ts > 1e12 else datetime.fromtimestamp(ts)
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO xsec_log (ts, date, equity, period_return_pct, longs_json, shorts_json)
            VALUES (?,?,?,?,?,?)
        """, (ts, dt.strftime('%Y-%m-%d %H:%M'), equity, period_return_pct, longs_json, shorts_json))


def xsec_load_log(limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM xsec_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Trend-Following state ─────────────────────────────────
def trend_get_state():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM trend_state WHERE id=1").fetchone()
        return dict(row) if row else None


def trend_save_state(last_check_ts, positions_json):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO trend_state (id, last_check_ts, positions_json)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_check_ts=excluded.last_check_ts,
                positions_json=excluded.positions_json
        """, (last_check_ts, positions_json))


def trend_add_log(ts, symbol, entry, exit_price, pnl_pct):
    dt = datetime.fromtimestamp(ts / 1000) if ts > 1e12 else datetime.fromtimestamp(ts)
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO trend_log (ts, date, symbol, entry, exit, pnl_pct)
            VALUES (?,?,?,?,?,?)
        """, (ts, dt.strftime('%Y-%m-%d %H:%M'), symbol, entry, exit_price, pnl_pct))


def trend_load_log(limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trend_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Пользователи / сессии ─────────────────────────────────
def create_user(email, password_hash, salt, tier='free', trial_ends_at=None):
    with _lock, get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO users (email, password_hash, salt, tier, created_at, trial_ends_at)
            VALUES (?,?,?,?,?,?)
        """, (email.lower().strip(), password_hash, salt, tier, datetime.now().isoformat(), trial_ends_at))
        return cur.lastrowid


def get_user_by_email(email):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def set_user_tier(user_id, tier):
    with _lock, get_conn() as conn:
        conn.execute("UPDATE users SET tier=? WHERE id=?", (tier, user_id))


def set_user_admin(user_id, is_admin: bool):
    with _lock, get_conn() as conn:
        conn.execute("UPDATE users SET is_admin=? WHERE id=?", (int(is_admin), user_id))


def create_session(token, user_id, expires_at):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO sessions (token, user_id, created_at, expires_at)
            VALUES (?,?,?,?)
        """, (token, user_id, datetime.now().isoformat(), expires_at))


def get_user_by_token(token):
    """Возвращает пользователя по валидной (не истёкшей) сессии, иначе None."""
    if not token:
        return None
    with get_conn() as conn:
        row = conn.execute("""
            SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token=? AND s.expires_at > ?
        """, (token, datetime.now().isoformat())).fetchone()
        return dict(row) if row else None


def delete_session(token):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))


# ── Трейдеры (авторы сигналов) ────────────────────────────
def create_trader(name, avatar_url=None, bio=None, source_url=None, source_type='manual'):
    with _lock, get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO traders (name, avatar_url, bio, is_active, created_at, source_url, source_type)
            VALUES (?,?,?,1,?,?,?)
        """, (name, avatar_url, bio, datetime.now().isoformat(), source_url, source_type))
        return cur.lastrowid


def get_trader(trader_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM traders WHERE id=?", (trader_id,)).fetchone()
        return dict(row) if row else None


def get_or_create_trader(name, bio=None):
    """Для автоматических источников сигналов (TradingView и т.п.) —
    заводит трейдера по имени при первом сигнале, дальше переиспользует.
    Гонка при параллельных вебхуках безвредна: UNIQUE не нужен, дубль
    просто получит свою отдельную (пустую) статистику, а не сломает данные."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM traders WHERE name=?", (name,)).fetchone()
        if row:
            return row['id']
    return create_trader(name, avatar_url=None, bio=bio or "Автоматический источник (TradingView)")


def get_or_create_source_trader(name, source_url=None, source_type='manual', bio=None):
    """Как get_or_create_trader, но для источников с атрибуцией (Telegram-агрегатор
    и т.п.) — хранит source_url/source_type, чтобы фронт мог честно показать
    происхождение сигнала и не путать его с ручными/собственными."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM traders WHERE name=?", (name,)).fetchone()
        if row:
            return row['id']
    return create_trader(name, avatar_url=None, bio=bio, source_url=source_url, source_type=source_type)


def list_traders(only_active=False):
    """Трейдеры с честной статистикой, посчитанной прямо из history/open_trades
    (не денормализованные счётчики — исключает рассинхрон)."""
    with get_conn() as conn:
        traders = conn.execute(
            "SELECT * FROM traders" + (" WHERE is_active=1" if only_active else "") + " ORDER BY id"
        ).fetchall()
        out = []
        for t in traders:
            t = dict(t)
            hist = conn.execute(
                "SELECT result, pnl FROM history WHERE trader_id=?", (t['id'],)
            ).fetchall()
            open_count = conn.execute(
                "SELECT COUNT(*) c FROM open_trades WHERE trader_id=?", (t['id'],)
            ).fetchone()['c']
            closed = len(hist)
            wins = sum(1 for h in hist if h['pnl'] > 0)
            total_pnl = sum(h['pnl'] for h in hist)
            t['closed_trades'] = closed
            t['open_positions'] = open_count
            t['winrate'] = round(wins / closed * 100, 1) if closed else None
            t['total_pnl'] = round(total_pnl, 2)
            out.append(t)
        return out


def update_trader(trader_id, name=None, avatar_url=None, bio=None, is_active=None):
    fields, values = [], []
    if name is not None:       fields.append("name=?");       values.append(name)
    if avatar_url is not None: fields.append("avatar_url=?"); values.append(avatar_url)
    if bio is not None:        fields.append("bio=?");        values.append(bio)
    if is_active is not None:  fields.append("is_active=?");  values.append(int(is_active))
    if not fields:
        return
    values.append(trader_id)
    with _lock, get_conn() as conn:
        conn.execute(f"UPDATE traders SET {', '.join(fields)} WHERE id=?", values)