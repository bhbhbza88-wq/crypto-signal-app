"""
Scanner — фоновый процесс, сканирующий рынок каждые 2 минуты.
Заменяет send_signal()/scan() из бота: вместо Telegram пишет в БД.
"""

import time
import json
import threading
import asyncio
from datetime import datetime

import database as db
from data_layer import clean_cache
from nfi_strategy import scan_for_nfi_signals
import tracker

try:
    from telegram_bot import notify_new_signal, notify_signal_closed, send_daily_summary
    TELEGRAM_ENABLED = True
except ImportError:
    TELEGRAM_ENABLED = False
    print("⚠️ telegram_bot не найден, уведомления отключены")

SCAN_INTERVAL_SECONDS = 2 * 60


def register_signal(nfi_result):
    """NFI сигнал -> БД."""
    signal = nfi_result['signal']
    symbol = nfi_result['symbol']
    entry = nfi_result['entry']
    stop = nfi_result['stop']
    tp1 = nfi_result['tp1']
    tp2 = nfi_result['tp2']
    pos_usdt = nfi_result['position_size']
    score = nfi_result['score']
    last = nfi_result['last']
    
    # Сохраняем свечи для графика
    candles = nfi_result['df'].tail(60)[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    candles_json = candles.to_json(orient='records')
    entry_reasons_json = json.dumps(nfi_result.get('entry_reasons', []), ensure_ascii=False)

    trade = {
        'signal': signal, 'entry': entry, 'stop': stop,
        'tp1': tp1, 'tp2': tp2, 'tp3': tp2 * 1.5,  # tp3 пропорциональный
        'score': score, 'regime': 'NFI',
        'tp1_hit': False, 'tp2_hit': False,
        'be_hit': False, 'potential_warned': False,
        'opened_at': datetime.now().isoformat(),
        'candles_json': candles_json,
        'entry_reasons_json': entry_reasons_json,
        'position_size': pos_usdt,
    }
    db.upsert_trade(symbol, trade)
    db.add_event(symbol, 'new_signal',
                 f"NFI {signal} | score={score}/20 | вход={entry:.4f} | позиция~{pos_usdt:.0f} USDT")
    print(f"✅ {symbol} {signal} | score={score}/20 | EWO entry")

    # Telegram
    if TELEGRAM_ENABLED:
        tg_data = {
            'symbol': symbol,
            'signal': signal,
            'entry': entry,
            'stop': stop,
            'tp1': tp1,
            'tp2': tp2,
            'score': score,
            'regime': 'NFI',
            'position_size': pos_usdt,
        }
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(notify_new_signal(tg_data))
            loop.close()
        except Exception as e:
            print(f"⚠️ Telegram ошибка: {e}")


MAX_OPEN_TRADES = 3
DCA_THRESHOLD = -1.5
DCA_MULT = 0.5


def pnl_pct(signal, entry, price):
    return ((price - entry) / entry * 100) if signal == 'LONG' else ((entry - price) / entry * 100)


def try_dca(symbol, trade):
    """DCA при просадке."""
    if trade.get('dca_done'):
        return
    try:
        from data_layer import fetch_ticker
        ticker = fetch_ticker(symbol)
        if not ticker:
            return
        price = ticker['last']
        pnl = pnl_pct(trade['signal'], trade['entry'], price)
        if pnl <= DCA_THRESHOLD:
            orig_pos = trade.get('position_size', 0)
            dca_pos = orig_pos * DCA_MULT
            orig_entry = trade['entry']
            new_entry = (orig_entry * orig_pos + price * dca_pos) / (orig_pos + dca_pos)
            trade['entry'] = new_entry
            trade['position_size'] = orig_pos + dca_pos
            trade['dca_done'] = True
            db.upsert_trade(symbol, trade)
            db.add_event(symbol, 'dca', f"DCA: добавлено {dca_pos:.0f} USDT по {price:.4f}")
            print(f"📊 DCA {symbol}: новая средняя {new_entry:.4f}")
    except Exception as e:
        print(f"⚠️ DCA ошибка {symbol}: {e}")


def scan_once():
    print(f"\n🔍 {datetime.now().strftime('%H:%M:%S')}")
    clean_cache()
    tracker.check_trades()

    open_trades = db.load_trades()

    # DCA для открытых позиций
    for symbol, trade in open_trades.items():
        try_dca(symbol, trade)

    if len(open_trades) >= MAX_OPEN_TRADES:
        print(f"⏳ Активно {len(open_trades)}/{MAX_OPEN_TRADES}: {', '.join(open_trades.keys())}")
        return

    # Сканируем на NFI сигналы
    signals = scan_for_nfi_signals()
    
    if not signals:
        print("⏳ Нет NFI сигналов...")
        return

    # Открываем топ сигналы
    slots = MAX_OPEN_TRADES - len(open_trades)
    opened_count = 0
    
    for nfi_sig in signals[:slots]:
        if nfi_sig['symbol'] in open_trades:
            continue
        print(f"💎 NFI: {nfi_sig['symbol']} {nfi_sig['signal']} score={nfi_sig['score']}/20")
        register_signal(nfi_sig)
        opened_count += 1
    
    if opened_count == 0:
        print("⏳ Нет новых сигналов...")


def safe_scan():
    try:
        scan_once()
    except Exception as e:
        import traceback
        print(f"❌ scan: {e}\n{traceback.format_exc()}")


def run_scanner_loop():
    """Запускается в отдельном потоке: сканирует рынок каждые 2 минуты."""
    safe_scan()
    while True:
        time.sleep(SCAN_INTERVAL_SECONDS)
        safe_scan()


def start_background_scanner():
    db.init_db()
    thread = threading.Thread(target=run_scanner_loop, daemon=True)
    thread.start()
    print("⏰ Сканер запущен в фоне (каждые 2 минуты)")
    return thread