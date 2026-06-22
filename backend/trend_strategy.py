"""
Trend-Following — позиционная стратегия "в рынке / в кэше" по золотому кресту.

Идея (валидировано на 5 годах, реальные издержки, walk-forward, весь грид параметров,
честно по каждой монете):
  - На топ-5 ликвидных монетах: EMA50 > EMA200 -> держим (лонг). Иначе -> кэш.
  - Это НЕ источник альфы — это снижение риска: в среднем идёт вровень с buy&hold
    в обычные годы, но сильно меньше теряет в крахи (2022: -64% holding vs гораздо
    мягче с трендом). Топ-5: ROI +161% / Sharpe 0.73 / maxDD -33% за 5 лет
    (buy&hold BTC: +91% / 0.51 / -77%).
  - ОЧЕНЬ редкие сделки по дизайну (~7/год на 5 монет, ~раз в 7 недель) — это
    и есть причина, почему он работает: мало шума, мало издержек. Не нужно
    форсировать частоту — на полной вселенной 39 монет результат УЖЕ ХУЖЕ
    buy&hold (whipsaw на шумных альтах). Топ-5 — проверенный предел.

Это ОТДЕЛЬНАЯ стратегия от momentum-сканера (который остаётся "высокочастотной"
стороной) и от cross-sectional long-short. Здесь нет TP/SL — выход при
пересечении EMA вниз. Проверяется раз в день (тренд не меняется внутри дня).
"""
import time
import json
import datetime
import pandas as pd
import numpy as np

from data_layer import exchange, api_call
import database as db

COMM = 0.055 / 100
SLIP = 0.10 / 100

TREND_UNIVERSE = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT']
TREND_EMA_FAST = 50
TREND_EMA_SLOW = 200
TREND_DEPOSIT = 1000   # бумажный депозит на каждую монету (independent allocation)

_daily_cache = {'ts': 0.0, 'data': {}}
_CACHE_TTL = 3600 * 4  # 4 часа — тренд меняется редко, не нужно дёргать биржу часто


def fetch_daily_history(symbol, days=400):
    """Дневные свечи — нужно >= EMA_SLOW+несколько для надёжного сигнала."""
    now = time.time()
    cache = _daily_cache['data'].get(symbol)
    if cache is not None and now - _daily_cache['ts'] < _CACHE_TTL:
        return cache
    try:
        raw = api_call(exchange.fetch_ohlcv, symbol, '1d', limit=days)
    except Exception:
        raw = None
    if not raw or len(raw) < TREND_EMA_SLOW + 5:
        return None
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df = pd.DataFrame(raw, columns=cols)
    _daily_cache['data'][symbol] = df
    _daily_cache['ts'] = now
    return df


def compute_signal(symbol):
    """Возвращает (in_trend: bool, close, ema_fast, ema_slow) по последней ЗАКРЫТОЙ свече."""
    df = fetch_daily_history(symbol)
    if df is None or len(df) < TREND_EMA_SLOW + 2:
        return None
    close = df['close']
    ef = close.ewm(span=TREND_EMA_FAST, adjust=False).mean()
    es = close.ewm(span=TREND_EMA_SLOW, adjust=False).mean()
    # последняя закрытая свеча — предпоследняя строка (последняя может быть неполной)
    i = -2 if len(df) >= TREND_EMA_SLOW + 3 else -1
    return {
        'in_trend': bool(ef.iloc[i] > es.iloc[i]),
        'close': float(close.iloc[i]),
        'ema_fast': float(ef.iloc[i]),
        'ema_slow': float(es.iloc[i]),
    }


def compute_all_signals():
    out = {}
    for sym in TREND_UNIVERSE:
        sig = compute_signal(sym)
        if sig:
            out[sym] = sig
    return out


def get_current_prices(symbols):
    out = {}
    for sym in symbols:
        try:
            t = api_call(exchange.fetch_ticker, sym) or {}
            out[sym] = t.get('last')
        except Exception:
            out[sym] = None
    return out


# ══════════════════════════════════════════════════════════════════
# БУМАЖНАЯ ТОРГОВЛЯ — проверка раз в день (тренд не меняется внутри дня)
# ══════════════════════════════════════════════════════════════════
def _now_ms():
    return int(time.time() * 1000)


def _load_positions():
    st = db.trend_get_state()
    if not st or not st.get('positions_json'):
        return {}
    return json.loads(st['positions_json'])


def tick():
    """
    Раз в день (вызывается из scanner) — для каждой монеты:
      - если сигнал стал in_trend и позиции нет -> открыть
      - если сигнал стал не-in_trend и позиция есть -> закрыть, записать в лог
    """
    positions = _load_positions()
    signals = compute_all_signals()
    if not signals:
        return

    changed = False
    for sym, sig in signals.items():
        has_pos = sym in positions
        if sig['in_trend'] and not has_pos:
            positions[sym] = {'entry': sig['close'], 'opened_at': _now_ms()}
            db.add_event(sym, 'trend_enter', f"Trend-Following: вход (EMA{TREND_EMA_FAST}>{TREND_EMA_SLOW}) @ {sig['close']:.4f}")
            changed = True
        elif not sig['in_trend'] and has_pos:
            entry = positions[sym]['entry']
            pnl_pct = (sig['close'] - entry) / entry * 100 - (COMM + SLIP) * 100
            db.trend_add_log(_now_ms(), sym, entry, sig['close'], round(pnl_pct, 3))
            db.add_event(sym, 'trend_exit', f"Trend-Following: выход @ {sig['close']:.4f} ({pnl_pct:+.1f}%)")
            del positions[sym]
            changed = True

    if changed or not db.trend_get_state():
        db.trend_save_state(_now_ms(), json.dumps(positions))


def get_market_phase():
    """
    Информационный индикатор фазы рынка (по BTC, дневные свечи).
    ТОЛЬКО для отображения — не управляет капиталом ни в одной стратегии.
    Авто-переключение стратегий по фазе было честно протестировано и
    отклонено (long-short в любой фазе ухудшает результат относительно
    простого правила "в тренде — держим, нет тренда — кэш").
    """
    SIDEWAYS_THR = 0.05  # та же граница, что валидировали — для контекста, не для решений
    df = fetch_daily_history('BTC/USDT')
    if df is None or len(df) < TREND_EMA_SLOW + 2:
        return None
    close = df['close']
    ef = close.ewm(span=TREND_EMA_FAST, adjust=False).mean()
    es = close.ewm(span=TREND_EMA_SLOW, adjust=False).mean()
    i = -2 if len(df) >= TREND_EMA_SLOW + 3 else -1
    strength = float((ef.iloc[i] - es.iloc[i]) / es.iloc[i])
    if abs(strength) <= SIDEWAYS_THR:
        phase = 'SIDEWAYS'
    elif strength > 0:
        phase = 'UPTREND'
    else:
        phase = 'DOWNTREND'
    return {
        'phase': phase,
        'strength_pct': round(strength * 100, 2),
        'btc_close': float(close.iloc[i]),
        'ema_fast': round(float(ef.iloc[i]), 2),
        'ema_slow': round(float(es.iloc[i]), 2),
        'note': 'Только информационно — не переключает стратегии (проверено и отклонено)',
    }


def get_status():
    """Снимок для дашборда: открытые позиции с live-PnL + сигналы по всей вселенной."""
    positions = _load_positions()
    prices = get_current_prices(list(positions.keys())) if positions else {}
    pos_out = []
    for sym, p in positions.items():
        price = prices.get(sym)
        pnl = ((price - p['entry']) / p['entry'] * 100) if price and p['entry'] else 0.0
        pos_out.append({'symbol': sym, 'entry': p['entry'], 'price': price,
                        'pnl_pct': round(pnl, 2), 'opened_at': p.get('opened_at')})

    signals = compute_all_signals()
    sig_out = [{'symbol': s, 'in_trend': v['in_trend'], 'close': v['close'],
               'ema_fast': round(v['ema_fast'], 4), 'ema_slow': round(v['ema_slow'], 4),
               'distance_pct': round((v['ema_fast'] - v['ema_slow']) / v['ema_slow'] * 100, 2)}
              for s, v in signals.items()]

    log = db.trend_load_log(limit=200)
    closed_pnls = [r['pnl_pct'] for r in log]
    total_pnl = sum(closed_pnls)
    wins = sum(1 for p in closed_pnls if p > 0)

    return {
        'positions': pos_out,
        'signals': sig_out,
        'universe_size': len(TREND_UNIVERSE),
        'ema_fast': TREND_EMA_FAST, 'ema_slow': TREND_EMA_SLOW,
        'closed_trades': len(log),
        'wins': wins,
        'total_realized_pnl_pct': round(total_pnl, 2),
    }
