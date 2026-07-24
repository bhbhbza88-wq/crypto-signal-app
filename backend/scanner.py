"""
Фоновый цикл: трекинг открытых позиций + paper-стратегии xsec/trend.
Автопоиск сигналов (NFI/V8) удалён — торговые сигналы только из каналов / ручной ввод / webhook.
"""

import time
import threading
from datetime import datetime

import database as db
from data_layer import clean_cache, get_market_overview
import tracker

SCAN_INTERVAL_SECONDS = 2 * 60
MAX_OPEN_TRADES = 3


def scan_once():
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f"\n⏱ {now_str} tracker")
    clean_cache()
    tracker.check_trades()


def xsec_tick():
    """Cross-sectional momentum — независимая стратегия, ребаланс раз в неделю."""
    try:
        import xsec_strategy
        if xsec_strategy.should_rebalance():
            xsec_strategy.rebalance()
    except Exception as e:
        import traceback
        print(f"❌ xsec: {e}\n{traceback.format_exc()}")


def trend_tick():
    """Trend-Following — независимая стратегия, проверка раз в день."""
    try:
        import trend_strategy, database as _db
        st = _db.trend_get_state()
        last = st.get('last_check_ts') if st else None
        if not last or (time.time() * 1000 - last) >= 20 * 3600 * 1000:
            trend_strategy.tick()
            trend_strategy.check_phase_change()
    except Exception as e:
        import traceback
        print(f"❌ trend: {e}\n{traceback.format_exc()}")


def safe_scan():
    try:
        scan_once()
    except Exception as e:
        import traceback
        print(f"❌ tracker loop: {e}\n{traceback.format_exc()}")
    xsec_tick()
    trend_tick()
    try:
        get_market_overview()
    except Exception as e:
        print(f"❌ overview: {e}")


def run_scanner_loop():
    safe_scan()
    while True:
        time.sleep(SCAN_INTERVAL_SECONDS)
        safe_scan()


def start_background_scanner():
    db.init_db()
    t = threading.Thread(target=run_scanner_loop, daemon=True)
    t.start()
    print(f"⏰ Tracker loop | макс {MAX_OPEN_TRADES} открытых | без NFI-автоскана")
    return t
