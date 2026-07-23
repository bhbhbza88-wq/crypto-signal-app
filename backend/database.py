"""
Database — SQLite хранилище для открытых сделок и истории.
Заменяет open_trades.json / trades_history.json из бота.
"""

import os
import sqlite3
import json
import threading
from datetime import datetime, timedelta
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
            ("exit_mode", "TEXT DEFAULT 'ladder'"),
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
        if 'welcome_email_sent' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN welcome_email_sent INTEGER DEFAULT 0")
            print("✅ Миграция: добавлена колонка welcome_email_sent в users")
        if 'pricing_nudge_sent' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN pricing_nudge_sent INTEGER DEFAULT 0")
            print("✅ Миграция: добавлена колонка pricing_nudge_sent в users")
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
            CREATE TABLE IF NOT EXISTS heleket_orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                heleket_uuid TEXT,
                period TEXT NOT NULL DEFAULT 'month',
                amount TEXT,
                currency TEXT,
                pay_url TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                paid_at TEXT
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
        # Антидетект: счётчики исходящих reply/profit по чатам
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_engage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_engage_events_lookup "
            "ON chat_engage_events(chat_key, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_engage_events_global "
            "ON chat_engage_events(kind, created_at)"
        )
        # Память диалога + OARS-шаг на peer (chat:user)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_dialog_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_key TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_dialog_peer "
            "ON chat_dialog_memory(peer_key, id)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_oars_state (
                peer_key TEXT PRIMARY KEY,
                step INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)
        # Общий key-value склад для мелких флагов/маркеров (напр. до какого id
        # истории уже сделан бэкфилл в публичный канал) — чтобы не городить
        # отдельную таблицу под каждую мелочь.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chart_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                display_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                pnl_pct REAL NOT NULL,
                comment TEXT NOT NULL,
                is_seed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chart_help_votes (
                user_id INTEGER PRIMARY KEY,
                helped INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chart_vote_pending (
                user_id INTEGER PRIMARY KEY,
                pending INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)
        # Ingest quality: уже обработанные TG-сообщения (не гоняем AI повторно)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                channel TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                processed_at TEXT NOT NULL,
                PRIMARY KEY (channel, message_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_processed_msg_at ON processed_messages(processed_at)"
        )
        # Дневные лимиты сигналов с канала (живут между рестартами)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_day_counts (
                channel_alias TEXT NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (channel_alias, day)
            )
        """)
        # Health ingest: последняя активность по каналу
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingest_channel_health (
                channel TEXT PRIMARY KEY,
                alias TEXT,
                last_message_at TEXT,
                last_signal_at TEXT,
                last_error TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        # Retry queue: временные сбои AI/биржи
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingest_retry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                channel_alias TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                text TEXT,
                reason TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(channel, message_id)
            )
        """)
        # Чистим протухшие сессии/токены при старте, чтобы БД не пухла.
        now = datetime.now().isoformat()
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (now,))

    _seed_chart_reviews_if_needed()
    _ensure_chart_vote_baseline()


_CHART_REVIEW_SEEDS = [
    ("Артём К.", "BTC", "LONG", 4.2, "Разбор по скрину 15m — вход после ретеста, закрыл на TP2."),
    ("Mila", "ETH", "LONG", 3.1, "AI правильно сказал ждать пробой. Зашла и +3% за день."),
    ("Denis", "SOL", "SHORT", 5.4, "Шорт после слабости на H1 — отработал чисто."),
    ("Игорь", "BNB", "LONG", 2.6, "Думал флэт, а разбор показал лонг от уровня. Спасибо."),
    ("Kate", "XRP", "LONG", 3.8, "Скрин с телефона — разобрали за минуту, вход совпал."),
    ("Павел", "DOGE", "SHORT", 4.0, "Не лез в лонг, как советовали — и правильно, шорт дал плюс."),
    ("Sergey", "AVAX", "LONG", 2.9, "Хороший take: ждал ретест, не купил на хаях."),
    ("Настя", "LINK", "LONG", 6.1, "Разбор спас от FOMO. Вошла позже и вышла в плюс."),
    ("Alex", "OP", "LONG", 3.4, "Структура на 5m читалась слабо, AI сказал мимо — не потерял."),
    ("Виктор", "ARB", "SHORT", 2.8, "Короткий шорт после отказа от хая — +2.8%."),
    ("Lena", "SUI", "LONG", 5.2, "Скрин TradingView, разбор попал в точку."),
    ("Roman", "NEAR", "LONG", 3.0, "Ждал подтверждения — как и советовали. Итог зелёный."),
    ("Тимур", "APT", "SHORT", 4.7, "Шорт от сопротивления, SL маленький, RR хороший."),
    ("Olya", "INJ", "LONG", 2.4, "Первый раз пользовалась разбором — уже в плюсе."),
    ("Max", "TIA", "LONG", 7.2, "Сильный импульс после разбора, держал до TP."),
    ("Даша", "PEPE", "LONG", 8.5, "Мемка, но уровни на скрине были чистые — сработало."),
    ("Andrey", "WIF", "SHORT", 3.6, "Не ловил нож — разбор сказал шорт после отката."),
    ("Кирилл", "DOT", "LONG", 2.2, "Спокойный лонг, без жадности. Плюс есть."),
    ("Sofia", "ATOM", "LONG", 3.3, "AI увидел дивергенцию, которую я пропустил."),
    ("Женя", "FIL", "SHORT", 4.1, "Разбор отговорил от лонга на хае — шорт зашёл."),
    ("Nick", "AAVE", "LONG", 2.7, "Классика: ретест + объём. Разбор подтвердил."),
    ("Марина", "UNI", "LONG", 3.9, "Скрин с Bybit, всё прочитали сами — удобно."),
    ("Boris", "LTC", "SHORT", 2.5, "Короткий сетап, быстрый плюс."),
    ("Юля", "ADA", "LONG", 2.1, "Не большой профит, но уверенный вход."),
    ("Leo", "TON", "LONG", 5.8, "Разбор на 1H — тренд держался, вышел на TP1+."),
    ("Саша", "TRX", "LONG", 1.9, "Скальп по совету, закрыл в плюс."),
    ("Eva", "MATIC", "SHORT", 3.5, "Слабость тренда на скрине — шорт оправдан."),
    ("Глеб", "SEI", "LONG", 4.4, "Ждал pullback, как в разборе. Красиво отработало."),
    ("Tina", "RUNE", "LONG", 6.0, "Риск написали честно, но сетап был сильный."),
    ("Олег", "STX", "SHORT", 2.3, "Не пересидел — вышел по плану из разбора."),
    ("Vera", "ORDI", "LONG", 5.1, "Скрин был шумный, AI сказал «пока мимо» — спас депозит."),
    ("Илья", "FET", "LONG", 4.8, "AI-сектор, лонг после консолидации — плюс."),
    ("Dima", "OP", "LONG", -1.2, "Разбор звал в лонг, рынок развернул — минус небольшой."),
    ("Катя", "SOL", "SHORT", -0.8, "Не помогло: шорт не зашёл, вышла по стопу."),
    ("Mark", "ETH", "LONG", -2.1, "Ждал подтверждения слишком долго — уже не то."),
    ("Никита", "BTC", "SHORT", -1.5, "Разбор мимо, лучше бы не лез."),
    ("Alina", "ARB", "LONG", -0.6, "Плюса не вышло, но хотя бы стоп маленький."),
    ("Pete", "SUI", "LONG", -1.8, "Не совпало с моим планом — в минус."),
    ("Юра", "NEAR", "SHORT", -1.1, "Сигнал слабый оказался, закрыл в небольшой минус."),
    ("Helen", "LINK", "LONG", -0.9, "Не помогло в этот раз."),
]


def _ensure_chart_vote_baseline() -> None:
    """База голосов: ~72% помощи (627 yes / 244 no)."""
    if get_setting("chart_vote_yes") is not None:
        return
    set_setting("chart_vote_yes", "627")
    set_setting("chart_vote_no", "244")
    if get_setting("chart_helped_total") is None:
        set_setting("chart_helped_total", "627")


def _seed_chart_reviews_if_needed() -> None:
    """Один раз наполняем витрину разборов."""
    if get_setting("chart_reviews_seeded") == "1":
        return
    with _lock, get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM chart_reviews").fetchone()["c"]
        if n == 0:
            import random
            now = datetime.now()
            for i, (name, sym, side, pnl, text) in enumerate(_CHART_REVIEW_SEEDS):
                days_ago = random.randint(0, 90)
                hours = random.randint(0, 23)
                ts = (now - timedelta(days=days_ago, hours=hours)).isoformat(timespec="seconds")
                conn.execute(
                    "INSERT INTO chart_reviews "
                    "(user_id, display_name, symbol, side, pnl_pct, comment, is_seed, created_at) "
                    "VALUES (NULL,?,?,?,?,?,1,?)",
                    (name, sym, side, float(pnl), text, ts),
                )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('chart_reviews_seeded', '1') "
            "ON CONFLICT(key) DO UPDATE SET value='1'"
        )


def list_chart_reviews(limit: int = 40) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, display_name, symbol, side, pnl_pct, comment, is_seed, created_at "
            "FROM chart_reviews ORDER BY datetime(created_at) DESC LIMIT ?",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [dict(r) for r in rows]


def chart_review_stats(user_id: int | None = None) -> dict:
    _ensure_chart_vote_baseline()
    yes = int(get_setting("chart_vote_yes", "627") or 627)
    no = int(get_setting("chart_vote_no", "244") or 244)
    total = yes + no
    winrate = round(100.0 * yes / total, 1) if total else 0.0
    my_vote = None
    can_vote = False
    if user_id is not None:
        with get_conn() as conn:
            pend = conn.execute(
                "SELECT pending FROM chart_vote_pending WHERE user_id=?",
                (user_id,),
            ).fetchone()
            can_vote = bool(pend and int(pend["pending"]) == 1)
            row = conn.execute(
                "SELECT helped FROM chart_help_votes WHERE user_id=?",
                (user_id,),
            ).fetchone()
            if row is not None and not can_vote:
                my_vote = bool(row["helped"])
    return {
        "helped": yes,
        "not_helped": no,
        "votes_total": total,
        "winrate": winrate,
        "my_vote": my_vote,
        "can_vote": can_vote,
    }


def grant_chart_vote_pending(user_id: int) -> None:
    """После успешного разбора скрина — один голос +/- доступен."""
    now = datetime.now().isoformat(timespec="seconds")
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO chart_vote_pending (user_id, pending, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET pending=1, updated_at=excluded.updated_at",
            (user_id, 1, now),
        )


def cast_chart_help_vote(user_id: int, helped: bool) -> dict:
    """Один плюс/минус только если только что был разбор. Повторный клик без нового разбора — нельзя."""
    _ensure_chart_vote_baseline()
    now = datetime.now().isoformat(timespec="seconds")
    want = 1 if helped else 0
    with _lock, get_conn() as conn:
        pend = conn.execute(
            "SELECT pending FROM chart_vote_pending WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not pend or int(pend["pending"]) != 1:
            raise ValueError("need_analysis")

        yes = int(
            (conn.execute("SELECT value FROM settings WHERE key='chart_vote_yes'").fetchone() or {"value": "627"})["value"]
        )
        no = int(
            (conn.execute("SELECT value FROM settings WHERE key='chart_vote_no'").fetchone() or {"value": "244"})["value"]
        )
        if want:
            yes += 1
        else:
            no += 1

        conn.execute(
            "INSERT INTO chart_help_votes (user_id, helped, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET helped=excluded.helped, updated_at=excluded.updated_at",
            (user_id, want, now),
        )
        conn.execute(
            "UPDATE chart_vote_pending SET pending=0, updated_at=? WHERE user_id=?",
            (now, user_id),
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('chart_vote_yes', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(yes),),
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('chart_vote_no', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(no),),
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('chart_helped_total', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(yes),),
        )
    return chart_review_stats(user_id=user_id)


def get_setting(key: str, default: str | None = None) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


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


def count_chat_style_samples(chat_ref: str | None = None) -> int:
    with get_conn() as conn:
        if chat_ref:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM chat_style_samples WHERE chat_ref=?",
                (chat_ref.lstrip("@"),),
            ).fetchone()
        else:
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


def record_chat_engage_event(chat_key: str, kind: str = "reply") -> None:
    from datetime import datetime
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_engage_events (chat_key, kind, created_at) VALUES (?,?,?)",
            (chat_key, kind, datetime.now().isoformat()),
        )
        n = conn.execute("SELECT COUNT(*) AS n FROM chat_engage_events").fetchone()["n"]
        if n > 5000:
            conn.execute(
                """
                DELETE FROM chat_engage_events WHERE id IN (
                    SELECT id FROM chat_engage_events ORDER BY id ASC LIMIT ?
                )
                """,
                (n - 5000,),
            )


def count_chat_engage_events(
    *,
    chat_key: str | None = None,
    kind: str | None = "reply",
    since_iso: str,
) -> int:
    with get_conn() as conn:
        if chat_key and kind:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM chat_engage_events "
                "WHERE chat_key=? AND kind=? AND created_at>=?",
                (chat_key, kind, since_iso),
            ).fetchone()
        elif chat_key:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM chat_engage_events "
                "WHERE chat_key=? AND created_at>=?",
                (chat_key, since_iso),
            ).fetchone()
        elif kind:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM chat_engage_events "
                "WHERE kind=? AND created_at>=?",
                (kind, since_iso),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM chat_engage_events WHERE created_at>=?",
                (since_iso,),
            ).fetchone()
        return int(row["n"] if row else 0)


def add_dialog_memory(peer_key: str, role: str, text: str, keep: int = 12) -> None:
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_dialog_memory (peer_key, role, text, created_at) VALUES (?,?,?,?)",
            (peer_key, role, text[:400], datetime.now().isoformat()),
        )
        rows = conn.execute(
            "SELECT id FROM chat_dialog_memory WHERE peer_key=? ORDER BY id DESC",
            (peer_key,),
        ).fetchall()
        if len(rows) > keep:
            drop_ids = [r["id"] for r in rows[keep:]]
            conn.executemany(
                "DELETE FROM chat_dialog_memory WHERE id=?",
                [(i,) for i in drop_ids],
            )


def list_dialog_memory(peer_key: str, limit: int = 8) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, text FROM chat_dialog_memory WHERE peer_key=? "
            "ORDER BY id DESC LIMIT ?",
            (peer_key, limit),
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


def get_oars_step(peer_key: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT step FROM chat_oars_state WHERE peer_key=?", (peer_key,)
        ).fetchone()
        return int(row["step"]) if row else 0


def set_oars_step(peer_key: str, step: int) -> None:
    with _lock, get_conn() as conn:
        conn.execute(
            """
            INSERT INTO chat_oars_state (peer_key, step, updated_at) VALUES (?,?,?)
            ON CONFLICT(peer_key) DO UPDATE SET step=excluded.step, updated_at=excluded.updated_at
            """,
            (peer_key, int(step), datetime.now().isoformat()),
        )


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
                 exchange, listed_on, exit_mode)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            trade.get('exit_mode') or 'ladder',
        ))
        return cur.rowcount


def upsert_trade(symbol, trade: dict):
    with _lock, get_conn() as conn:
        conn.execute("""
            INSERT INTO open_trades
                (symbol, signal, entry, stop, tp1, tp2, tp3, score, regime,
                 tp1_hit, tp2_hit, be_hit, potential_warned, pre_tp1_trail,
                 opened_at, candles_json, entry_reasons_json, position_size, trader_id,
                 exchange, listed_on, exit_mode)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                listed_on=excluded.listed_on,
                exit_mode=excluded.exit_mode
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
            trade.get('exit_mode') or 'ladder',
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


def load_history(limit=200, days: int | None = None):
    """Последние сделки. Если days задан — только за последние N календарных дней."""
    limit = max(1, min(int(limit or 200), 5000))
    with get_conn() as conn:
        if days is not None:
            from datetime import timedelta
            days = max(1, min(int(days), 365))
            since = (datetime.now() - timedelta(days=days - 1)).strftime('%Y-%m-%d')
            rows = conn.execute(
                "SELECT * FROM history WHERE date >= ? ORDER BY id DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        else:
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


def list_users(limit: int = 50, offset: int = 0, q: str | None = None, tier_filter: str | None = None):
    """CRM-lite: пользователи с pending premium и последним статусом Heleket."""
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    q = (q or "").strip().lower()
    tier_filter = (tier_filter or "").strip().lower() or None
    now_iso = datetime.now().isoformat()

    where = ["1=1"]
    params: list = []
    if q:
        where.append("u.email LIKE ?")
        params.append(f"%{q}%")

    # free / premium / unverified — по «эффективному» тарифу и верификации
    if tier_filter == "unverified":
        where.append("COALESCE(u.email_verified, 0) = 0")
    elif tier_filter == "premium":
        where.append(
            """(
                u.tier IN ('premium', 'vip')
                AND (u.premium_until IS NULL OR u.premium_until > ?)
            )"""
        )
        params.append(now_iso)
    elif tier_filter == "free":
        where.append(
            """(
                COALESCE(u.email_verified, 0) = 1
                AND NOT (
                    u.tier IN ('premium', 'vip')
                    AND (u.premium_until IS NULL OR u.premium_until > ?)
                )
            )"""
        )
        params.append(now_iso)

    sql = f"""
        SELECT
            u.id, u.email, u.created_at, u.email_verified, u.tier, u.premium_until,
            u.telegram_id,
            (
                SELECT pr.status FROM premium_requests pr
                WHERE pr.email = u.email AND pr.status = 'pending'
                ORDER BY pr.id DESC LIMIT 1
            ) AS pending_premium_status,
            (
                SELECT h.status FROM heleket_orders h
                WHERE h.user_id = u.id
                ORDER BY h.created_at DESC LIMIT 1
            ) AS last_heleket_status
        FROM users u
        WHERE {' AND '.join(where)}
        ORDER BY u.id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            pending = d.pop("pending_premium_status", None)
            d["email_verified"] = bool(d.get("email_verified"))
            d["pending_premium_request"] = pending or False
            d["telegram_linked"] = bool(d.get("telegram_id"))
            out.append(d)
        return out


def mark_welcome_email_sent(user_id: int) -> None:
    with _lock, get_conn() as conn:
        conn.execute(
            "UPDATE users SET welcome_email_sent=1 WHERE id=?",
            (int(user_id),),
        )


def mark_pricing_nudge_sent(user_id: int) -> None:
    with _lock, get_conn() as conn:
        conn.execute(
            "UPDATE users SET pricing_nudge_sent=1 WHERE id=?",
            (int(user_id),),
        )


def list_users_for_pricing_nudge(limit: int = 40) -> list[dict]:
    """Free, verified, созданы ≥24ч назад, nudge ещё не уходил, не premium."""
    limit = max(1, min(int(limit or 40), 100))
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    now_iso = datetime.now().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, email FROM users
            WHERE COALESCE(email_verified, 0) = 1
              AND COALESCE(pricing_nudge_sent, 0) = 0
              AND created_at IS NOT NULL
              AND created_at <= ?
              AND NOT (
                  tier IN ('premium', 'vip')
                  AND (premium_until IS NULL OR premium_until > ?)
              )
            ORDER BY id ASC
            LIMIT ?
            """,
            (cutoff, now_iso, limit),
        ).fetchall()
        return [dict(r) for r in rows]


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


def create_heleket_order(
    *,
    order_id: str,
    user_id: int,
    heleket_uuid: str | None,
    period: str,
    amount: str,
    currency: str,
    pay_url: str | None,
) -> None:
    with _lock, get_conn() as conn:
        conn.execute(
            """INSERT INTO heleket_orders
               (order_id, user_id, heleket_uuid, period, amount, currency, pay_url, status, created_at)
               VALUES (?,?,?,?,?,?,?, 'pending', ?)""",
            (
                order_id,
                int(user_id),
                heleket_uuid,
                period,
                amount,
                currency,
                pay_url,
                datetime.now().isoformat(),
            ),
        )


def get_heleket_order(order_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM heleket_orders WHERE order_id=?",
            (order_id,),
        ).fetchone()
        return dict(row) if row else None


def list_heleket_orders_for_user(user_id: int, *, limit: int = 20):
    limit = max(1, min(int(limit or 20), 50))
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM heleket_orders
               WHERE user_id=?
               ORDER BY created_at DESC
               LIMIT ?""",
            (int(user_id), limit),
        ).fetchall()
        return [dict(r) for r in rows]


def list_pending_heleket_orders(*, limit: int = 50):
    """Orders not yet granted (pending / paid_no_user / check / etc.)."""
    limit = max(1, min(int(limit or 50), 200))
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM heleket_orders
               WHERE COALESCE(status, '') NOT IN ('granted', 'cancel', 'cancel_timeout', 'fail', 'wrong_amount', 'system_fail')
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_heleket_order(order_id: str, status: str, heleket_uuid: str | None = None) -> None:
    paid_statuses = {"paid", "paid_over", "granted", "paid_no_user"}
    with _lock, get_conn() as conn:
        if status in paid_statuses:
            conn.execute(
                """UPDATE heleket_orders
                   SET status=?, paid_at=?, heleket_uuid=COALESCE(?, heleket_uuid)
                   WHERE order_id=?""",
                (status, datetime.now().isoformat(), heleket_uuid, order_id),
            )
        else:
            conn.execute(
                """UPDATE heleket_orders
                   SET status=?, heleket_uuid=COALESCE(?, heleket_uuid)
                   WHERE order_id=?""",
                (status, heleket_uuid, order_id),
            )


# ── Ingest quality helpers ────────────────────────────────────────────

def is_message_processed(channel: str, message_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_messages WHERE channel=? AND message_id=?",
            (channel, int(message_id)),
        ).fetchone()
        return bool(row)


def mark_message_processed(channel: str, message_id: int) -> None:
    with _lock, get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO processed_messages (channel, message_id, processed_at)
               VALUES (?,?,?)""",
            (channel, int(message_id), datetime.now().isoformat()),
        )


def prune_processed_messages(keep_days: int = 14) -> int:
    cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
    with _lock, get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM processed_messages WHERE processed_at < ?", (cutoff,)
        )
        return cur.rowcount


def channel_day_count(channel_alias: str) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count FROM channel_day_counts WHERE channel_alias=? AND day=?",
            (channel_alias, today),
        ).fetchone()
        return int(row["count"]) if row else 0


def channel_day_bump(channel_alias: str) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    with _lock, get_conn() as conn:
        conn.execute(
            """INSERT INTO channel_day_counts (channel_alias, day, count)
               VALUES (?,?,1)
               ON CONFLICT(channel_alias, day) DO UPDATE SET count = count + 1""",
            (channel_alias, today),
        )
        row = conn.execute(
            "SELECT count FROM channel_day_counts WHERE channel_alias=? AND day=?",
            (channel_alias, today),
        ).fetchone()
        return int(row["count"]) if row else 1


def touch_ingest_health(
    channel: str,
    *,
    alias: str | None = None,
    message: bool = False,
    signal: bool = False,
    error: str | None = None,
) -> None:
    now = datetime.now().isoformat()
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM ingest_channel_health WHERE channel=?", (channel,)
        ).fetchone()
        if not row:
            conn.execute(
                """INSERT INTO ingest_channel_health
                   (channel, alias, last_message_at, last_signal_at, last_error, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    channel,
                    alias,
                    now if message else None,
                    now if signal else None,
                    error,
                    now,
                ),
            )
            return
        conn.execute(
            """UPDATE ingest_channel_health SET
                 alias=COALESCE(?, alias),
                 last_message_at=CASE WHEN ? THEN ? ELSE last_message_at END,
                 last_signal_at=CASE WHEN ? THEN ? ELSE last_signal_at END,
                 last_error=COALESCE(?, last_error),
                 updated_at=?
               WHERE channel=?""",
            (
                alias,
                1 if message else 0, now,
                1 if signal else 0, now,
                error,
                now,
                channel,
            ),
        )


def list_ingest_health() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ingest_channel_health ORDER BY channel"
        ).fetchall()
        return [dict(r) for r in rows]


def enqueue_ingest_retry(
    *,
    channel: str,
    channel_alias: str,
    message_id: int,
    text: str | None,
    reason: str,
    delay_sec: int = 45,
) -> None:
    next_at = (datetime.now() + timedelta(seconds=delay_sec)).isoformat()
    now = datetime.now().isoformat()
    with _lock, get_conn() as conn:
        conn.execute(
            """INSERT INTO ingest_retry_queue
               (channel, channel_alias, message_id, text, reason, attempts, next_attempt_at, created_at)
               VALUES (?,?,?,?,?,0,?,?)
               ON CONFLICT(channel, message_id) DO UPDATE SET
                 reason=excluded.reason,
                 next_attempt_at=excluded.next_attempt_at,
                 text=COALESCE(excluded.text, ingest_retry_queue.text)""",
            (channel, channel_alias, int(message_id), text, reason, next_at, now),
        )


def pop_due_ingest_retries(limit: int = 20) -> list[dict]:
    now = datetime.now().isoformat()
    with _lock, get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM ingest_retry_queue
               WHERE next_attempt_at <= ? AND attempts < 3
               ORDER BY next_attempt_at ASC LIMIT ?""",
            (now, limit),
        ).fetchall()
        out = [dict(r) for r in rows]
        for r in out:
            conn.execute(
                """UPDATE ingest_retry_queue
                   SET attempts = attempts + 1,
                       next_attempt_at = ?
                   WHERE id=?""",
                (
                    (datetime.now() + timedelta(seconds=60 * (r["attempts"] + 1))).isoformat(),
                    r["id"],
                ),
            )
        return out


def clear_ingest_retry(channel: str, message_id: int) -> None:
    with _lock, get_conn() as conn:
        conn.execute(
            "DELETE FROM ingest_retry_queue WHERE channel=? AND message_id=?",
            (channel, int(message_id)),
        )


def purge_failed_ingest_retries() -> int:
    """Удаляет ретраи после 3 неудачных попыток."""
    with _lock, get_conn() as conn:
        cur = conn.execute("DELETE FROM ingest_retry_queue WHERE attempts >= 3")
        return cur.rowcount


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
    """today / week / month / all_time без загрузки тысяч строк в Python."""
    from datetime import timedelta
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    week_ago = (now - timedelta(days=6)).strftime('%Y-%m-%d')
    month_ago = (now - timedelta(days=29)).strftime('%Y-%m-%d')
    with get_conn() as conn:
        return {
            "today": _stats_bucket(conn, "WHERE date=?", (today_str,)),
            "week": _stats_bucket(conn, "WHERE date>=?", (week_ago,)),
            "month": _stats_bucket(conn, "WHERE date>=?", (month_ago,)),
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