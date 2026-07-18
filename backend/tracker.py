"""
Trade Tracker — TP1/TP2/TP3, стоп, Chandelier Exit trailing.
Новое: Chandelier Exit, cooldown после стопа, daily loss recording.
"""

import asyncio
import pandas as pd
from datetime import datetime
import database as db
import nfi_strategy
import telegram_bot
from data_layer import fetch_data_cached, build_features, fetch_ticker
from nfi_strategy import (
    set_cooldown, record_daily_loss,
    calc_chandelier_exit, calc_supertrend
)


def _notify_closed(symbol, signal, result, pnl):
    """check_trades() — синхронный код в фоновом потоке сканера, а
    notify_signal_closed — async (шлёт HTTP в Telegram) — поднимаем свой
    короткоживущий event loop, как уже делает scanner.py для notify_new_signal.
    Не должно ронять трекинг, если Telegram недоступен — только предупреждение."""
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(telegram_bot.notify_signal_closed(
            {"symbol": symbol, "signal": signal}, result, pnl))
        loop.close()
    except Exception as e:
        print(f"⚠️ Telegram (закрытие {symbol}): {e}")
    try:
        import chat_engage
        chat_engage.fire_close(symbol, signal, result, pnl)
    except Exception as e:
        print(f"⚠️ chat_engage (закрытие {symbol}): {e}")

# Выход по времени — должен совпадать с таймаутом бэктеста (36 свечей 1h).
# Для momentum это ОСНОВНОЙ механизм выхода (TP недостижимы), без него
# live расходится с бэктестом.
TIMEOUT_HOURS = 36

# Pre-TP1 trailing: при 70% прогресса до TP1 подтягиваем стоп не на
# фиксированный процент от Entry, а на PRE_TP1_TRAIL_LOCK_PCT (45%, середина
# диапазона 40-50%) от уже пройденного расстояния Entry->TP1 — фиксируем
# бОльшую часть движения вместо плоского буфера 0.3%, который не масштабировался
# под волатильность конкретной монеты/сигнала.
PRE_TP1_TRAIL_PROGRESS = 0.70
PRE_TP1_TRAIL_LOCK_PCT = 0.45


def pnl_pct(signal, entry, price):
    if not entry:
        return 0.0
    return ((price - entry) / entry * 100) if signal == 'LONG' else ((entry - price) / entry * 100)


def _hit(signal, price, level, kind):
    if signal == 'LONG':
        return price >= level if kind == 'tp' else price <= level
    return price <= level if kind == 'tp' else price >= level


def calc_chandelier_trailing(signal, df, current_stop):
    """
    Chandelier Exit trailing — двигаем стоп от максимума/минимума свечей.
    Лучше классического ATR: меньше ложных выбиваний.
    """
    try:
        long_ce, short_ce = calc_chandelier_exit(df, period=22, multiplier=3.0)
        if signal == 'LONG':
            new_stop = float(long_ce.iloc[-1])
            return max(new_stop, current_stop)
        else:
            new_stop = float(short_ce.iloc[-1])
            return min(new_stop, current_stop)
    except Exception:
        # Fallback на ATR trailing
        last = df.iloc[-1]
        atr  = last['atr']
        if pd.isna(atr) or atr == 0:
            return current_stop
        if signal == 'LONG':
            return max(last['close'] - atr * 0.8, current_stop)
        return min(last['close'] + atr * 0.8, current_stop)


def check_potential_loss(symbol, signal, entry, price):
    pnl = pnl_pct(signal, entry, price)
    if pnl > 0.3 or abs(price - entry) / entry >= 0.015:
        return False, [], 0
    data = fetch_data_cached(symbol)
    if not data:
        return False, [], 0
    df = build_features(data['1h'])
    last = df.iloc[-1]
    weak, lines = 0, []
    if last['volume'] < last['vol_avg']:
        weak += 1; lines.append("Объём упал")
    if last['vol_trend'] < 0.70:
        weak += 1; lines.append("Объём угасает")
    if signal == 'LONG':
        if last['ema9'] < last['ema21']:
            weak += 1; lines.append("EMA разворачиваются вниз")
        if last['rsi'] < 45:
            weak += 1; lines.append(f"RSI {last['rsi']:.0f}")
        if last['close'] < last['ema50']:
            weak += 1; lines.append("Цена ниже EMA50")
    else:
        if last['ema9'] > last['ema21']:
            weak += 1; lines.append("EMA разворачиваются вверх")
        if last['rsi'] > 55:
            weak += 1; lines.append(f"RSI {last['rsi']:.0f}")
        if last['close'] > last['ema50']:
            weak += 1; lines.append("Цена выше EMA50")
    return (weak >= 3), lines, weak


def analyze_tp1(symbol, signal):
    data = fetch_data_cached(symbol)
    if not data:
        return "Анализ недоступен", "Тянем дальше"
    df   = build_features(data['1h'])
    last = df.iloc[-1]
    rsi  = last['rsi']
    adx  = last['adx'] if not pd.isna(last['adx']) else 0
    pts, lines = 0, []
    if signal == 'LONG':
        if rsi < 60:   pts += 2; lines.append(f"RSI {rsi:.0f} — потенциал есть")
        elif rsi < 70: pts += 1; lines.append(f"RSI {rsi:.0f} — умеренно")
        else:          pts -= 1; lines.append(f"RSI {rsi:.0f} — перекуплен")
    else:
        if rsi > 40:   pts += 2; lines.append(f"RSI {rsi:.0f} — потенциал есть")
        elif rsi > 30: pts += 1; lines.append(f"RSI {rsi:.0f} — умеренно")
        else:          pts -= 1; lines.append(f"RSI {rsi:.0f} — перепродан")
    if last['volume'] > last['vol_avg'] and last['vol_trend'] > 0.9:
        pts += 2; lines.append("Объём держится")
    elif last['volume'] > last['vol_avg']:
        pts += 1; lines.append("Объём умеренный")
    else:
        pts -= 1; lines.append("Объём слабеет")
    ema_ok = last['ema9'] > last['ema21'] if signal == 'LONG' else last['ema9'] < last['ema21']
    if ema_ok: pts += 1; lines.append("EMA импульс сохраняется")
    else:      pts -= 1; lines.append("EMA пересеклись")
    if adx > 25:   pts += 1; lines.append(f"ADX {adx:.0f} — тренд силён")
    elif adx < 15: pts -= 1; lines.append(f"ADX {adx:.0f} — тренд слабеет")
    rec = ("Тянем до TP2 — потенциал есть" if pts >= 5 else
           "Можно тянуть до TP2, но осторожно" if pts >= 3 else
           "Лучше закрыть остаток здесь")
    return '\n'.join(lines), rec


def analyze_tp2(symbol, signal):
    data = fetch_data_cached(symbol)
    if not data:
        return "Фиксируем на TP2"
    df   = build_features(data['1h'])
    last = df.iloc[-1]
    rsi  = last['rsi']
    adx  = last['adx'] if not pd.isna(last['adx']) else 0
    pts  = 0
    if signal == 'LONG': pts += 2 if rsi < 65 else (1 if rsi < 75 else 0)
    else:                pts += 2 if rsi > 35 else (1 if rsi > 25 else 0)
    if last['volume'] > last['vol_avg']: pts += 2
    ema_ok = last['ema9'] > last['ema21'] if signal == 'LONG' else last['ema9'] < last['ema21']
    if ema_ok: pts += 1
    if adx > 30: pts += 2
    return "Держим до TP3 — потенциал есть!" if pts >= 5 else "Закрываем на TP2 — отличная сделка!"


def check_trades():
    open_trades = db.load_trades()
    if not open_trades:
        return

    for symbol, trade in open_trades.items():
        try:
            ticker = fetch_ticker(symbol)
            if not ticker or ticker.get('last') is None:
                continue
            price  = ticker['last']
            signal = trade['signal']
            entry  = trade['entry']
            stop   = trade['stop']
            tp1, tp2, tp3 = trade['tp1'], trade['tp2'], trade['tp3']
            pnl    = pnl_pct(signal, entry, price)
            tp1_hit = bool(trade.get('tp1_hit'))
            trader_id = trade.get('trader_id')

            # ── Потеря потенциала (только до TP1) ─────────────────
            # Для momentum отключено: TP1 недостижим (выход по времени/стопу),
            # этот механизм не моделируется в бэктесте momentum.
            mom_mode = nfi_strategy.STRATEGY_MODE == 'momentum'
            if not mom_mode and not tp1_hit and not trade.get('potential_warned'):
                lost, lines, _ = check_potential_loss(symbol, signal, entry, price)
                if lost:
                    trade['potential_warned'] = True
                    db.upsert_trade(symbol, trade)
                    db.add_event(symbol, 'potential',
                                 f"Закрыто по потере потенциала ({pnl:+.1f}%): " + ", ".join(lines))
                    record_daily_loss(pnl)
                    db.add_to_history(symbol, signal, entry, 'potential', pnl, trader_id)
                    db.remove_trade(symbol)
                    _notify_closed(symbol, signal, 'potential', pnl)
                    if pnl < -0.5:
                        set_cooldown(symbol)
                    continue

            # ── Pre-TP1 trailing (70% пути до TP1) ────────────────
            if not tp1_hit and not trade.get('pre_tp1_trail'):
                dist_total = abs(tp1 - entry)
                dist_done  = abs(price - entry)
                if dist_total > 0 and dist_done / dist_total >= PRE_TP1_TRAIL_PROGRESS:
                    lock_dist = dist_total * PRE_TP1_TRAIL_LOCK_PCT
                    if signal == 'LONG':
                        new_stop = entry + lock_dist
                        if new_stop > trade['stop']:
                            trade['stop'] = new_stop
                            trade['be_hit'] = True
                            trade['pre_tp1_trail'] = True
                            db.upsert_trade(symbol, trade)
                            db.add_event(symbol, 'trail',
                                         f"Стоп подтянут в +{pnl_pct(signal, entry, new_stop):.1f}% "
                                         f"({PRE_TP1_TRAIL_PROGRESS:.0%} до TP1)")
                    else:
                        new_stop = entry - lock_dist
                        if new_stop < trade['stop']:
                            trade['stop'] = new_stop
                            trade['be_hit'] = True
                            trade['pre_tp1_trail'] = True
                            db.upsert_trade(symbol, trade)
                            db.add_event(symbol, 'trail',
                                         f"Стоп подтянут в {pnl_pct(signal, entry, new_stop):+.1f}% "
                                         f"({PRE_TP1_TRAIL_PROGRESS:.0%} до TP1)")

            # ── Стоп ──────────────────────────────────────────────
            if _hit(signal, price, stop, 'sl'):
                result = 'be' if trade.get('be_hit') else 'sl'
                db.add_event(symbol, result, f"{'Безубыток' if result=='be' else 'Стоп'} ({pnl:+.1f}%)")
                record_daily_loss(pnl)
                db.add_to_history(symbol, signal, entry, result, pnl, trader_id)
                db.remove_trade(symbol)
                _notify_closed(symbol, signal, result, pnl)
                if result == 'sl':
                    set_cooldown(symbol)   # cooldown только после реального стопа
                continue

            # ── Таймаут по времени (как в бэктесте) ───────────────
            opened_at = trade.get('opened_at')
            if opened_at:
                try:
                    hours_open = (datetime.now() - datetime.fromisoformat(opened_at)).total_seconds() / 3600
                except (ValueError, TypeError):
                    hours_open = 0
                if hours_open >= TIMEOUT_HOURS:
                    db.add_event(symbol, 'timeout', f"Закрыто по времени ({TIMEOUT_HOURS}ч, {pnl:+.1f}%)")
                    record_daily_loss(pnl)
                    db.add_to_history(symbol, signal, entry, 'timeout', pnl, trader_id)
                    db.remove_trade(symbol)
                    _notify_closed(symbol, signal, 'timeout', pnl)
                    continue

            # ── TP1 — фиксируем 50%, стоп в б/у ──────────────────
            if not tp1_hit and _hit(signal, price, tp1, 'tp'):
                trade['tp1_hit'] = True
                trade['be_hit']  = True
                trade['stop']    = entry
                pnl_tp1 = pnl_pct(signal, entry, tp1)
                _, rec  = analyze_tp1(symbol, signal)
                db.add_event(symbol, 'tp1', f"TP1 достигнут (+{pnl_tp1:.1f}%). {rec}")
                db.add_to_history(symbol, signal, entry, 'tp1', pnl_tp1, trader_id)
                db.upsert_trade(symbol, trade)

            # ── Chandelier Exit trailing после TP1 ────────────────
            if trade.get('tp1_hit'):
                data_cached = fetch_data_cached(symbol)
                if data_cached:
                    df_trail = build_features(data_cached['1h'])
                    new_stop = calc_chandelier_trailing(signal, df_trail, trade['stop'])
                    if abs(new_stop - trade['stop']) / (trade['stop'] + 1e-10) > 0.002:
                        trade['stop'] = new_stop
                        db.upsert_trade(symbol, trade)

            # ── TP2 ───────────────────────────────────────────────
            if not trade.get('tp2_hit') and _hit(signal, price, tp2, 'tp'):
                trade['tp2_hit'] = True
                pnl_tp2 = pnl_pct(signal, entry, tp2)
                rec2 = analyze_tp2(symbol, signal)
                db.add_event(symbol, 'tp2', f"TP2 достигнут (+{pnl_tp2:.1f}%). {rec2}")
                db.upsert_trade(symbol, trade)

            # ── TP3 — закрываем всё ───────────────────────────────
            if _hit(signal, price, tp3, 'tp'):
                pnl_tp3 = pnl_pct(signal, entry, tp3)
                db.add_event(symbol, 'tp3', f"TP3 достигнут (+{pnl_tp3:.1f}%)")
                db.add_to_history(symbol, signal, entry, 'tp3', pnl_tp3, trader_id)
                db.remove_trade(symbol)
                _notify_closed(symbol, signal, 'tp3', pnl_tp3)
                continue

        except Exception as e:
            print(f"Ошибка трекинга {symbol}: {e}")