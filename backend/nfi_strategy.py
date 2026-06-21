"""
V8 Strategy — оптимизированная версия.
Новое: Supertrend, MACD Histogram filter, Volatility Position Sizing,
Chandelier Exit trailing, Daily Loss Limit, Cooldown per pair.
"""

import os
import time
import pandas as pd
from datetime import datetime, timedelta
from data_layer import (
    fetch_data_cached, build_features, detect_regime,
    get_active_symbols, api_call, exchange,
)

# ── Параметры ────────────────────────────────────────────────────
SL_BASE  = 1.8
TP1_BASE = 2.5
TP2_BASE = 4.0
TP3_BASE = 6.0

DEPOSIT       = float(os.environ.get("DEPOSIT",  "1000"))
RISK_PCT      = float(os.environ.get("RISK_PCT", "1.5"))
SCORE_MIN     = int(os.environ.get("SCORE_MIN",  "18"))
SCORE_MAX     = 20
ADX_MIN       = 30
DAILY_LOSS_LIMIT_PCT = 3.0    # стоп торговли если за день потеряли >3% депозита
COOLDOWN_HOURS       = 4      # пауза после стопа на той же паре


# ══════════════════════════════════════════════════════════════════
# НОВЫЕ ИНДИКАТОРЫ
# ══════════════════════════════════════════════════════════════════

def calc_supertrend(df, period=10, multiplier=3.0):
    """
    Supertrend — лучший трендовый индикатор.
    Возвращает колонки supertrend_up (bullish) и supertrend_dir (1=up, -1=down).
    """
    df = df.copy()
    hl2 = (df['high'] + df['low']) / 2

    # ATR
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low']  - df['close'].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction  = pd.Series(1, index=df.index, dtype=int)

    for i in range(1, len(df)):
        # Upper band
        if upper.iloc[i] < upper.iloc[i-1] or df['close'].iloc[i-1] > upper.iloc[i-1]:
            upper.iloc[i] = upper.iloc[i]
        else:
            upper.iloc[i] = upper.iloc[i-1]

        # Lower band
        if lower.iloc[i] > lower.iloc[i-1] or df['close'].iloc[i-1] < lower.iloc[i-1]:
            lower.iloc[i] = lower.iloc[i]
        else:
            lower.iloc[i] = lower.iloc[i-1]

        # Direction
        if supertrend.iloc[i-1] == upper.iloc[i-1]:
            direction.iloc[i] = -1 if df['close'].iloc[i] > upper.iloc[i] else 1
        else:
            direction.iloc[i] = 1 if df['close'].iloc[i] < lower.iloc[i] else -1

        supertrend.iloc[i] = lower.iloc[i] if direction.iloc[i] == -1 else upper.iloc[i]

    df['supertrend']     = supertrend
    df['supertrend_dir'] = direction   # -1 = bullish, 1 = bearish
    return df


def calc_macd_histogram(df):
    """MACD Histogram — растёт = импульс в направлении тренда."""
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    histogram   = macd - signal_line
    return histogram


def calc_chandelier_exit(df, period=22, multiplier=3.0):
    """
    Chandelier Exit — трейлинг от максимума/минимума свечей.
    Лучше ATR-трейлинга: меньше ложных выбиваний.
    Returns: (long_stop, short_stop)
    """
    atr = df['atr'] if 'atr' in df.columns else (
        pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low']  - df['close'].shift()).abs(),
        ], axis=1).max(axis=1).rolling(14).mean()
    )
    highest_high = df['high'].rolling(period).max()
    lowest_low   = df['low'].rolling(period).min()
    long_stop    = highest_high - multiplier * atr
    short_stop   = lowest_low  + multiplier * atr
    return long_stop, short_stop


def supertrend_bullish(df):
    """Последние 3 свечи Supertrend = bullish."""
    if 'supertrend_dir' not in df.columns:
        return True  # если нет — не блокируем
    return (df['supertrend_dir'].tail(3) == -1).all()


def supertrend_bearish(df):
    """Последние 3 свечи Supertrend = bearish."""
    if 'supertrend_dir' not in df.columns:
        return True
    return (df['supertrend_dir'].tail(3) == 1).all()


def macd_confirms(df, signal):
    """MACD histogram растёт последние 2 свечи в направлении сигнала."""
    hist = calc_macd_histogram(df)
    if len(hist) < 3:
        return True
    h1, h2 = hist.iloc[-2], hist.iloc[-1]
    if signal == 'LONG':
        return h2 > h1 and h2 > 0   # растёт и в плюсе
    return h2 < h1 and h2 < 0       # падает и в минусе


def volatility_position_size(entry, stop, atr_pct):
    """
    Динамический размер позиции.
    При высокой волатильности (ATR > 1%) — уменьшаем риск вдвое.
    """
    risk_pct = RISK_PCT
    if atr_pct > 0.015:
        risk_pct *= 0.5    # экстремальная волатильность — половина риска
    elif atr_pct > 0.01:
        risk_pct *= 0.75   # высокая волатильность — 75% риска
    risk_usdt = DEPOSIT * risk_pct / 100
    sl_dist   = abs(entry - stop)
    if sl_dist == 0:
        return 0.0
    return round(risk_usdt / sl_dist * entry, 2)


# ══════════════════════════════════════════════════════════════════
# COOLDOWN и DAILY LOSS LIMIT
# ══════════════════════════════════════════════════════════════════

_cooldown_map = {}   # symbol -> datetime когда cooldown кончается
_daily_loss   = {'date': '', 'loss_pct': 0.0}


def set_cooldown(symbol):
    """Ставим паузу на COOLDOWN_HOURS после стопа."""
    _cooldown_map[symbol] = datetime.now() + timedelta(hours=COOLDOWN_HOURS)
    print(f"  ⏳ Cooldown {symbol}: {COOLDOWN_HOURS}ч")


def is_in_cooldown(symbol):
    until = _cooldown_map.get(symbol)
    if until and datetime.now() < until:
        return True
    return False


def record_daily_loss(pnl_pct_val):
    """Записываем потерю дня."""
    today = datetime.now().strftime('%Y-%m-%d')
    if _daily_loss['date'] != today:
        _daily_loss['date']     = today
        _daily_loss['loss_pct'] = 0.0
    if pnl_pct_val < 0:
        _daily_loss['loss_pct'] += abs(pnl_pct_val)


def daily_loss_ok():
    """True если лимит потерь за день не достигнут."""
    today = datetime.now().strftime('%Y-%m-%d')
    if _daily_loss['date'] != today:
        return True
    if _daily_loss['loss_pct'] >= DAILY_LOSS_LIMIT_PCT:
        print(f"  🛑 Daily loss limit {DAILY_LOSS_LIMIT_PCT}% достигнут — торговля остановлена")
        return False
    return True


# ══════════════════════════════════════════════════════════════════
# СУЩЕСТВУЮЩИЕ ДЕТЕКТОРЫ
# ══════════════════════════════════════════════════════════════════

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
        return False
    if signal == 'SHORT' and btc == 'UPTREND':
        return False
    return True


# ── Score 0-20 ───────────────────────────────────────────────────
def calc_score(df_1h, df_1h_unused, regime, adx_1h, signal):
    last      = df_1h.iloc[-1]
    adx_val   = last['adx']   if not pd.isna(last['adx'])   else 0
    atr_pct   = last['atr'] / last['close'] if last['close'] > 0 else 0
    vol_ratio = last['volume'] / (last['vol_avg'] + 1e-10)
    score     = 0

    # Объём (0-3)
    if vol_ratio > 2.0:     score += 3
    elif vol_ratio > 1.5:   score += 2
    elif vol_ratio > 1.2:   score += 1

    # ADX (0-3)
    if adx_val > 40:        score += 3
    elif adx_val > 35:      score += 2
    elif adx_val > ADX_MIN: score += 1

    # Режим (0-3)
    if regime in ('UPTREND', 'DOWNTREND'):
        score += 2
        if adx_1h > 25: score += 1

    # Волатильность ATR (0-2)
    if atr_pct > 0.006:     score += 2
    elif atr_pct > 0.003:   score += 1

    # Pullback (0-3)
    _, pb_bonus = detect_pullback(df_1h, signal)
    score += pb_bonus

    # Structure (0-3)
    _, st_bonus = detect_structure(df_1h, signal)
    score += st_bonus

    # Trend Strength (0-3)
    score += detect_trend_strength(df_1h)

    # Supertrend бонус (0-1)
    try:
        df_st = calc_supertrend(df_1h)
        if signal == 'LONG'  and supertrend_bullish(df_st): score += 1
        if signal == 'SHORT' and supertrend_bearish(df_st): score += 1
    except Exception:
        pass

    return min(score, SCORE_MAX)


# ── Levels ───────────────────────────────────────────────────────
def get_mults(adx, atr_pct):
    sl, tp1, tp2, tp3 = SL_BASE, TP1_BASE, TP2_BASE, TP3_BASE
    if adx > 40:
        tp1 *= 1.25; tp2 *= 1.35; tp3 *= 1.50; sl *= 1.15
    elif adx > 30:
        tp1 *= 1.10; tp2 *= 1.15; tp3 *= 1.20; sl *= 1.08
    if atr_pct > 0.008:   sl *= 1.15
    elif atr_pct > 0.005: sl *= 1.08
    return round(sl,3), round(tp1,3), round(tp2,3), round(tp3,3)


def calc_levels(signal, entry, atr_30m, atr_1h, sl_m, tp1_m, tp2_m, tp3_m):
    atr = atr_1h
    d   = atr * sl_m
    if signal == 'LONG':
        return entry - d, entry + atr*tp1_m, entry + atr*tp2_m, entry + atr*tp3_m
    return entry + d, entry - atr*tp1_m, entry - atr*tp2_m, entry - atr*tp3_m


def calc_position_size(entry, stop):
    """Базовый размер позиции — используй volatility_position_size для динамического."""
    risk_usdt = DEPOSIT * RISK_PCT / 100
    sl_dist   = abs(entry - stop)
    if sl_dist == 0:
        return 0.0
    return round(risk_usdt / sl_dist * entry, 2)


# ── Generate Signal ──────────────────────────────────────────────
def generate_nfi_signal(symbol):
    # Cooldown проверка
    if is_in_cooldown(symbol):
        return None

    # Daily loss limit
    if not daily_loss_ok():
        return None

    data = fetch_data_cached(symbol)
    if not data:
        return None

    df_4h  = build_features(data['4h'])
    df_1h  = build_features(data['1h'])

    # Supertrend на 1h
    try:
        df_1h = calc_supertrend(df_1h)
    except Exception:
        pass

    regime, adx_1h = detect_regime(df_1h)
    if regime in ('FLAT', 'CHOP'):
        return None

    last_1h    = df_1h.iloc[-1]
    adx_1h_val = last_1h['adx'] if not pd.isna(last_1h['adx']) else 0

    if adx_1h_val < ADX_MIN:                           return None
    if pd.isna(last_1h['atr']) or last_1h['atr'] <= 0: return None
    if pd.isna(last_1h['rsi']):                         return None

    signal = None
    if entry_conditions(df_1h, 'LONG')  and regime == 'UPTREND':   signal = 'LONG'
    elif entry_conditions(df_1h, 'SHORT') and regime == 'DOWNTREND': signal = 'SHORT'
    if not signal: return None

    # Supertrend фильтр
    if signal == 'LONG'  and not supertrend_bullish(df_1h): return None
    if signal == 'SHORT' and not supertrend_bearish(df_1h): return None

    # MACD histogram фильтр
    if not macd_confirms(df_1h, signal):
        print(f"  ⛔ {symbol}: MACD не подтверждает")
        return None

    if not detect_trend_stable(df_1h, signal):  return None
    if not mtf_confirms(df_4h, df_1h, signal):  return None
    if not volume_healthy(df_1h):               return None
    if not btc_allows(symbol, signal):          return None
    if is_overextended(df_1h, signal):          return None
    if detect_volume_climax(df_1h):             return None

    fresh_cross     = detect_ema_cross_fresh(df_1h, signal, max_bars=3)
    has_pullback, _ = detect_pullback(df_1h, signal)
    if not fresh_cross and not has_pullback:    return None

    score = calc_score(df_1h, df_1h, regime, adx_1h_val, signal)
    if score < SCORE_MIN:
        print(f"  ⛔ {symbol}: score={score} < {SCORE_MIN}")
        return None

    entry       = last_1h['close']
    atr_val     = last_1h['atr']
    atr_pct     = atr_val / entry if entry > 0 else 0

    sl_m, tp1_m, tp2_m, tp3_m = get_mults(adx_1h_val, atr_pct)
    stop, tp1, tp2, tp3 = calc_levels(signal, entry, atr_val, atr_val, sl_m, tp1_m, tp2_m, tp3_m)

    # Динамический размер позиции
    pos_size = volatility_position_size(entry, stop, atr_pct)
    if pos_size <= 0: return None

    _, pb_bonus = detect_pullback(df_1h, signal)
    _, st_bonus = detect_structure(df_1h, signal)

    # Chandelier Exit уровни для трекера
    long_ce, short_ce = calc_chandelier_exit(df_1h)
    chandelier_stop = float(long_ce.iloc[-1]) if signal == 'LONG' else float(short_ce.iloc[-1])

    print(f"💎 {symbol}: {signal} | {regime} | ADX={adx_1h_val:.0f} | score={score}/{SCORE_MAX} | vol_size={pos_size:.0f}$")

    return {
        'symbol':           symbol,
        'signal':           signal,
        'score':            score,
        'regime':           regime,
        'entry':            entry,
        'stop':             stop,
        'tp1':              tp1,
        'tp2':              tp2,
        'tp3':              tp3,
        'chandelier_stop':  chandelier_stop,
        'position_size':    pos_size,
        'last':             last_1h,
        'last_1h':          last_1h,
        'df':               df_1h,
        'entry_reasons': [
            f'Режим: {regime} | ADX {adx_1h_val:.0f}',
            f'Supertrend: {"✓ бычий" if signal == "LONG" else "✓ медвежий"}',
            f'MACD histogram: подтверждает ✓',
            f'RSI: {last_1h["rsi"]:.0f} | Score: {score}/{SCORE_MAX}',
            f'Pullback к EMA: {"✓" if pb_bonus > 0 else "—"}',
            f'Структура: {"✓" if st_bonus > 0 else "—"}',
            f'Позиция: {pos_size:.0f}$ (volatility-adjusted)',
            f'BTC: {get_btc_regime()}',
        ],
    }


def scan_for_nfi_signals():
    signals = []
    for symbol in get_active_symbols():
        try:
            sig = generate_nfi_signal(symbol)
            if sig:
                signals.append(sig)
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
    signals.sort(key=lambda x: x['score'], reverse=True)
    return signals


# ── Совместимость с бэктестом ────────────────────────────────────
def build_nfi_features(df):
    return df


def should_enter(df, signal):
    """Для бэктеста на 1h — все фильтры кроме BTC и cooldown."""
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
    # Supertrend
    try:
        df_st = calc_supertrend(df)
        if signal == 'LONG'  and not supertrend_bullish(df_st): return False
        if signal == 'SHORT' and not supertrend_bearish(df_st): return False
    except Exception:
        pass
    # MACD
    if not macd_confirms(df, signal):
        return False
    fresh_cross     = detect_ema_cross_fresh(df, signal, max_bars=3)
    has_pullback, _ = detect_pullback(df, signal)
    return fresh_cross or has_pullback