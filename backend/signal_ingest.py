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


def open_signal(symbol, signal, entry, stop, tp1, tp2, tp3, trader_id, regime, reasons=None):
    """Валидирует и открывает позицию через db.upsert_trade.

    Возвращает (symbol, None) при успехе или (None, причина) при отказе,
    где причина — 'invalid_levels' или 'already_open'. Не бросает исключений:
    вызывающая сторона (HTTP-хендлер или фоновый парсер) сама решает, что
    делать с отказом (409 для API, тихий пропуск + лог для фоновых источников).
    """
    symbol = normalize_symbol(symbol)
    signal = signal.upper().strip()

    if db.get_trade(symbol):
        return None, 'already_open'

    if signal == 'LONG':
        ok = stop < entry < tp1 < tp2 < tp3
    else:
        ok = stop > entry > tp1 > tp2 > tp3
    if not ok:
        return None, 'invalid_levels'

    trade = {
        "signal": signal,
        "entry": entry,
        "stop": stop,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "score": None,
        "regime": regime,
        "opened_at": datetime.now().isoformat(),
        "entry_reasons_json": json.dumps(reasons or [], ensure_ascii=False),
        "trader_id": trader_id,
    }
    db.upsert_trade(symbol, trade)
    return symbol, None
