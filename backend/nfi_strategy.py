"""
NFI Strategy — упрощённая версия NostalgiaForInfinity логики.
EWO (Elliott Wave Oscillator) + Bollinger Bands + простой, но эффективный DCA.
"""

import os
import pandas as pd
import numpy as np
from data_layer import (
    fetch_data_cached, build_features, detect_regime,
    get_active_symbols, api_call, exchange,
)

# Параметры входа
EWO_BUY = 0.5           # Порог EWO для buy (EMA5 > EMA35 и значение > 2.0)
EWO_SELL = -0.5         # Порог EWO для sell
BB_LENGTH = 20          # Период Bollinger Bands
BB_STD = 2.0            # Стандартные отклонения
RSI_MIN_BUY = 25        # Минимальный RSI для входа в лонг
RSI_MAX_BUY = 75        # Максимальный RSI для входа в лонг
RSI_MIN_SELL = 30       # Минимальный RSI для входа в шорт
RSI_MAX_SELL = 70       # Максимальный RSI для входа в шорт

SL_BASE = 1.5
TP1_BASE = 3.0
TP2_BASE = 5.0

DEPOSIT = float(os.environ.get("DEPOSIT", "1000"))
RISK_PCT = float(os.environ.get("RISK_PCT", "1.5"))


def calc_ewo(df):
    """
    Elliott Wave Oscillator = EMA(5) - EMA(35), нормализовано на цену.
    Показывает силу и направление импульса.
    """
    if len(df) < 35:
        return pd.Series(0, index=df.index)
    ema5 = df['close'].ewm(span=5, adjust=False).mean()
    ema35 = df['close'].ewm(span=35, adjust=False).mean()
    ewo = ((ema5 - ema35) / df['close']) * 100
    return ewo


def calc_bollinger_bands(df, length=20, std=2.0):
    """Bollinger Bands для определения уровней входа (средняя и нижняя полоса)."""
    sma = df['close'].rolling(length).mean()
    std_dev = df['close'].rolling(length).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return sma, upper, lower


def is_dip_buy_signal(df, signal='LONG'):
    """
    Сигнал входа в лонг:
    - EWO растёт и выше порога (2.0) — волна импульса вверх
    - Цена выше нижней полосы BB (не переигрок)
    - RSI в зоне (30-70)
    """
    if len(df) < 50:
        return False
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Проверяем EWO
    ewo_last = last.get('ewo', 0)
    ewo_prev = prev.get('ewo', 0) if len(df) > 1 else 0
    
    if signal == 'LONG':
        # EWO растёт выше порога
        ewo_ok = ewo_last > EWO_BUY and ewo_last > ewo_prev
        
        # Цена выше нижней BB (не переигрок)
        bb_ok = last['close'] > last.get('bb_lower', last['close'] * 0.99)
        
        # RSI в нормальной зоне (не перекуплено, но растёт)
        rsi_ok = RSI_MIN_BUY < last['rsi'] < RSI_MAX_BUY
        
        return ewo_ok and bb_ok and rsi_ok
    else:
        # SHORT: EWO падает ниже порога
        ewo_ok = ewo_last < EWO_SELL and ewo_last < ewo_prev
        bb_ok = last['close'] < last.get('bb_upper', last['close'] * 1.01)
        rsi_ok = RSI_MIN_SELL < last['rsi'] < RSI_MAX_SELL
        return ewo_ok and bb_ok and rsi_ok


def should_enter(df, signal):
    """Проверка полного набора условий для входа."""
    if len(df) < 50:
        return False
    
    # Торгуем ТОЛЬКО LONG — против тренда не входим
    if signal == 'SHORT':
        return False
    
    last = df.iloc[-1]
    
    # Цена выше EMA50 (бычий рынок, slope не проверяем)
    if last['close'] < last['ema50']:
        return False
    
    # Краткосрочный тренд: EMA9 > EMA21
    if last['ema9'] < last['ema21']:
        return False
    
    return is_dip_buy_signal(df, 'LONG')


def build_nfi_features(df):
    """Добавляет EWO и Bollinger Bands к датафрейму."""
    df = df.copy()
    
    # EWO
    df['ewo'] = calc_ewo(df)
    
    # Bollinger Bands
    bb_mid, bb_upper, bb_lower = calc_bollinger_bands(df, BB_LENGTH, BB_STD)
    df['bb_mid'] = bb_mid
    df['bb_upper'] = bb_upper
    df['bb_lower'] = bb_lower
    
    return df


def get_mults(atr_pct):
    """Динамические множители SL/TP в зависимости от волатильности."""
    sl, tp1, tp2 = SL_BASE, TP1_BASE, TP2_BASE
    if atr_pct > 0.008:
        sl *= 1.2
        tp1 *= 1.1
        tp2 *= 1.1
    elif atr_pct > 0.005:
        sl *= 1.05
    return round(sl, 3), round(tp1, 3), round(tp2, 3)


def calc_levels(signal, entry, atr, sl_m, tp1_m, tp2_m):
    """Расчёт уровней SL/TP на основе ATR."""
    d = atr * sl_m
    if signal == 'LONG':
        return (
            entry - d,                    # stop
            entry + atr * tp1_m,          # tp1
            entry + atr * tp2_m,          # tp2
        )
    return (
        entry + d,
        entry - atr * tp1_m,
        entry - atr * tp2_m,
    )


def calc_position_size(entry, stop):
    """Размер позиции на основе риска."""
    risk_usdt = DEPOSIT * RISK_PCT / 100
    sl_dist = abs(entry - stop)
    if sl_dist == 0:
        return 0.0
    return round(risk_usdt / sl_dist * entry, 2)


def generate_nfi_signal(symbol):
    """
    Генерирует сигнал на основе NFI-логики.
    Вход: EWO + BB + тренд + RSI.
    Простой, но эффективный.
    """
    data = fetch_data_cached(symbol)
    if not data:
        return None
    
    # Грузим и обогащаем данные
    df_1h = build_features(data['1h'])
    df_30m = build_features(data['30m'])
    df_30m = build_nfi_features(df_30m)
    
    last = df_30m.iloc[-1]
    
    # Базовые проверки
    if pd.isna(last['atr']) or last['atr'] <= 0:
        return None
    if pd.isna(last['rsi']):
        return None
    if pd.isna(last.get('ewo', 0)):
        return None
    
    # Определяем сигнал — только LONG по тренду
    signal = None
    if should_enter(df_30m, 'LONG'):
        signal = 'LONG'
    
    if not signal:
        return None
    
    # Расчёт уровней
    entry = last['close']
    atr = last['atr']
    atr_pct = atr / entry if entry > 0 else 0
    
    sl_m, tp1_m, tp2_m = get_mults(atr_pct)
    stop, tp1, tp2 = calc_levels(signal, entry, atr, sl_m, tp1_m, tp2_m)
    pos_size = calc_position_size(entry, stop)
    
    if pos_size <= 0:
        return None
    
    # Оценка качества (простой скоринг)
    score = 10  # базовая оценка
    ewo = last['ewo']
    
    if signal == 'LONG':
        if ewo > 5.0:
            score += 3
        elif ewo > 3.0:
            score += 2
        elif ewo > EWO_BUY:
            score += 1
    else:
        if abs(ewo) > 5.0:
            score += 3
        elif abs(ewo) > 3.0:
            score += 2
    
    # Проверяем волатильность
    if atr_pct > 0.01:
        score += 2
    elif atr_pct > 0.005:
        score += 1
    
    return {
        'symbol': symbol,
        'signal': signal,
        'score': min(score, 20),
        'entry': entry,
        'stop': stop,
        'tp1': tp1,
        'tp2': tp2,
        'position_size': pos_size,
        'last': last,
        'last_1h': df_1h.iloc[-1],
        'df': df_30m,
        'entry_reasons': [
            f'EWO сигнал: {ewo:.1f}',
            f'Цена на уровне {"между BB" if signal == "LONG" else "между BB"}',
            f'RSI в зоне: {last["rsi"]:.0f}',
            f'ATR: {atr:.4f} ({atr_pct*100:.2f}%)',
        ]
    }


def scan_for_nfi_signals():
    """
    Сканирует все пары и возвращает список всех найденных сигналов
    (отсортированных по score), или пустой список.
    """
    signals = []
    for symbol in get_active_symbols():
        sig = generate_nfi_signal(symbol)
        if sig:
            signals.append(sig)
    
    # Сортируем по score
    signals.sort(key=lambda x: x['score'], reverse=True)
    return signals