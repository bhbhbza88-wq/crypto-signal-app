"""
Общая точка открытия сигнала — используется ручным вводом админа,
TradingView-вебхуком и Telegram-агрегатором, чтобы валидация уровней и
правило "один символ — одна открытая позиция" не дублировались в каждом
источнике по отдельности.
"""

import json
from datetime import datetime

import database as db


def normalize_symbol(raw: str) -> str:
    """'BTCUSDT' / 'btc/usdt' -> 'BTC/USDT' (унифицированный формат ccxt, нужен tracker.py)."""
    s = raw.upper().strip()
    if '/' in s:
        return s
    if s.endswith('USDT'):
        return s[:-4] + '/USDT'
    return s


def open_signal(symbol, signal, entry, stop, tp1, tp2, tp3, trader_id, regime,
                reasons=None, score=None, candles_json=None):
    """Валидирует и открывает позицию через db.insert_trade_if_not_exists.

    Возвращает (symbol, None) при успехе или (None, причина) при отказе,
    где причина — 'invalid_levels' или 'already_open'. Не бросает исключений:
    вызывающая сторона (HTTP-хендлер или фоновый парсер) сама решает, что
    делать с отказом (409 для API, тихий пропуск + лог для фоновых источников).

    Проверка 'уже открыта' полагается на affected rows атомарной вставки
    (ON CONFLICT(symbol) DO NOTHING под _lock в database.py), а не на
    предварительный db.get_trade() — так закрывается TOCTOU-гонка между
    проверкой и записью при конкурентных вызовах на один symbol.
    """
    symbol = normalize_symbol(symbol)
    signal = signal.upper().strip()

    if signal == 'LONG':
        ok = stop < entry < tp1 < tp2 < tp3
    else:
        ok = stop > entry > tp1 > tp2 > tp3
    if not ok:
        return None, 'invalid_levels'

    if not candles_json:
        try:
            import data_layer
            candles_json = data_layer.fetch_candles_json(symbol)
        except Exception:
            candles_json = None

    trade = {
        "signal": signal,
        "entry": entry,
        "stop": stop,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "score": score,
        "regime": regime,
        "opened_at": datetime.now().isoformat(),
        "candles_json": candles_json,
        "entry_reasons_json": json.dumps(reasons or [], ensure_ascii=False),
        "trader_id": trader_id,
    }
    rowcount = db.insert_trade_if_not_exists(symbol, trade)
    if rowcount == 0:
        return None, 'already_open'
    return symbol, None
