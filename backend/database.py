"""
Database — SQLite хранилище для открытых сделок и истории.
Заменяет open_trades.json / trades_history.json из бота.
"""

import os
import sqlite3
import json
import threading
from datetime import datetime
from contextlib import contextmanager

# DATA_DIR указывает на примонтированный persistent volume в проде (Railway) —
# без него SQLite-файл живёт на эфемерной файловой системе контейнера и полностью
# стирается при каждом деплое (случилось на практике: пропадали все пользователи,
# открытые позиции, история). Локально DATA_DIR не задан -> поведение прежнее.
DATA_DIR = os.getenv("DATA_DIR", ".")
DB_PATH = os.path.join(DATA_DIR, "trading_app.db")
_lock = threading.Lock()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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
            ("exchange", "TEXT DEFAULT 'bybit'"),
            ("listed_on", "TEXT DEFAULT 'bybit'"),
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
        if 'email_verified' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
            # Старые аккаунты не блокируем — считаем уже подтверждёнными
            conn.execute("UPDATE users SET email_verified=1")
        if 'google_id' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
        if 'telegram_id' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN telegram_id INTEGER")
            print("✅ Миграция: добавлена колонка telegram_id в users")
        if 'premium_until' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN premium_until TEXT")
            print("✅ Миграция: добавлена колонка premium_until в users")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS premium_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                created_at TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT,
                expires_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id, kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_trader ON history(trader_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_date ON history(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")

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

        # ── Кэш готового отчёта по каналу (Channel Analyzer) ──────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_stats (
                channel TEXT PRIMARY KEY,
                period_days INTEGER,
                total_signals INTEGER,
                checked INTEGER,
                closed_trades INTEGER,
                wins INTEGER,
                losses INTEGER,
                winrate_pct REAL,
                avg_risk_reward REAL,
                total_pnl_pct REAL,
                equity_curve_json TEXT,
                last_analyzed_at TEXT
            )
        """)
        cs_cols = [r[1] for r in conn.execute("PRAGMA table_info(channel_stats)").fetchall()]
        for col, typedef in [("tp2_hit_rate", "REAL"), ("tp2_sample", "INTEGER"),
                              ("tp3_hit_rate", "REAL"), ("tp3_sample", "INTEGER"),
                              ("total_pnl_usd", "REAL"),
                              # Параметры, с которыми считался кэш — без них повторный запрос с другими
                              # days/entry_timeout/max_hold/risk молча получал бы старый отчёт под чужими
                              # настройками (реальный баг: анализ на 7д "залипал" при запросе на 30д).
                              ("entry_timeout_hours", "INTEGER"), ("max_hold_hours", "INTEGER"),
                              ("risk_per_trade_usd", "REAL")]:
            if col not in cs_cols:
                conn.execute(f"ALTER TABLE channel_stats ADD COLUMN {col} {typedef}")

        # ── Исторические сигналы каналов (для channel_backtest.py, офлайн-анализ) ─
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historical_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry REAL NOT NULL,
                stop REAL NOT NULL,
                tp1 REAL NOT NULL,
                posted_at TEXT NOT NULL,
                entry_filled INTEGER DEFAULT 0,
                entry_filled_at TEXT,
                outcome TEXT,
                exit_price REAL,
                pnl_pct REAL,
                checked_at TEXT,
                UNIQUE(channel, message_id)
            )
        """)
        # Миграция: TP2/TP3 (только если канал сам их назвал — NULL иначе,
        # никогда не достраиваем сами) + флаги, дошла ли цена дальше TP1
        hist_cols = [r[1] for r in conn.execute("PRAGMA table_info(historical_signals)").fetchall()]
        for col, typedef in [("tp2", "REAL"), ("tp3", "REAL"), ("tp2_hit", "INTEGER"), ("tp3_hit", "INTEGER"),
                              ("pnl_usd", "REAL"), ("position_size", "REAL")]:
            if col not in hist_cols:
                conn.execute(f"ALTER TABLE historical_signals ADD COLUMN {col} {typedef}")

        # ── Chat engage: куда писали про вход (чтобы закрытие ушло в те же чаты)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_engage_posts (
                symbol TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                msg_id INTEGER,
                chat_ref TEXT,
                created_at TEXT,
                PRIMARY KEY (symbol, chat_id)
            )
        """)
        # Живые фразы из чатов — стиль для engage
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_style_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_ref TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_style_chat ON chat_style_samples(chat_ref)"
        )
        # Чистим протухшие сессии/токены при старте, чтобы БД не пухла.
        now = datetime.now().isoformat()
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (now,))


def replace_chat_style_samples(chat_ref: str, texts: list) -> int:
    """Заменить сэмплы одного чата новым набором. Возвращает сколько записали."""
    chat_ref = (chat_ref or "").lstrip("@").strip()
    cleaned = []
    seen = set()
    for t in texts or []:
        s = " ".join(str(t).split()).strip()
        if len(s) < 4 or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM chat_style_samples WHERE chat_ref=?", (chat_ref,))
        now = datetime.now().isoformat()
        for s in cleaned:
            conn.execute(
                "INSERT INTO chat_style_samples (chat_ref, text, created_at) VALUES (?,?,?)",
                (chat_ref, s, now),
            )
    return len(cleaned)


def list_chat_style_samples(limit: int = 80, chat_ref: str | None = None) -> list:
    with get_conn() as conn:
        if chat_ref:
            rows = conn.execute(
                "SELECT * FROM chat_style_samples WHERE chat_ref=? ORDER BY id DESC LIMIT ?",
                (chat_ref.lstrip("@"), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM chat_style_samples ORDER BY RANDOM() LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def count_chat_style_samples() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM chat_style_samples").fetchone()
        return int(row["n"] if row else 0)


def trim_chat_style_samples(max_total: int = 250) -> None:
    with _lock, get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM chat_style_samples").fetchone()["n"]
        if n <= max_total:
            return
        drop = n - max_total
        conn.execute(
            """
            DELETE FROM chat_style_samples WHERE id IN (
                SELECT id FROM chat_style_samples ORDER BY id ASC LIMIT ?
            )
            """,
            (drop,),
        )


def save_chat_engage_post(symbol: str, chat_id: int, msg_id: int, chat_ref: str = ""):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO chat_engage_posts (symbol, chat_id, msg_id, chat_ref, created_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(symbol, chat_id) DO UPDATE SET
                msg_id=excluded.msg_id,
                chat_ref=excluded.chat_ref,
                created_at=excluded.created_at
        """, (symbol, chat_id, msg_id, chat_ref, datetime.now().isoformat()))


def list_chat_engage_posts(symbol: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_engage_posts WHERE symbol=?", (symbol,)
        ).fetchall()
        return [dict(r) for r in rows]


def clear_chat_engage_posts(symbol: str):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM chat_engage_posts WHERE symbol=?", (symbol,))


# ── Open trades ──────────────────────────────────────────
def load_trades():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM open_trades").fetchall()
        return {r['symbol']: dict(r) for r in rows}


def get_trade(symbol):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM open_trades WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row else None


def insert_trade_if_not_exists(symbol, trade: dict) -> int:
    """Атомарная вставка новой позиции: INSERT ... ON CONFLICT(symbol) DO NOTHING.

    В отличие от upsert_trade (который апдейтит существующую позицию и
    используется трекером для tp1_hit/trailing и т.п.), этот метод никогда
    не перезаписывает уже открытую сделку — конфликт по symbol просто
    отбрасывается на уровне БД под тем же _lock, что закрывает TOCTOU-окно
    между db.get_trade() и записью в open_signal().

    Возвращает rowcount: 1 если позиция реально создана, 0 если symbol
    уже был открыт (вызывающая сторона должна трактовать 0 как 'already_open').
    """
    with _lock, get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO open_trades
                (symbol, signal, entry, stop, tp1, tp2, tp3, score, regime,
                 tp1_hit, tp2_hit, be_hit, potential_warned, pre_tp1_trail,
                 opened_at, candles_json, entry_reasons_json, position_size, trader_id,
                 exchange, listed_on)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO NOTHING
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
            trade.get('exchange') or 'bybit',
            trade.get('listed_on') or (trade.get('exchange') or 'bybit'),
        ))
        return cur.rowcount


def upsert_trade(symbol, trade: dict):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO open_trades
                (symbol, signal, entry, stop, tp1, tp2, tp3, score, regime,
                 tp1_hit, tp2_hit, be_hit, potential_warned, pre_tp1_trail,
                 opened_at, candles_json, entry_reasons_json, position_size, trader_id,
                 exchange, listed_on)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                trader_id=excluded.trader_id,
                exchange=excluded.exchange,
                listed_on=excluded.listed_on
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
            trade.get('exchange') or 'bybit',
            trade.get('listed_on') or (trade.get('exchange') or 'bybit'),
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


def channel_daily_stats(days: int = 14):
    """Сделки по каналам (traders) за последние N дней: total / wins / pnl."""
    from datetime import timedelta
    days = max(1, min(int(days or 14), 90))
    since = (datetime.now() - timedelta(days=days - 1)).strftime('%Y-%m-%d')
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                h.date AS date,
                COALESCE(t.id, 0) AS trader_id,
                COALESCE(t.name, 'Без канала / старое') AS channel,
                COALESCE(t.source_type, 'unknown') AS source_type,
                COUNT(*) AS total,
                SUM(CASE WHEN h.pnl > 0 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN h.pnl < 0 THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN h.pnl = 0 THEN 1 ELSE 0 END) AS breakeven,
                COALESCE(SUM(h.pnl), 0) AS total_pnl
            FROM history h
            LEFT JOIN traders t ON t.id = h.trader_id
            WHERE h.date >= ?
            GROUP BY h.date, t.id, t.name, t.source_type
            ORDER BY h.date DESC, total DESC, channel ASC
        """, (since,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            total = int(d['total'] or 0)
            wins = int(d['wins'] or 0)
            d['total'] = total
            d['wins'] = wins
            d['losses'] = int(d['losses'] or 0)
            d['breakeven'] = int(d['breakeven'] or 0)
            d['total_pnl'] = round(float(d['total_pnl'] or 0), 2)
            d['winrate'] = round(wins / total * 100, 1) if total else 0
            out.append(d)
        return {"days": days, "since": since, "rows": out}


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
def create_user(email, password_hash, salt, tier='free', trial_ends_at=None,
                email_verified=0, google_id=None):
    with _lock, get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO users (email, password_hash, salt, tier, created_at, trial_ends_at,
                               email_verified, google_id)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            email.lower().strip(), password_hash, salt, tier,
            datetime.now().isoformat(), trial_ends_at,
            int(email_verified), google_id,
        ))
        return cur.lastrowid


def get_user_by_email(email):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None


def get_user_by_google_id(google_id: str):
    if not google_id:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE google_id=?", (google_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def set_user_tier(user_id, tier):
    with _lock, get_conn() as conn:
        conn.execute("UPDATE users SET tier=? WHERE id=?", (tier, user_id))


def set_user_telegram_id(user_id, telegram_id: int):
    with _lock, get_conn() as conn:
        conn.execute("UPDATE users SET telegram_id=? WHERE id=?", (int(telegram_id), user_id))


def get_user_by_telegram_id(telegram_id: int):
    if not telegram_id:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (int(telegram_id),)).fetchone()
        return dict(row) if row else None


def grant_premium(user_id, days: int = 30):
    """Ставит tier=premium и premium_until (+days от сейчас)."""
    from datetime import timedelta
    until = (datetime.now() + timedelta(days=max(1, int(days)))).isoformat()
    with _lock, get_conn() as conn:
        conn.execute(
            "UPDATE users SET tier='premium', premium_until=? WHERE id=?",
            (until, user_id),
        )
    return until


def add_premium_request(telegram_id: int, email: str):
    with _lock, get_conn() as conn:
        conn.execute(
            "UPDATE premium_requests SET status='cancelled' WHERE telegram_id=? AND status='pending'",
            (int(telegram_id),),
        )
        cur = conn.execute(
            """INSERT INTO premium_requests (telegram_id, email, created_at, status)
               VALUES (?,?,?, 'pending')""",
            (int(telegram_id), email.lower().strip(), datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_pending_premium_request(email: str = None, telegram_id: int = None):
    with get_conn() as conn:
        if email:
            row = conn.execute(
                "SELECT * FROM premium_requests WHERE email=? AND status='pending' ORDER BY id DESC LIMIT 1",
                (email.lower().strip(),),
            ).fetchone()
        elif telegram_id:
            row = conn.execute(
                "SELECT * FROM premium_requests WHERE telegram_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
                (int(telegram_id),),
            ).fetchone()
        else:
            return None
        return dict(row) if row else None


def resolve_premium_request(req_id: int, status: str = "granted"):
    with _lock, get_conn() as conn:
        conn.execute("UPDATE premium_requests SET status=? WHERE id=?", (status, req_id))


def set_user_admin(user_id, is_admin: bool):
    with _lock, get_conn() as conn:
        conn.execute("UPDATE users SET is_admin=? WHERE id=?", (int(is_admin), user_id))


def set_email_verified(user_id, verified: bool = True):
    with _lock, get_conn() as conn:
        conn.execute("UPDATE users SET email_verified=? WHERE id=?", (int(verified), user_id))


def set_user_google_id(user_id, google_id: str):
    with _lock, get_conn() as conn:
        conn.execute("UPDATE users SET google_id=? WHERE id=?", (google_id, user_id))


def set_user_password(user_id, password_hash, salt):
    with _lock, get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, salt=? WHERE id=?",
            (password_hash, salt, user_id),
        )


def create_auth_token(token: str, user_id: int, kind: str, expires_at: str):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE user_id=? AND kind=?", (user_id, kind))
        conn.execute("""
            INSERT INTO auth_tokens (token, user_id, kind, created_at, expires_at)
            VALUES (?,?,?,?,?)
        """, (token, user_id, kind, datetime.now().isoformat(), expires_at))


def consume_auth_token(token: str, kind: str):
    """Возвращает user_id если токен валиден и не истёк, иначе None.

    Валидный токен удаляется (одноразовый). Просроченный/битый — тоже удаляется
    как мусор, но user_id не возвращается.
    """
    if not token:
        return None
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM auth_tokens WHERE token=? AND kind=?",
            (token, kind),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            expired = datetime.now() > datetime.fromisoformat(data["expires_at"])
        except (ValueError, TypeError):
            expired = True
        conn.execute("DELETE FROM auth_tokens WHERE token=?", (token,))
        return None if expired else data["user_id"]


def purge_expired_auth() -> int:
    """Удаляет истёкшие сессии и одноразовые токены. Возвращает число строк."""
    now = datetime.now().isoformat()
    with _lock, get_conn() as conn:
        c1 = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,)).rowcount
        c2 = conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (now,)).rowcount
    return (c1 or 0) + (c2 or 0)


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
        hist_rows = conn.execute("""
            SELECT trader_id,
                   COUNT(*) AS closed,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                   COALESCE(SUM(pnl), 0) AS total_pnl
            FROM history
            WHERE trader_id IS NOT NULL
            GROUP BY trader_id
        """).fetchall()
        hist_by_id = {r['trader_id']: r for r in hist_rows}
        open_rows = conn.execute("""
            SELECT trader_id, COUNT(*) AS c
            FROM open_trades
            WHERE trader_id IS NOT NULL
            GROUP BY trader_id
        """).fetchall()
        open_by_id = {r['trader_id']: r['c'] for r in open_rows}
        out = []
        for t in traders:
            t = dict(t)
            h = hist_by_id.get(t['id'])
            closed = int(h['closed']) if h else 0
            wins = int(h['wins'] or 0) if h else 0
            total_pnl = float(h['total_pnl'] or 0) if h else 0.0
            t['closed_trades'] = closed
            t['open_positions'] = int(open_by_id.get(t['id'], 0))
            t['winrate'] = round(wins / closed * 100, 1) if closed else None
            t['total_pnl'] = round(total_pnl, 2)
            out.append(t)
        return out


def get_traders_by_ids(ids):
    """Лёгкий lookup без агрегатов — для /api/signals."""
    ids = [i for i in ids if i is not None]
    if not ids:
        return {}
    with get_conn() as conn:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT id, name, avatar_url, source_type FROM traders WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        return {r['id']: dict(r) for r in rows}


def _stats_bucket(conn, where_sql="", params=()):
    """Одна корзина метрик как у _summarize в main.py."""
    row = conn.execute(f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN result = 'sl' THEN 1 ELSE 0 END) AS stops,
            SUM(CASE WHEN result IN ('be', 'potential') THEN 1 ELSE 0 END) AS breakeven,
            SUM(CASE WHEN result = 'tp1' THEN 1 ELSE 0 END) AS tp1,
            COALESCE(SUM(pnl), 0) AS total_pnl
        FROM history
        {where_sql}
    """, params).fetchone()
    total = int(row['total'] or 0)
    if not total:
        return {
            "total": 0, "winrate": 0, "tp1": 0, "tp2_plus": 0,
            "stops": 0, "breakeven": 0, "total_pnl": 0, "avg_pnl": 0,
            "best": None, "worst": None,
        }
    wins = int(row['wins'] or 0)
    tp1s = int(row['tp1'] or 0)
    total_pnl = float(row['total_pnl'] or 0)
    best = conn.execute(
        f"SELECT symbol, pnl FROM history {where_sql} ORDER BY pnl DESC LIMIT 1", params
    ).fetchone()
    worst = conn.execute(
        f"SELECT symbol, pnl FROM history {where_sql} ORDER BY pnl ASC LIMIT 1", params
    ).fetchone()
    return {
        "total": total,
        "winrate": round(wins / total * 100, 1),
        "tp1": tp1s,
        "tp2_plus": wins - tp1s,
        "stops": int(row['stops'] or 0),
        "breakeven": int(row['breakeven'] or 0),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2),
        "best": {"symbol": best['symbol'], "pnl": best['pnl']} if best else None,
        "worst": {"symbol": worst['symbol'], "pnl": worst['pnl']} if worst else None,
    }


def get_stats_summaries():
    """today / week / all_time без загрузки тысяч строк в Python."""
    from datetime import timedelta
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    with get_conn() as conn:
        return {
            "today": _stats_bucket(conn, "WHERE date=?", (today_str,)),
            "week": _stats_bucket(conn, "WHERE date>=?", (week_ago,)),
            "all_time": _stats_bucket(conn),
        }


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


# ── Исторические сигналы каналов (channel_backtest.py) ────
def save_historical_signal(channel, message_id, symbol, side, entry, stop, tp1, posted_at, tp2=None, tp3=None):
    """INSERT OR IGNORE — при повторном запуске ingest по тому же каналу
    не дублирует уже сохранённые посты (UNIQUE(channel, message_id)).
    tp2/tp3 — только если канал сам их назвал в посте, иначе NULL (не достраиваем)."""
    with _lock, get_conn() as conn:
        cur = conn.execute("""
            INSERT OR IGNORE INTO historical_signals
                (channel, message_id, symbol, side, entry, stop, tp1, tp2, tp3, posted_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (channel, message_id, symbol, side, entry, stop, tp1, tp2, tp3, posted_at))
        return cur.lastrowid if cur.rowcount else None


def load_historical_signals(channel, unchecked_only=False):
    with get_conn() as conn:
        q = "SELECT * FROM historical_signals WHERE channel=?"
        if unchecked_only:
            q += " AND checked_at IS NULL"
        rows = conn.execute(q + " ORDER BY posted_at", (channel,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            # SQLite хранит tp2_hit/tp3_hit как 0/1/NULL — приводим к настоящему
            # bool/None, иначе на фронте `s.tp2_hit === true` не совпадёт с числом 1.
            d['tp2_hit'] = None if d['tp2_hit'] is None else bool(d['tp2_hit'])
            d['tp3_hit'] = None if d['tp3_hit'] is None else bool(d['tp3_hit'])
            out.append(d)
        return out


def save_backtest_result(signal_id, entry_filled, entry_filled_at, outcome, exit_price, pnl_pct,
                          tp2_hit=None, tp3_hit=None, pnl_usd=None, position_size=None):
    with _lock, get_conn() as conn:
        conn.execute("""
            UPDATE historical_signals SET
                entry_filled=?, entry_filled_at=?, outcome=?, exit_price=?, pnl_pct=?, checked_at=?,
                tp2_hit=?, tp3_hit=?, pnl_usd=?, position_size=?
            WHERE id=?
        """, (int(entry_filled), entry_filled_at, outcome, exit_price, pnl_pct,
              datetime.now().isoformat(),
              None if tp2_hit is None else int(tp2_hit),
              None if tp3_hit is None else int(tp3_hit),
              pnl_usd, position_size,
              signal_id))


# ── Кэш отчёта по каналу (Channel Analyzer) ────────────────
def save_channel_stats(channel, period_days, report: dict, equity_curve_json: str,
                        entry_timeout_hours=None, max_hold_hours=None, risk_per_trade_usd=None):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO channel_stats
                (channel, period_days, total_signals, checked, closed_trades, wins, losses,
                 winrate_pct, avg_risk_reward, total_pnl_pct, total_pnl_usd, equity_curve_json,
                 last_analyzed_at, tp2_hit_rate, tp2_sample, tp3_hit_rate, tp3_sample,
                 entry_timeout_hours, max_hold_hours, risk_per_trade_usd)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(channel) DO UPDATE SET
                period_days=excluded.period_days,
                total_signals=excluded.total_signals,
                checked=excluded.checked,
                closed_trades=excluded.closed_trades,
                wins=excluded.wins,
                losses=excluded.losses,
                winrate_pct=excluded.winrate_pct,
                avg_risk_reward=excluded.avg_risk_reward,
                total_pnl_pct=excluded.total_pnl_pct,
                total_pnl_usd=excluded.total_pnl_usd,
                equity_curve_json=excluded.equity_curve_json,
                last_analyzed_at=excluded.last_analyzed_at,
                tp2_hit_rate=excluded.tp2_hit_rate,
                tp2_sample=excluded.tp2_sample,
                tp3_hit_rate=excluded.tp3_hit_rate,
                tp3_sample=excluded.tp3_sample,
                entry_timeout_hours=excluded.entry_timeout_hours,
                max_hold_hours=excluded.max_hold_hours,
                risk_per_trade_usd=excluded.risk_per_trade_usd
        """, (channel, period_days, report['total_signals'], report['checked'],
              report['closed_trades'], report['wins'], report['losses'],
              report['winrate_pct'], report['avg_risk_reward'], report['total_pnl_pct_of_risk'],
              report['total_pnl_usd'],
              equity_curve_json, datetime.now().isoformat(),
              report.get('tp2_hit_rate'), report.get('tp2_sample'),
              report.get('tp3_hit_rate'), report.get('tp3_sample'),
              entry_timeout_hours, max_hold_hours, risk_per_trade_usd))


def get_channel_stats(channel):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM channel_stats WHERE channel=?", (channel,)).fetchone()
        return dict(row) if row else None


def list_channel_stats():
    """Все проанализированные каналы — для рейтинга/сравнения на фронте."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM channel_stats ORDER BY total_pnl_pct DESC NULLS LAST"
        ).fetchall()
        return [dict(r) for r in rows]