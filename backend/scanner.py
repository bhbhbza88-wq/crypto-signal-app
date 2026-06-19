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
from signal_engine import scan_for_best_signal, get_mults, calc_levels, calc_position
import tracker

try:
    from telegram_bot import notify_new_signal, notify_signal_closed, send_daily_summary
    TELEGRAM_ENABLED = True
except ImportError:
    TELEGRAM_ENABLED = False
    print("⚠️ telegram_bot не найден, уведомления отключены")

SCAN_INTERVAL_SECONDS = 2 * 60


def register_signal(result):
    """Берёт лучший сигнал, считает уровни и записывает как открытую сделку."""
    signal = result['signal']
    last = result['last']
    last_1h = result['last_1h']
    symbol = result['symbol']
    entry = last['close']
    regime = result['regime']
    adx_30m = result['adx_30m']
    score = result['score']

    atr_30m = last['atr']
    atr_1h = last_1h['atr'] if last_1h['atr'] == last_1h['atr'] else atr_30m  # NaN check
    atr_pct = atr_30m / entry if entry > 0 else 0

    sl_m, tp1_m, tp2_m, tp3_m = get_mults(adx_30m, atr_pct)
    stop, tp1, tp2, tp3 = calc_levels(signal, entry, atr_30m, atr_1h, sl_m, tp1_m, tp2_m, tp3_m)
    pos_usdt = calc_position(entry, stop)

    # Сохраняем последние N свечей для отображения графика на фронтенде
    candles = result['df'].tail(60)[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    candles_json = candles.to_json(orient='records')
    entry_reasons_json = json.dumps(result.get('entry_reasons', []), ensure_ascii=False)

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
                 f"Новый сигнал {signal} | score={score}/20 | вход={entry:.4f} | позиция~{pos_usdt:.0f} USDT")
    print(f"✅ {symbol} {signal} | score={score}/20 | ADX={adx_30m:.0f}")

    # Telegram уведомление
    if TELEGRAM_ENABLED:
        tg_data = {
            'symbol': symbol,
            'signal': signal,
            'entry': entry,
            'stop': stop,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'score': score,
            'regime': regime,
            'position_size': pos_usdt,
        }
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(notify_new_signal(tg_data))
            loop.close()
        except Exception as e:
            print(f"⚠️ Telegram ошибка: {e}")


def scan_once():
    print(f"\n🔍 {datetime.now().strftime('%H:%M:%S')}")
    clean_cache()
    tracker.check_trades()

    open_trades = db.load_trades()
    if open_trades:
        print(f"⏳ Активно: {', '.join(open_trades.keys())}")
        return

    print("🔍 Ищем сигнал...")
    best = scan_for_best_signal()
    if best:
        print(f"💎 Лучший: {best['symbol']} {best['signal']} score={best['score']}/20")
        register_signal(best)
    else:
        print("⏳ Нет сигналов...")


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
