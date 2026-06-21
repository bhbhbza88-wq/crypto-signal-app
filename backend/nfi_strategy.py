"""
V9 Strategy — единая логика для лайва и бэктеста.
Ключевые принципы:
  - Вход на ОТКАТЕ к EMA (не на хае): RSI 35-55 для LONG, 45-65 для SHORT
  - R:R минимум 2:1 (SL 2.2 ATR, TP1 2.5, TP2 4.5, TP3 7.0)
  - Правильный векторизованный Supertrend (без look-ahead)
  - Score 0-20, единый core_signal() для лайва и бэктеста
  - Supertrend + MACD + ADX + объём + структура как фильтры
  - Cooldown, Daily Loss Limit, Volatility Sizing
"""

import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_layer import (
    fetch_data_cached, build_features, detect_regime,
    get_active_symbols, api_call, exchange,
)

# ── Параметры ────────────────────────────────────────────────────
SL_BASE   = 2.2     # шире — меньше ложных выбиваний на шуме
TP1_BASE  = 2.5     # R:R 1.14 на первой цели (фиксируем 40%)
TP2_BASE  = 4.5     # R:R 2.0
TP3_BASE  = 7.0     # R:R 3.2

DEPOSIT   = float(os.environ.get("DEPOSIT",  "1000"))
RISK_PCT  = float(os.environ.get("RISK_PCT", "1.5"))
SCORE_MIN = int(os.environ.get("SCORE_MIN", "15"))
SCORE_MAX = 20
ADX_MIN   = 22

DAILY_LOSS_LIMIT_PCT = 4.0
COOLDOWN_HOURS       = 3

# RSI окна — вход на откате, а не на пике импульса
RSI_LONG_MIN,  RSI_LONG_MAX  = 35, 58
RSI_SHORT_MIN, RSI_SHORT_MAX = 42, 65

# ── Выбор стратегии ──────────────────────────────────────────────
# "trend"          — трендследящая (вход на откате по тренду) — PF < 1, не использовать
# "mean_reversion" — возврат к среднему — анти-edge на этих данных, НЕ использовать
# "breakout"       — пробой консолидации — PF < 1, не использовать
# "momentum"       — ADX+EMA continuation, edge подтверждён forward-return аудитом —
#                    кандидат для dry-run (PF 1.59/0.65/1.77 на 30/90/180д с MAX_OPEN_TRADES=3)
STRATEGY_MODE = os.environ.get("STRATEGY_MODE", "momentum")

# ── Mean-reversion параметры ─────────────────────────────────────
BB_LENGTH    = 20
BB_STD       = 1.8    # было 2.0 — полосы ближе, больше касаний
MR_RSI_LONG  = 35     # было 30 — покупаем когда RSI < 35 (перепродан)
MR_RSI_SHORT = 65     # было 70 — продаём когда RSI > 65 (перекуплен)
MR_SL_BASE   = 2.0    # стоп за пределами полосы
MR_TP1_BASE  = 1.5    # цель — возврат к средней (короче чем у тренда)
MR_TP2_BASE  = 2.5
MR_TP3_BASE  = 3.5
MR_ADX_MAX   = 30     # было 25 — чуть шире окно "не сильный тренд"

# ── Breakout параметры ────────────────────────────────────────────
BO_LOOKBACK      = 20     # свечей консолидации до пробоя
BO_RANGE_MAX_PCT = 0.05   # диапазон консолидации <= 5% от цены
BO_VOL_MULT      = 1.5    # объём пробойной свечи >= 1.5x среднего
BO_BUFFER_ATR    = 0.15   # пробой должен быть за пределами диапазона на 0.15 ATR
BO_SL_BUFFER_ATR = 0.3    # стоп за диапазоном + буфер


# ══════════════════════════════════════════════════════════════════
# ИНДИКАТОРЫ
# ══════════════════════════════════════════════════════════════════

def calc_supertrend(df, period=10, multiplier=3.0):
    """
    Правильный векторизованный Supertrend без look-ahead.
    supertrend_dir: 1 = bullish (цена выше), -1 = bearish.
    """
    df = df.copy()
    high, low, close = df['high'], df['low'], df['close']
    hl2 = (high + low) / 2

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()

    upperband = hl2 + multiplier * atr
    lowerband = hl2 - multiplier * atr

    final_upper = upperband.copy()
    final_lower = lowerband.copy()
    n = len(df)
    fu = final_upper.values
    fl = final_lower.values
    cl = close.values

    for i in range(1, n):
        fu[i] = upperband.iloc[i] if (upperband.iloc[i] < fu[i-1] or cl[i-1] > fu[i-1]) else fu[i-1]
        fl[i] = lowerband.iloc[i] if (lowerband.iloc[i] > fl[i-1] or cl[i-1] < fl[i-1]) else fl[i-1]

    direction = np.ones(n, dtype=int)
    supertrend = np.zeros(n)
    supertrend[0] = fu[0]
    for i in range(1, n):
        if cl[i] > fu[i]:
            direction[i] = 1
        elif cl[i] < fl[i]:
            direction[i] = -1
        else:
            direction[i] = direction[i-1]
        supertrend[i] = fl[i] if direction[i] == 1 else fu[i]

    df['supertrend']     = supertrend
    df['supertrend_dir'] = direction   # 1 = bullish, -1 = bearish
    return df


def calc_macd(df):
    """MACD + histogram."""
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    return macd - signal_line


def calc_chandelier_exit(df, period=22, multiplier=3.0):
    """Chandelier Exit для трейлинга."""
    if 'atr' in df.columns:
        atr = df['atr']
    else:
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low']  - df['close'].shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
    long_stop  = df['high'].rolling(period).max() - multiplier * atr
    short_stop = df['low'].rolling(period).min()  + multiplier * atr
    return long_stop, short_stop


# ══════════════════════════════════════════════════════════════════
# ДЕТЕКТОРЫ
# ══════════════════════════════════════════════════════════════════

def detect_pullback(df, signal):
    """
    Откат к EMA21/EMA50 с возобновлением. Это ТОЧКА ВХОДА.
    Возвращает (bool, bonus).
    """
    if len(df) < 10:
        return False, 0
    recent = df.tail(8)
    last   = df.iloc[-1]
    atr = last['atr'] if not pd.isna(last.get('atr', float('nan'))) else 0
    if signal == 'LONG':
        touched21 = (recent['low'] <= recent['ema21'] * 1.004).any()
        touched50 = (recent['low'] <= recent['ema50'] * 1.006).any()
        prev      = df.iloc[-2]
        resumed   = (last['close'] > last['ema9'] + atr * 0.15 and
                     last['close'] > prev['close'] and
                     prev['close'] > df.iloc[-3]['close'])
        if (touched21 or touched50) and resumed:
            return True, (3 if touched50 else 2)
    else:
        touched21 = (recent['high'] >= recent['ema21'] * 0.996).any()
        touched50 = (recent['high'] >= recent['ema50'] * 0.994).any()
        prev      = df.iloc[-2]
        resumed   = (last['close'] < last['ema9'] - atr * 0.15 and
                     last['close'] < prev['close'] and
                     prev['close'] < df.iloc[-3]['close'])
        if (touched21 or touched50) and resumed:
            return True, (3 if touched50 else 2)
    return False, 0


def detect_structure(df, signal):
    """HH/HL для LONG, LH/LL для SHORT."""
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
        hh = highs[-1] > highs[-2]
        hl = lows[-1]  > lows[-2]
        if hh and hl: return True, 3
        if hh or hl:  return True, 1
    else:
        lh = highs[-1] < highs[-2]
        ll = lows[-1]  < lows[-2]
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
    """Аномальный объём = кульминация = разворот. Не входим."""
    if len(df) < 20:
        return False
    last = df.iloc[-1]
    if pd.isna(last['vol_avg']) or last['vol_avg'] == 0:
        return False
    return (last['volume'] / last['vol_avg']) > 4.5


def is_overextended(df, signal):
    """Цена слишком растянута — ждём отката."""
    last = df.iloc[-1]
    atr  = last['atr']
    if pd.isna(atr) or atr == 0:
        return False
    # Большая импульсная свеча
    if abs(last['close'] - last['open']) > atr * 2.8:
        return True
    # RSI на экстремуме
    if signal == 'LONG'  and last['rsi'] > 72: return True
    if signal == 'SHORT' and last['rsi'] < 28: return True
    # Цена далеко от EMA21 (>3 ATR) — перерастянута
    dist_ema21 = abs(last['close'] - last['ema21'])
    if dist_ema21 > atr * 3.0:
        return True
    return False


def entry_conditions(df, signal):
    """
    Базовые условия. RSI окно сдвинуто на ОТКАТ:
    LONG: тренд вверх, но RSI ещё не перегрет (35-58)
    SHORT: тренд вниз, RSI ещё не перепродан (42-65)
    """
    last = df.iloc[-1]
    if signal == 'LONG':
        return (last['ema9'] > last['ema21'] and
                last['close'] > last['ema50'] and
                RSI_LONG_MIN < last['rsi'] < RSI_LONG_MAX and
                last['plus_di'] > last['minus_di'])
    return (last['ema9'] < last['ema21'] and
            last['close'] < last['ema50'] and
            RSI_SHORT_MIN < last['rsi'] < RSI_SHORT_MAX and
            last['minus_di'] > last['plus_di'])


def macd_confirms(df, signal):
    """MACD histogram в нужную сторону и разворачивается к тренду."""
    hist = calc_macd(df)
    if len(hist) < 4:
        return True
    h0, h1, h2 = hist.iloc[-3], hist.iloc[-2], hist.iloc[-1]
    if signal == 'LONG':
        return h2 > h1 > h0          # 2 свечи подряд растёт, не разовый дёрг
    return h2 < h1 < h0               # 2 свечи подряд падает


def supertrend_ok(df, signal):
    if 'supertrend_dir' not in df.columns:
        return True
    d = df['supertrend_dir'].iloc[-1]
    return d == 1 if signal == 'LONG' else d == -1


# ══════════════════════════════════════════════════════════════════
# COOLDOWN + DAILY LOSS
# ══════════════════════════════════════════════════════════════════
_cooldown_map = {}
_daily_loss   = {'date': '', 'loss_pct': 0.0}

def set_cooldown(symbol):
    _cooldown_map[symbol] = datetime.now() + timedelta(hours=COOLDOWN_HOURS)

def is_in_cooldown(symbol):
    until = _cooldown_map.get(symbol)
    return bool(until and datetime.now() < until)

def record_daily_loss(pnl_pct_val):
    today = datetime.now().strftime('%Y-%m-%d')
    if _daily_loss['date'] != today:
        _daily_loss['date'] = today
        _daily_loss['loss_pct'] = 0.0
    if pnl_pct_val < 0:
        _daily_loss['loss_pct'] += abs(pnl_pct_val)

def daily_loss_ok():
    today = datetime.now().strftime('%Y-%m-%d')
    if _daily_loss['date'] != today:
        return True
    return _daily_loss['loss_pct'] < DAILY_LOSS_LIMIT_PCT


def get_risk_status():
    """Снимок риск-менеджмента для дашборда дальрана."""
    today = datetime.now().strftime('%Y-%m-%d')
    loss_pct = _daily_loss['loss_pct'] if _daily_loss['date'] == today else 0.0
    now = datetime.now()
    cooldowns = [
        {'symbol': sym, 'until': until.isoformat(), 'minutes_left': max(0, round((until - now).total_seconds() / 60))}
        for sym, until in _cooldown_map.items() if until > now
    ]
    return {
        'strategy_mode': STRATEGY_MODE,
        'daily_loss_pct': round(loss_pct, 2),
        'daily_loss_limit_pct': DAILY_LOSS_LIMIT_PCT,
        'daily_loss_ok': loss_pct < DAILY_LOSS_LIMIT_PCT,
        'cooldowns': cooldowns,
    }


# ══════════════════════════════════════════════════════════════════
# BTC FILTER
# ══════════════════════════════════════════════════════════════════
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
    if signal == 'LONG'  and btc == 'DOWNTREND': return False
    if signal == 'SHORT' and btc == 'UPTREND':   return False
    return True


# ══════════════════════════════════════════════════════════════════
# SCORE
# ══════════════════════════════════════════════════════════════════
def calc_score(df, regime, signal):
    last      = df.iloc[-1]
    adx_val   = last['adx'] if not pd.isna(last['adx']) else 0
    atr_pct   = last['atr'] / last['close'] if last['close'] > 0 else 0
    vol_ratio = last['volume'] / (last['vol_avg'] + 1e-10)
    score = 0

    # Объём (0-3)
    if vol_ratio > 1.8:   score += 3
    elif vol_ratio > 1.4: score += 2
    elif vol_ratio > 1.1: score += 1

    # ADX (0-3)
    if adx_val > 38:        score += 3
    elif adx_val > 30:      score += 2
    elif adx_val > ADX_MIN: score += 1

    # Режим (0-3)
    if regime in ('UPTREND', 'DOWNTREND'):
        score += 2
        if adx_val > 28: score += 1

    # Волатильность (0-2)
    if atr_pct > 0.006:   score += 2
    elif atr_pct > 0.003: score += 1

    # Pullback (0-3) — главный бонус, это точка входа
    _, pb = detect_pullback(df, signal)
    score += pb

    # Структура (0-3)
    _, st = detect_structure(df, signal)
    score += st

    # Сила тренда (0-3)
    score += detect_trend_strength(df)

    # Supertrend (0-1)
    if supertrend_ok(df, signal):
        score += 1

    return min(score, SCORE_MAX)


# ══════════════════════════════════════════════════════════════════
# LEVELS
# ══════════════════════════════════════════════════════════════════
def get_mults(adx, atr_pct):
    sl, tp1, tp2, tp3 = SL_BASE, TP1_BASE, TP2_BASE, TP3_BASE
    if adx > 38:
        tp1 *= 1.2; tp2 *= 1.3; tp3 *= 1.45
    elif adx > 30:
        tp1 *= 1.1; tp2 *= 1.15; tp3 *= 1.2
    if atr_pct > 0.008:   sl *= 1.1
    return round(sl,3), round(tp1,3), round(tp2,3), round(tp3,3)

def calc_levels(signal, entry, atr, sl_m, tp1_m, tp2_m, tp3_m):
    d = atr * sl_m
    if signal == 'LONG':
        return entry - d, entry + atr*tp1_m, entry + atr*tp2_m, entry + atr*tp3_m
    return entry + d, entry - atr*tp1_m, entry - atr*tp2_m, entry - atr*tp3_m

def volatility_position_size(entry, stop, atr_pct):
    risk_pct = RISK_PCT
    if atr_pct > 0.015:   risk_pct *= 0.5
    elif atr_pct > 0.01:  risk_pct *= 0.75
    risk_usdt = DEPOSIT * risk_pct / 100
    sl_dist   = abs(entry - stop)
    if sl_dist == 0:
        return 0.0
    return round(risk_usdt / sl_dist * entry, 2)

def calc_position_size(entry, stop):
    risk_usdt = DEPOSIT * RISK_PCT / 100
    sl_dist   = abs(entry - stop)
    if sl_dist == 0:
        return 0.0
    return round(risk_usdt / sl_dist * entry, 2)


# ══════════════════════════════════════════════════════════════════
# ЕДИНОЕ ЯДРО СИГНАЛА — используется и лайвом, и бэктестом
# ══════════════════════════════════════════════════════════════════
def calc_bollinger(df, length=BB_LENGTH, std=BB_STD):
    """Bollinger Bands — для mean-reversion."""
    mid   = df['close'].rolling(length).mean()
    sd    = df['close'].rolling(length).std()
    upper = mid + std * sd
    lower = mid - std * sd
    return mid, upper, lower


def core_signal_mean_reversion(df_1h, signal, df_4h=None):
    """
    Mean-reversion вход: цена ушла к краю Bollinger в ФЛЭТЕ, RSI на экстремуме,
    и появился разворотный признак. Выход — к средней полосе.

    LONG:  close <= lower BB, RSI < 30, бычья свеча (разворот вверх)
    SHORT: close >= upper BB, RSI > 70, медвежья свеча (разворот вниз)
    """
    if len(df_1h) < 50:
        return False

    last = df_1h.iloc[-1]
    prev = df_1h.iloc[-2]
    adx  = last['adx'] if not pd.isna(last['adx']) else 100

    if pd.isna(last['atr']) or last['atr'] <= 0:  return False
    if pd.isna(last['rsi']):                        return False

    # Mean-reversion работает только в боковике / слабом тренде
    if adx > MR_ADX_MAX:
        return False

    mid, upper, lower = calc_bollinger(df_1h)
    bb_lower = lower.iloc[-1]
    bb_upper = upper.iloc[-1]
    if pd.isna(bb_lower) or pd.isna(bb_upper):
        return False

    if signal == 'LONG':
        # Цена коснулась/пробила нижнюю полосу
        touched = last['low'] <= bb_lower
        # RSI перепродан
        rsi_ok  = last['rsi'] < MR_RSI_LONG
        # Разворотная свеча: закрытие выше открытия ИЛИ выше предыдущего close
        reversal = last['close'] > last['open'] or last['close'] > prev['close']
        return bool(touched and rsi_ok and reversal)
    else:
        touched = last['high'] >= bb_upper
        rsi_ok  = last['rsi'] > MR_RSI_SHORT
        reversal = last['close'] < last['open'] or last['close'] < prev['close']
        return bool(touched and rsi_ok and reversal)


def mr_levels(signal, entry, atr, df):
    """
    Уровни для mean-reversion. Цель — средняя полоса BB (TP1),
    стоп — за крайней полосой.
    """
    mid, upper, lower = calc_bollinger(df)
    bb_mid = mid.iloc[-1]
    sl  = atr * MR_SL_BASE
    if signal == 'LONG':
        stop = entry - sl
        tp1  = bb_mid if not pd.isna(bb_mid) else entry + atr * MR_TP1_BASE
        tp2  = entry + atr * MR_TP2_BASE
        tp3  = entry + atr * MR_TP3_BASE
        return stop, tp1, tp2, tp3
    else:
        stop = entry + sl
        tp1  = bb_mid if not pd.isna(bb_mid) else entry - atr * MR_TP1_BASE
        tp2  = entry - atr * MR_TP2_BASE
        tp3  = entry - atr * MR_TP3_BASE
        return stop, tp1, tp2, tp3


def _breakout_range(df):
    """Диапазон консолидации за BO_LOOKBACK свечей ДО текущей (текущая исключена)."""
    window = df.iloc[-(BO_LOOKBACK + 1):-1]
    return window['high'].max(), window['low'].min()


def core_signal_breakout(df, signal):
    """
    Вход на пробое диапазона консолидации с подтверждением объёмом.
    LONG:  close выше максимума диапазона + буфер ATR, объём >= 1.5x среднего
    SHORT: close ниже минимума диапазона - буфер ATR, объём >= 1.5x среднего
    Диапазон должен быть узким (<= 5% от цены) — иначе это не консолидация.
    """
    if len(df) < BO_LOOKBACK + 10:
        return False

    last = df.iloc[-1]
    atr  = last['atr'] if not pd.isna(last['atr']) else 0
    if atr <= 0:
        return False
    if pd.isna(last.get('vol_avg', float('nan'))) or last['vol_avg'] <= 0:
        return False

    range_high, range_low = _breakout_range(df)
    if pd.isna(range_high) or pd.isna(range_low):
        return False
    mid = (range_high + range_low) / 2
    if mid <= 0:
        return False
    range_pct = (range_high - range_low) / mid
    if range_pct > BO_RANGE_MAX_PCT:
        return False  # рынок не консолидировался — это не пробой, а просто движение

    vol_ok = last['volume'] >= last['vol_avg'] * BO_VOL_MULT

    if signal == 'LONG':
        broke = last['close'] > range_high + atr * BO_BUFFER_ATR
        return bool(broke and vol_ok)
    else:
        broke = last['close'] < range_low - atr * BO_BUFFER_ATR
        return bool(broke and vol_ok)


def breakout_levels(signal, entry, atr, df):
    """
    Уровни для breakout. Стоп — за диапазоном консолидации.
    Цели — измеренное движение (range width x 1/2/3), классика breakout-трейдинга.
    """
    range_high, range_low = _breakout_range(df)
    range_width = range_high - range_low
    if range_width <= 0 or pd.isna(range_width):
        range_width = atr * 2  # fallback

    if signal == 'LONG':
        stop = range_low - atr * BO_SL_BUFFER_ATR
        tp1  = entry + range_width * 1.0
        tp2  = entry + range_width * 2.0
        tp3  = entry + range_width * 3.0
    else:
        stop = range_high + atr * BO_SL_BUFFER_ATR
        tp1  = entry - range_width * 1.0
        tp2  = entry - range_width * 2.0
        tp3  = entry - range_width * 3.0
    return stop, tp1, tp2, tp3


def core_signal(df_1h, signal, df_4h=None):
    """
    Единая проверка входа. df_4h опционален (None в бэктесте).
    Возвращает True/False.
    """
    if len(df_1h) < 50:
        return False

    last = df_1h.iloc[-1]
    adx  = last['adx'] if not pd.isna(last['adx']) else 0

    if adx < ADX_MIN:                                return False
    if pd.isna(last['atr']) or last['atr'] <= 0:     return False
    if pd.isna(last['rsi']):                          return False

    # Базовые условия (RSI на откате)
    if not entry_conditions(df_1h, signal):          return False

    # Supertrend в сторону тренда
    if not supertrend_ok(df_1h, signal):             return False

    # MACD разворот в сторону сигнала
    if not macd_confirms(df_1h, signal):             return False

    # Не входим на растянутой цене
    if is_overextended(df_1h, signal):               return False

    # Не входим на кульминации объёма
    if detect_volume_climax(df_1h):                  return False

    # Главное условие — должен быть ОТКАТ (вход дёшево)
    has_pullback, _ = detect_pullback(df_1h, signal)
    if not has_pullback:                              return False

    # MTF подтверждение 4h (только в лайве)
    if df_4h is not None:
        l4 = df_4h.iloc[-1]
        if signal == 'LONG'  and not (l4['ema9'] > l4['ema21'] and l4['close'] > l4['ema50']):
            return False
        if signal == 'SHORT' and not (l4['ema9'] < l4['ema21'] and l4['close'] < l4['ema50']):
            return False

    return True


# ══════════════════════════════════════════════════════════════════
# LIVE SIGNAL
# ══════════════════════════════════════════════════════════════════
def _generate_momentum_signal(symbol, df_1h):
    """
    Live-версия momentum: входим в момент перехода ADX+EMA-тренда в true
    (см. core_signal_momentum). Не зависит от detect_regime — направление
    уже закодировано в самом условии. Уровни — те же, что в бэктесте
    (backtest_levels с STRATEGY_MODE='momentum': широкий стоп + время-выход).
    """
    signal = None
    if core_signal_momentum(df_1h, 'LONG'):
        signal = 'LONG'
    elif core_signal_momentum(df_1h, 'SHORT'):
        signal = 'SHORT'
    if not signal:
        return None

    if not btc_allows(symbol, signal):
        return None

    last    = df_1h.iloc[-1]
    entry   = last['close']
    atr_val = last['atr']
    atr_pct = atr_val / entry if entry > 0 else 0
    adx_val = last['adx'] if not pd.isna(last['adx']) else 0

    stop, tp1, tp2, tp3 = backtest_levels(signal, entry, atr_val, adx_val, atr_pct, df_1h)
    pos_size = volatility_position_size(entry, stop, atr_pct)
    if pos_size <= 0:
        return None

    score = min(SCORE_MAX, int(adx_val))  # прокси силы сигнала для сортировки в сканере

    print(f"💎 {symbol}: {signal} | MOMENTUM | ADX={adx_val:.0f} | {pos_size:.0f}$")

    return {
        'symbol': symbol, 'signal': signal, 'score': score, 'regime': 'MOMENTUM',
        'entry': entry, 'stop': stop, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
        'chandelier_stop': stop, 'position_size': pos_size,
        'last': last, 'last_1h': last, 'df': df_1h,
        'entry_reasons': [
            f'Momentum: ADX {adx_val:.0f} (растёт), переход в тренд',
            f'EMA-стек по сигналу: ✓',
            f'Позиция: {pos_size:.0f}$ (volatility-adj)',
            f'Выход по времени (~36ч) — широкий защитный стоп {stop:.4f}',
            f'BTC: {get_btc_regime()}',
        ],
    }


def generate_nfi_signal(symbol):
    if is_in_cooldown(symbol):  return None
    if not daily_loss_ok():     return None

    data = fetch_data_cached(symbol)
    if not data:
        return None

    df_4h = build_features(data['4h'])
    df_1h = build_features(data['1h'])

    try:
        df_1h = calc_supertrend(df_1h)
    except Exception:
        pass

    if STRATEGY_MODE == "momentum":
        return _generate_momentum_signal(symbol, df_1h)

    regime, adx_1h = detect_regime(df_1h)
    if regime in ('FLAT', 'CHOP'):
        return None

    # Определяем направление по режиму
    signal = None
    if regime == 'UPTREND'   and core_signal(df_1h, 'LONG',  df_4h):  signal = 'LONG'
    elif regime == 'DOWNTREND' and core_signal(df_1h, 'SHORT', df_4h): signal = 'SHORT'
    if not signal:
        return None

    if not btc_allows(symbol, signal):
        return None

    score = calc_score(df_1h, regime, signal)
    if score < SCORE_MIN:
        print(f"  ⛔ {symbol}: score={score} < {SCORE_MIN}")
        return None

    last    = df_1h.iloc[-1]
    entry   = last['close']
    atr_val = last['atr']
    atr_pct = atr_val / entry if entry > 0 else 0
    adx_val = last['adx'] if not pd.isna(last['adx']) else 0

    sl_m, tp1_m, tp2_m, tp3_m = get_mults(adx_val, atr_pct)
    stop, tp1, tp2, tp3 = calc_levels(signal, entry, atr_val, sl_m, tp1_m, tp2_m, tp3_m)
    pos_size = volatility_position_size(entry, stop, atr_pct)
    if pos_size <= 0:
        return None

    _, pb = detect_pullback(df_1h, signal)
    _, st = detect_structure(df_1h, signal)
    long_ce, short_ce = calc_chandelier_exit(df_1h)
    chandelier_stop = float(long_ce.iloc[-1]) if signal == 'LONG' else float(short_ce.iloc[-1])

    print(f"💎 {symbol}: {signal} | {regime} | ADX={adx_val:.0f} | score={score}/{SCORE_MAX} | {pos_size:.0f}$")

    return {
        'symbol': symbol, 'signal': signal, 'score': score, 'regime': regime,
        'entry': entry, 'stop': stop, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
        'chandelier_stop': chandelier_stop, 'position_size': pos_size,
        'last': last, 'last_1h': last, 'df': df_1h,
        'entry_reasons': [
            f'Режим: {regime} | ADX {adx_val:.0f}',
            f'Вход на откате к EMA (RSI {last["rsi"]:.0f})',
            f'Supertrend: {"бычий ✓" if signal == "LONG" else "медвежий ✓"}',
            f'MACD разворот: ✓',
            f'Структура: {"✓" if st > 0 else "—"} | Score: {score}/{SCORE_MAX}',
            f'Позиция: {pos_size:.0f}$ (volatility-adj)',
            f'R:R ≈ 1:2 (SL {sl_m:.1f} ATR / TP2 {tp2_m:.1f} ATR)',
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


# ══════════════════════════════════════════════════════════════════
# BACKTEST INTERFACE — та же логика через core_signal
# ══════════════════════════════════════════════════════════════════
def build_nfi_features(df):
    """Добавляет Supertrend (build_features уже вызван в main.py)."""
    try:
        return calc_supertrend(df)
    except Exception:
        return df


def _momentum_condition(row, signal):
    adx = row['adx'] if not pd.isna(row['adx']) else 0
    if pd.isna(row['atr']) or row['atr'] <= 0 or adx < ADX_MIN:
        return False
    if signal == 'LONG':
        return bool(row['ema9'] > row['ema21'] and row['close'] > row['ema50'])
    return bool(row['ema9'] < row['ema21'] and row['close'] < row['ema50'])


def core_signal_momentum(df, signal):
    """
    По результатам forward-return аудита: ADX>=22 + EMA-стек в сторону сигнала —
    статистически значимый continuation-сигнал, растущий на горизонте 6-24ч.
    ВАЖНО: условие персистентно (держится много баров подряд внутри тренда),
    поэтому входим только в момент ПЕРЕХОДА false->true (начало тренда),
    а не на каждом баре, где оно истинно — иначе плодим избыточные пересдводы.

    Доп. фильтр чопа: ADX должен РАСТИ последние 3 свечи (не просто быть выше
    порога) — отсекает ложные старты, когда ADX дёргается около границы 22
    в боковике, а не разворачивается в настоящий тренд.
    """
    if len(df) < 5:
        return False
    now_true  = _momentum_condition(df.iloc[-1], signal)
    prev_true = _momentum_condition(df.iloc[-2], signal)
    if not (now_true and not prev_true):
        return False

    adx_now  = df['adx'].iloc[-1]
    adx_3ago = df['adx'].iloc[-4]
    if pd.isna(adx_now) or pd.isna(adx_3ago):
        return False
    return bool(adx_now > adx_3ago)


def should_enter(df, signal):
    """
    Бэктест-вход. Переключается по STRATEGY_MODE.
    trend          — core_signal (вход на откате по тренду, нужен UPTREND/DOWNTREND)
    mean_reversion — core_signal_mean_reversion (вход на экстремуме во флэте)
    momentum       — core_signal_momentum (чистый ADX+EMA continuation, по аудиту)
    """
    if len(df) < 50:
        return False

    if STRATEGY_MODE == "mean_reversion":
        # MR не зависит от режима тренда — работает во флэте
        return core_signal_mean_reversion(df, signal, None)

    if STRATEGY_MODE == "breakout":
        # Breakout не зависит от режима тренда — работает на выходе из консолидации
        return core_signal_breakout(df, signal)

    if STRATEGY_MODE == "momentum":
        return core_signal_momentum(df, signal)

    # trend (по умолчанию)
    regime, _ = detect_regime(df)
    if regime == 'UPTREND'  and signal == 'LONG':
        return core_signal(df, 'LONG', None)
    if regime == 'DOWNTREND' and signal == 'SHORT':
        return core_signal(df, 'SHORT', None)
    return False


def backtest_levels(signal, entry, atr, adx, atr_pct, df):
    """
    Возвращает (stop, tp1, tp2, tp3) для бэктеста в зависимости от STRATEGY_MODE.
    Используется в main.py.
    """
    if STRATEGY_MODE == "mean_reversion":
        return mr_levels(signal, entry, atr, df)
    if STRATEGY_MODE == "breakout":
        return breakout_levels(signal, entry, atr, df)
    if STRATEGY_MODE == "momentum":
        # Время-ориентированный выход: держим до таймаута (~36ч, близко к
        # измеренному в аудите 24ч-горизонту edge). TP недостижимы специально —
        # стоп только катастрофический, чтобы не резать позицию раньше срока.
        sl = atr * 4.5
        far = atr * 999
        if signal == 'LONG':
            return entry - sl, entry + far, entry + far, entry + far
        return entry + sl, entry - far, entry - far, entry - far
    sl_m, tp1_m, tp2_m, tp3_m = get_mults(adx, atr_pct)
    return calc_levels(signal, entry, atr, sl_m, tp1_m, tp2_m, tp3_m)