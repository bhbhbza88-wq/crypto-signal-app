"""
Trade Tracker — мониторинг открытых сделок: TP1/TP2/TP3, стоп, трейлинг.
Перенесено из check_trades() бота. send_message() заменён на запись событий в БД.
"""

import pandas as pd

import database as db
from data_layer import fetch_data_cached, build_features, fetch_ticker


def pnl_pct(signal, entry, price):
    if not entry:
        return 0.0
    return ((price - entry) / entry * 100) if signal == 'LONG' else ((entry - price) / entry * 100)


def _hit(signal, price, level, kind):
    if signal == 'LONG':
        return price >= level if kind == 'tp' else price <= level
    return price <= level if kind == 'tp' else price >= level


def calc_trailing_stop(signal, price, atr, current_stop):
    if signal == 'LONG':
        new_stop = price - atr * 0.8
        return max(new_stop, current_stop)
    else:
        new_stop = price + atr * 0.8
        return min(new_stop, current_stop)


def check_potential_loss(symbol, signal, entry, price):
    pnl = pnl_pct(signal, entry, price)
    if pnl > 0.3 or abs(price - entry) / entry >= 0.015:
        return False, [], 0
    data = fetch_data_cached(symbol)
    if not data:
        return False, [], 0
    df = build_features(data['30m'])
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
    df = build_features(data['30m'])
    last = df.iloc[-1]
    rsi = last['rsi']
    adx = last['adx'] if not pd.isna(last['adx']) else 0
    pts, lines = 0, []
    if signal == 'LONG':
        if rsi < 60:
            pts += 2; lines.append(f"RSI {rsi:.0f} — потенциал есть")
        elif rsi < 70:
            pts += 1; lines.append(f"RSI {rsi:.0f} — умеренно")
        else:
            pts -= 1; lines.append(f"RSI {rsi:.0f} — перекуплен")
    else:
        if rsi > 40:
            pts += 2; lines.append(f"RSI {rsi:.0f} — потенциал есть")
        elif rsi > 30:
            pts += 1; lines.append(f"RSI {rsi:.0f} — умеренно")
        else:
            pts -= 1; lines.append(f"RSI {rsi:.0f} — перепродан")
    if last['volume'] > last['vol_avg'] and last['vol_trend'] > 0.9:
        pts += 2; lines.append("Объём держится")
    elif last['volume'] > last['vol_avg']:
        pts += 1; lines.append("Объём умеренный")
    else:
        pts -= 1; lines.append("Объём слабеет")
    ema_ok = last['ema9'] > last['ema21'] if signal == 'LONG' else last['ema9'] < last['ema21']
    if ema_ok:
        pts += 1; lines.append("EMA импульс сохраняется")
    else:
        pts -= 1; lines.append("EMA пересеклись")
    if adx > 25:
        pts += 1; lines.append(f"ADX {adx:.0f} — тренд силён")
    elif adx < 15:
        pts -= 1; lines.append(f"ADX {adx:.0f} — тренд слабеет")
    rec = ("Тянем до TP2 — потенциал есть" if pts >= 5 else
           "Можно тянуть до TP2, но осторожно" if pts >= 3 else
           "Лучше закрыть остаток здесь")
    return '\n'.join(lines), rec


def analyze_tp2(symbol, signal):
    data = fetch_data_cached(symbol)
    if not data:
        return "Фиксируем на TP2"
    df = build_features(data['30m'])
    last = df.iloc[-1]
    rsi = last['rsi']
    adx = last['adx'] if not pd.isna(last['adx']) else 0
    pts = 0
    if signal == 'LONG':
        pts += 2 if rsi < 65 else (1 if rsi < 75 else 0)
    else:
        pts += 2 if rsi > 35 else (1 if rsi > 25 else 0)
    if last['volume'] > last['vol_avg']:
        pts += 2
    ema_ok = last['ema9'] > last['ema21'] if signal == 'LONG' else last['ema9'] < last['ema21']
    if ema_ok:
        pts += 1
    if adx > 30:
        pts += 2
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
            price = ticker['last']
            signal = trade['signal']
            entry = trade['entry']
            stop = trade['stop']
            tp1, tp2, tp3 = trade['tp1'], trade['tp2'], trade['tp3']
            pnl = pnl_pct(signal, entry, price)
            tp1_hit = bool(trade.get('tp1_hit'))

            # ── Потеря потенциала (только до TP1) ──────
            if not tp1_hit and not trade.get('potential_warned'):
                lost, lines, _ = check_potential_loss(symbol, signal, entry, price)
                if lost:
                    trade['potential_warned'] = True
                    db.upsert_trade(symbol, trade)
                    db.add_event(symbol, 'potential',
                                 f"Закрыто по потере потенциала ({pnl:+.1f}%): " + ", ".join(lines))
                    db.add_to_history(symbol, signal, entry, 'potential', pnl)
                    db.remove_trade(symbol)
                    continue

            # ── Трейлинг стоп на 50% пути до TP1 ────────
            # Когда цена прошла половину пути entry→TP1,
            # подтягиваем стоп в небольшой плюс (+0.3% от входа)
            # чтобы не закрываться в б/у или минус
            if not tp1_hit and not trade.get('be_hit'):
                if signal == 'LONG':
                    progress = (price - entry) / (tp1 - entry) if (tp1 - entry) > 0 else 0
                    if progress >= 0.5:
                        new_stop = entry * 1.003  # стоп +0.3% от входа
                        if new_stop > trade['stop']:
                            trade['stop'] = new_stop
                            trade['be_hit'] = True
                            db.upsert_trade(symbol, trade)
                            db.add_event(symbol, 'trail',
                                         f"Стоп подтянут в плюс (+0.3%) — цена прошла 50% до TP1 ({pnl:+.1f}%)")
                else:  # SHORT
                    progress = (entry - price) / (entry - tp1) if (entry - tp1) > 0 else 0
                    if progress >= 0.5:
                        new_stop = entry * 0.997  # стоп -0.3% от входа
                        if new_stop < trade['stop']:
                            trade['stop'] = new_stop
                            trade['be_hit'] = True
                            db.upsert_trade(symbol, trade)
                            db.add_event(symbol, 'trail',
                                         f"Стоп подтянут в плюс (+0.3%) — цена прошла 50% до TP1 ({pnl:+.1f}%)")

            # ── Стоп ─────────────────────────────────────
            if _hit(signal, price, stop, 'sl'):
                result = 'be' if trade.get('be_hit') else 'sl'
                db.add_event(symbol, result, f"{'Безубыток' if result=='be' else 'Стоп'} ({pnl:+.1f}%)")
                db.add_to_history(symbol, signal, entry, result, pnl)
                db.remove_trade(symbol)
                continue

            # ── TP1 — фиксируем 50%, стоп в б/у ─────────
            if not tp1_hit and _hit(signal, price, tp1, 'tp'):
                trade['tp1_hit'] = True
                trade['be_hit'] = True
                trade['stop'] = entry
                pnl_tp1 = pnl_pct(signal, entry, tp1)
                analysis, rec = analyze_tp1(symbol, signal)
                db.add_event(symbol, 'tp1', f"TP1 достигнут (+{pnl_tp1:.1f}%). {rec}")
                db.add_to_history(symbol, signal, entry, 'tp1', pnl_tp1)
                db.upsert_trade(symbol, trade)

            # ── Trailing stop после TP1 ──────────────────
            if trade.get('tp1_hit'):
                data = fetch_data_cached(symbol)
                if data:
                    df_trail = build_features(data['30m'])
                    atr_now = df_trail.iloc[-1]['atr']
                    if not pd.isna(atr_now) and atr_now > 0:
                        new_stop = calc_trailing_stop(signal, price, atr_now, trade['stop'])
                        if abs(new_stop - trade['stop']) / (trade['stop'] + 1e-10) > 0.003:
                            trade['stop'] = new_stop
                            db.upsert_trade(symbol, trade)

            # ── TP2 ───────────────────────────────────────
            if not trade.get('tp2_hit') and _hit(signal, price, tp2, 'tp'):
                trade['tp2_hit'] = True
                pnl_tp2 = pnl_pct(signal, entry, tp2)
                rec2 = analyze_tp2(symbol, signal)
                db.add_event(symbol, 'tp2', f"TP2 достигнут (+{pnl_tp2:.1f}%). {rec2}")
                db.upsert_trade(symbol, trade)

            # ── TP3 — закрываем всё ──────────────────────
            if _hit(signal, price, tp3, 'tp'):
                pnl_tp3 = pnl_pct(signal, entry, tp3)
                db.add_event(symbol, 'tp3', f"TP3 достигнут, сделка завершена (+{pnl_tp3:.1f}%)")
                db.add_to_history(symbol, signal, entry, 'tp3', pnl_tp3)
                db.remove_trade(symbol)
                continue

        except Exception as e:
            print(f"Ошибка трекинга {symbol}: {e}")