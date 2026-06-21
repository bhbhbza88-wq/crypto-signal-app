"""
Scanner — фоновый процесс, сканирующий рынок каждые 2 минуты.
V8 + Supertrend + MACD + Cooldown + Daily Loss Limit.
"""

import time
import json
import threading
import asyncio
from datetime import datetime

import database as db
from data_layer import clean_cache
from nfi_strategy import scan_for_nfi_signals, daily_loss_ok, DAILY_LOSS_LIMIT_PCT
import tracker

try:
    from telegram_bot import notify_new_signal, send_daily_summary
    TELEGRAM_ENABLED = True
except ImportError:
    TELEGRAM_ENABLED = False
    print("⚠️ telegram_bot не найден")

SCAN_INTERVAL_SECONDS = 2 * 60
MAX_OPEN_TRADES = 3


def register_signal(sig):
    symbol   = sig['symbol']
    signal   = sig['signal']
    entry    = sig['entry']
    stop     = sig['stop']
    tp1      = sig['tp1']
    tp2      = sig['tp2']
    tp3      = sig['tp3']
    score    = sig['score']
    regime   = sig.get('regime', 'V8')
    pos_usdt = sig['position_size']

    candles_json       = sig['df'].tail(60)[['timestamp','open','high','low','close','volume']].to_json(orient='records')
    entry_reasons_json = json.dumps(sig.get('entry_reasons', []), ensure_ascii=False)

    trade = {
        'signal': signal, 'entry': entry, 'stop': stop,
        'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
        'score': score, 'regime': regime,
        'tp1_hit': False, 'tp2_hit': False,
        'be_hit': False, 'potential_warned': False,
        'opened_at': datetime.now().isoformat(),
        'candles_json': candles_json,
        'entry_reasons_json': entry_reasons_json,
        'position_size': pos_usdt,
    }
    db.upsert_trade(symbol, trade)
    db.add_event(symbol, 'new_signal',
                 f"V8 {signal} | score={score}/20 | вход={entry:.4f} | {pos_usdt:.0f}$")
    print(f"✅ {symbol} {signal} | score={score}/20 | {regime} | {pos_usdt:.0f}$")

    if TELEGRAM_ENABLED:
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(notify_new_signal({
                'symbol': symbol, 'signal': signal,
                'entry': entry, 'stop': stop,
                'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
                'score': score, 'regime': regime,
                'position_size': pos_usdt,
            }))
            loop.close()
        except Exception as e:
            print(f"⚠️ Telegram: {e}")


def scan_once():
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f"\n🔍 {now_str}")

    # Daily loss limit — если лимит достигнут, пропускаем сканирование
    if not daily_loss_ok():
        print(f"🛑 Daily loss limit {DAILY_LOSS_LIMIT_PCT}% — сканирование пропущено")
        return

    clean_cache()
    tracker.check_trades()

    open_trades = db.load_trades()
    slots = MAX_OPEN_TRADES - len(open_trades)

    if slots <= 0:
        print(f"⏳ Активно {len(open_trades)}/{MAX_OPEN_TRADES}: {', '.join(open_trades.keys())}")
        return

    signals = scan_for_nfi_signals()

    if not signals:
        print("⏳ Нет сигналов")
        return

    print(f"📊 Сигналов: {len(signals)}, слотов: {slots}")

    opened = 0
    for sig in signals[:slots]:
        if sig['symbol'] in open_trades:
            continue
        register_signal(sig)
        open_trades[sig['symbol']] = True
        opened += 1

    if opened == 0:
        print("⏳ Все сигналы уже открыты")


def safe_scan():
    try:
        scan_once()
    except Exception as e:
        import traceback
        print(f"❌ scan: {e}\n{traceback.format_exc()}")


def run_scanner_loop():
    safe_scan()
    while True:
        time.sleep(SCAN_INTERVAL_SECONDS)
        safe_scan()


def start_background_scanner():
    db.init_db()
    t = threading.Thread(target=run_scanner_loop, daemon=True)
    t.start()
    print(f"⏰ Сканер запущен | макс {MAX_OPEN_TRADES} позиций | loss limit {DAILY_LOSS_LIMIT_PCT}%/день")
    return t