"""
V8 Strategy — MTF (4h+1h+30m), Pullback, Structure, Trend Strength,
Volume Climax Filter, Score 0-20, ADX >= 23.
Извлечено из native_cod.py, адаптировано под текущий проект.
"""

import os
import time
import pandas as pd
from data_layer import (
    fetch_data_cached, build_features, detect_regime,
    get_active_symbols, api_call, exchange,
)

# ── Параметры ────────────────────────────────────────────────────
SL_BASE  = 1.8
TP1_BASE = 2.5
TP2_BASE = 4.0
TP3_BASE = 6.0

DEPOSIT  = float(os.environ.get("DEPOSIT",  "1000"))
RISK_PCT = float(os.environ.get("RISK_PCT", "1.5"))

SCORE_MIN = int(os.environ.get("SCORE_MIN", "15"))
SCORE_MAX = 20
ADX_MIN   = 23


def detect_pullback(df, signal):
    if len(df) < 10:
        return False, 0
    recent = df.tail(10)
    last   = df.iloc[-1]
    if signal == 'LONG':
        touched_ema21 = (recent['low'] <= recent['ema21'] * 1.005).any()
        touched_ema50 = (recent['low'] <= recent['ema50'] * 1.008).any()
        resumed = last['close'] > last['ema21']
        if (touched_ema21 or touched_ema50) and resumed:
            return True, (3 if touched_ema50 else 2)
    else:
        touched_ema21 = (recent['high'] >= recent['ema21'] * 0.995).any()
        touched_ema50 = (recent['high'] >= recent['ema50'] * 0.992).any()
        resumed = last['close'] < last['ema21']
        if (touched_ema21 or touched_ema50) and resumed:
            return True, (3 if touched_ema50 else 2)
    return False, 0


def detect_structure(df, signal):
    if len(df) < 20:
        return False, 0
    recent = df.tail(20)
    highs, lows = [], []
    for i in range(1, len(recent) - 1):
        if recent['high'].iloc[i] > recent['high'].iloc[i-1] and recent['high'].iloc[i] > recent['high'].iloc[i+1]:
            highs.append(recent['high'].iloc[i])
        if recent['low'].iloc[i] < recent['low'].iloc[i-1] and recent['low'].iloc[i] < recent['low'].iloc[i+1]:
            lows.append(recent['low'].iloc[i])
    if len(highs) < 2 or len(lows) < 2:
        return False, 0
    if signal == 'LONG':
        hh = all(highs[i] > highs[i-1] for i in range(1, len(highs)))
        hl = all(lows[i]  > lows[i-1]  for i in range(1, len(lows)))
        if hh and hl: return True, 3
        if hh or hl:  return True, 1
    else:
        lh = all(highs[i] < highs[i-1] for i in range(1, len(highs)))
        ll = all(lows[i]  < lows[i-1]  for i in range(1, len(lows)))
        if lh and ll: return True, 3
        if lh or ll:  return True, 1
    return False, 0


def detect_trend_strength(df):
    last = df.iloc[-1]
    if last['close'] == 0:
        return 0
    spread = abs(last['ema9'] - last['ema50']) / last['close']
    if spread > 0.04:   return 3
    elif spread > 0.02: return 2
    elif spread > 0.01: return 1
    return 0


def detect_volume_climax(df):
    if len(df) < 20:
        return False
    last    = df.iloc[-1]
    vol_avg = last['vol_avg']
    if pd.isna(vol_avg) or vol_avg == 0:
        return False
    return (last['volume'] / vol_avg) > 4.0


def detect_ema_cross_fresh(df, signal, max_bars=5):
    if len(df) < max_bars + 2:
        return False
    recent = df.tail(max_bars + 1)
    for i in range(1, len(recent)):
        prev = recent.iloc[i-1]
        curr = recent.iloc[i]
        if signal == 'LONG'  and prev['ema9'] <= prev['ema21'] and curr['ema9'] > curr['ema21']:
            return True
        if signal == 'SHORT' and prev['ema9'] >= prev['ema21'] and curr['ema9'] < curr['ema21']:
            return True
    return False


def detect_trend_stable(df, signal, lookback=5):
    if len(df) < lookback + 1:
        return False
    recent = df.tail(lookback)
    if signal == 'LONG':
        return ((recent['ema9'] > recent['ema21']).all() and
                (recent['close'] > recent['ema50']).sum() >= lookback - 1)
    return ((recent['ema9'] < recent['ema21']).all() and
            (recent['close'] < recent['ema50']).sum() >= lookback - 1)


def volume_healthy(df):
    last = df.iloc[-1]
    return last['volume'] > last['vol_avg'] and last['vol_trend'] > 0.85


def mtf_confirms(df_4h, df_1h, signal):
    l4 = df_4h.iloc[-1]
    l1 = df_1h.iloc[-1]
    if signal == 'LONG':
        return (l4['ema9'] > l4['ema21'] and l4['close'] > l4['ema50'] and
                l1['ema9'] > l1['ema21'] and l1['close'] > l1['ema50'])
    return (l4['ema9'] < l4['ema21'] and l4['close'] < l4['ema50'] and
            l1['ema9'] < l1['ema21'] and l1['close'] < l1['ema50'])


def is_overextended(df, signal):
    last = df.iloc[-1]
    atr  = last['atr']
    if pd.isna(atr) or atr == 0:
        return False
    if abs(last['close'] - last['open']) > atr * 2.5:
        return True
    if signal == 'LONG'  and last['rsi'] > 76: return True
    if signal == 'SHORT' and last['rsi'] < 24: return True
    if df.tail(4)['high'].max() - df.tail(4)['low'].min() > atr * 4.0:
        return True
    return False


def entry_conditions(df, signal):
    last = df.iloc[-1]
    if signal == 'LONG':
        return (last['ema9'] > last['ema21'] and last['close'] > last['ema50'] and
                40 < last['rsi'] < 70 and last['plus_di'] > last['minus_di'])
    return (last['ema9'] < last['ema21'] and last['close'] < last['ema50'] and
            30 < last['rsi'] < 60 and last['minus_di'] > last['plus_di'])


# ── BTC Filter ───────────────────────────────────────────────────
_btc_cache = {'ts': 0.0, 'regime': 'CHOP'}

def get_btc_regime():
    now = time.time()
    if now - _btc_cache['ts'] < 300:
        return _btc_cache['regime']
    d = api_call(exchange.fetch_ohlcv, 'BTC/USDT', '1h', limit=60)
    if not d:
        return _btc_cache['regime']
    df = build_features(pd.DataFrame(d, columns=['timestamp','open','high','low','close','volume']))
    regime, _ = detect_regime(df)
    _btc_cache.update({'ts': now, 'regime': regime})
    return regime

def btc_allows(symbol, signal):
    if symbol == 'BTC/USDT':
        return True
    btc = get_btc_regime()
    if signal == 'LONG'  and btc == 'DOWNTREND':
        print(f"  🚫 BTC DOWNTREND — лонг заблокирован")
        return False
    if signal == 'SHORT' and btc == 'UPTREND':
        print(f"  🚫 BTC UPTREND — шорт заблокирован")
        return False
    return True


# ── Score 0-20 ───────────────────────────────────────────────────
def calc_score(df_30m, df_1h, regime, adx_1h, signal):
    last      = df_30m.iloc[-1]
    adx_30m   = last['adx']   if not pd.isna(last['adx'])   else 0
    atr_pct   = last['atr'] / last['close'] if last['close'] > 0 else 0
    vol_ratio = last['volume'] / (last['vol_avg'] + 1e-10)
    score     = 0

    if vol_ratio > 2.0:     score += 3
    elif vol_ratio > 1.5:   score += 2
    elif vol_ratio > 1.2:   score += 1

    if adx_30m > 35:        score += 3
    elif adx_30m > 28:      score += 2
    elif adx_30m > ADX_MIN: score += 1

    if regime in ('UPTREND', 'DOWNTREND'):
        score += 2
        if adx_1h > 20: score += 1

    if atr_pct > 0.006:     score += 2
    elif atr_pct > 0.003:   score += 1

    _, pb_bonus = detect_pullback(df_30m, signal)
    score += pb_bonus

    _, st_bonus = detect_structure(df_30m, signal)
    score += st_bonus

    score += detect_trend_strength(df_30m)

    return min(score, SCORE_MAX)


# ── Levels ───────────────────────────────────────────────────────
def get_mults(adx, atr_pct):
    sl, tp1, tp2, tp3 = SL_BASE, TP1_BASE, TP2_BASE, TP3_BASE
    if adx > 40:
        tp1 *= 1.25; tp2 *= 1.35; tp3 *= 1.50; sl *= 1.15
    elif adx > 28:
        tp1 *= 1.10; tp2 *= 1.15; tp3 *= 1.20; sl *= 1.08
    if atr_pct > 0.008:   sl *= 1.15
    elif atr_pct > 0.005: sl *= 1.08
    return round(sl,3), round(tp1,3), round(tp2,3), round(tp3,3)

def calc_levels(signal, entry, atr_30m, atr_1h, sl_m, tp1_m, tp2_m, tp3_m):
    # Основной таймфрейм 1h — используем только atr_1h
    atr = atr_1h
    d   = atr * sl_m
    if signal == 'LONG':
        return entry - d, entry + atr*tp1_m, entry + atr*tp2_m, entry + atr*tp3_m
    return entry + d, entry - atr*tp1_m, entry - atr*tp2_m, entry - atr*tp3_m

def calc_position_size(entry, stop):
    risk_usdt = DEPOSIT * RISK_PCT / 100
    sl_dist   = abs(entry - stop)
    if sl_dist == 0:
        return 0.0
    return round(risk_usdt / sl_dist * entry, 2)


# ── Generate Signal ──────────────────────────────────────────────
def generate_nfi_signal(symbol):
    data = fetch_data_cached(symbol)
    if not data:
        return None

    df_4h  = build_features(data['4h'])
    df_1h  = build_features(data['1h'])
    df_30m = build_features(data['30m'])

    # Режим рынка и основная логика — на 1h
    regime, adx_1h = detect_regime(df_1h)
    if regime in ('FLAT', 'CHOP'):
        return None

    last_1h = df_1h.iloc[-1]
    adx_1h_val = last_1h['adx'] if not pd.isna(last_1h['adx']) else 0

    if adx_1h_val < ADX_MIN:                          return None
    if pd.isna(last_1h['atr']) or last_1h['atr'] <= 0: return None
    if pd.isna(last_1h['rsi']):                        return None

    # Условия входа проверяем на 1h (основной TF)
    signal = None
    if entry_conditions(df_1h, 'LONG')  and regime == 'UPTREND':   signal = 'LONG'
    elif entry_conditions(df_1h, 'SHORT') and regime == 'DOWNTREND': signal = 'SHORT'
    if not signal: return None

    if not detect_trend_stable(df_1h, signal):  return None
    if not mtf_confirms(df_4h, df_1h, signal):  return None
    if not volume_healthy(df_1h):               return None
    if not btc_allows(symbol, signal):          return None
    if is_overextended(df_1h, signal):          return None
    if detect_volume_climax(df_1h):
        print(f"  🚫 {symbol}: объём кульминация")
        return None

    # Триггер входа — свежий кросс или откат на 1h
    fresh_cross     = detect_ema_cross_fresh(df_1h, signal, max_bars=3)
    has_pullback, _ = detect_pullback(df_1h, signal)
    if not fresh_cross and not has_pullback:
        print(f"  ⛔ {symbol}: нет кросса и нет отката на 1h")
        return None

    # Score считаем по 1h
    score = calc_score(df_1h, df_1h, regime, adx_1h_val, signal)
    if score < SCORE_MIN:
        print(f"  ⛔ {symbol}: score={score} < {SCORE_MIN}")
        return None

    entry       = last_1h['close']
    atr_1h_val2 = last_1h['atr']
    atr_pct     = atr_1h_val2 / entry if entry > 0 else 0

    sl_m, tp1_m, tp2_m, tp3_m = get_mults(adx_1h_val, atr_pct)
    # calc_levels теперь использует atr_1h как основной
    stop, tp1, tp2, tp3 = calc_levels(signal, entry, atr_1h_val2, atr_1h_val2, sl_m, tp1_m, tp2_m, tp3_m)
    pos_size = calc_position_size(entry, stop)
    if pos_size <= 0: return None

    _, pb_bonus = detect_pullback(df_1h, signal)
    _, st_bonus = detect_structure(df_1h, signal)

    print(f"💎 {symbol}: {signal} | {regime} | ADX={adx_1h_val:.0f} | score={score}/{SCORE_MAX}")

    return {
        'symbol':        symbol,
        'signal':        signal,
        'score':         score,
        'regime':        regime,
        'entry':         entry,
        'stop':          stop,
        'tp1':           tp1,
        'tp2':           tp2,
        'tp3':           tp3,
        'position_size': pos_size,
        'last':          last_1h,
        'last_1h':       last_1h,
        'df':            df_1h,   # основной TF теперь 1h
        'entry_reasons': [
            f'Режим: {regime} | ADX {adx_1h_val:.0f}',
            f'RSI: {last_1h["rsi"]:.0f} | Score: {score}/{SCORE_MAX}',
            f'Pullback к EMA: {"✓" if pb_bonus > 0 else "—"}',
            f'Структура HH/HL: {"✓" if st_bonus > 0 else "—"}',
            f'MTF 4h подтверждение: ✓',
            f'BTC: {get_btc_regime()}',
        ],
    }


def scan_for_nfi_signals():
    signals = []
    for symbol in get_active_symbols():
        sig = generate_nfi_signal(symbol)
        if sig:
            signals.append(sig)
    signals.sort(key=lambda x: x['score'], reverse=True)
    return signals


# ── Совместимость с бэктестом в main.py ─────────────────────────
def build_nfi_features(df):
    return df

def should_enter(df, signal):
    """
    Для бэктеста на 1h данных. LONG и SHORT.
    """
    if len(df) < 50:
        return False
    last = df.iloc[-1]
    adx  = last['adx'] if not pd.isna(last.get('adx', float('nan'))) else 0
    if adx < ADX_MIN:
        return False
    if not entry_conditions(df, signal):
        return False
    if not detect_trend_stable(df, signal):
        return False
    if is_overextended(df, signal):
        return False
    if detect_volume_climax(df):
        return False
    fresh_cross     = detect_ema_cross_fresh(df, signal, max_bars=3)
    has_pullback, _ = detect_pullback(df, signal)
    return fresh_cross or has_pullback