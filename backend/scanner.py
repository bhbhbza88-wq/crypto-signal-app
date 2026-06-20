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

MAX_OPEN_TRADES = 3  # максимум одновременных позиций
DCA_THRESHOLD = -1.5  # DCA при просадке -1.5%
DCA_MULT = 0.5        # DCA добавляет 50% от исходной позиции


def pnl_pct(signal, entry, price):
    return ((price - entry) / entry * 100) if signal == 'LONG' else ((entry - price) / entry * 100)


def try_dca(symbol, trade):
    """DCA — добавляем к позиции если просадка >= DCA_THRESHOLD."""
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
            # Считаем новую среднюю цену входа
            orig_pos = trade.get('position_size', 0)
            dca_pos = orig_pos * DCA_MULT
            orig_entry = trade['entry']
            if trade['signal'] == 'LONG':
                new_entry = (orig_entry * orig_pos + price * dca_pos) / (orig_pos + dca_pos)
            else:
                new_entry = (orig_entry * orig_pos + price * dca_pos) / (orig_pos + dca_pos)
            trade['entry'] = new_entry
            trade['position_size'] = orig_pos + dca_pos
            trade['dca_done'] = True
            db.upsert_trade(symbol, trade)
            db.add_event(symbol, 'dca',
                         f"DCA: добавлено {dca_pos:.0f} USDT по {price:.4f} | новая средняя: {new_entry:.4f}")
            print(f"📊 DCA {symbol}: новая средняя {new_entry:.4f}")
    except Exception as e:
        print(f"⚠️ DCA ошибка {symbol}: {e}")

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

    # DCA для открытых позиций
    for symbol, trade in open_trades.items():
        try_dca(symbol, trade)

    if len(open_trades) >= MAX_OPEN_TRADES:
        print(f"⏳ Активно {len(open_trades)}/{MAX_OPEN_TRADES}: {', '.join(open_trades.keys())}")
        return

    # Ищем лучшие сигналы (топ по score)
    from signal_engine import get_active_symbols, generate_signal
    signals = []
    for s in get_active_symbols():
        if s in open_trades:
            continue  # уже есть открытая по этой паре
        r = generate_signal(s)
        if r:
            signals.append(r)

    if not signals:
        print("⏳ Нет сигналов...")
        return

    # Сортируем по score и берём топ до MAX_OPEN_TRADES
    signals.sort(key=lambda x: x['score'], reverse=True)
    slots = MAX_OPEN_TRADES - len(open_trades)
    for best in signals[:slots]:
        print(f"💎 Открываем: {best['symbol']} {best['signal']} score={best['score']}/20")
        register_signal(best)


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