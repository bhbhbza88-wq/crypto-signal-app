"""
Общая точка открытия сигнала — используется ручным вводом админа,
TradingView-вебхуком и Telegram-агрегатором, чтобы валидация уровней и
правило "один символ — одна открытая позиция" не дублировались в каждом
источнике по отдельности.
"""

import json
import os
from datetime import datetime, timedelta

import database as db

# Если на том же символе уже есть позиция от ДРУГОГО источника старше N часов —
# закрываем старую как superseded и открываем новую. Та же монета от того же
# trader_id всегда already_open.
REOPEN_AFTER_HOURS = float(os.getenv("SIGNAL_REOPEN_AFTER_HOURS", "6") or "6")


def normalize_symbol(raw: str) -> str:
    """'BTCUSDT' / 'btc/usdt' -> 'BTC/USDT' (унифицированный формат ccxt, нужен tracker.py)."""
    s = raw.upper().strip()
    if '/' in s:
        return s
    if s.endswith('USDT'):
        return s[:-4] + '/USDT'
    return s


def open_signal(symbol, signal, entry, stop, tp1, tp2, tp3, trader_id, regime,
                reasons=None, score=None, candles_json=None, exchange='bybit',
                listed_on=None, exit_mode: str | None = None):
    """Валидирует и открывает позицию через db.insert_trade_if_not_exists.

    Возвращает (symbol, None) при успехе или (None, причина) при отказе,
    где причина — 'invalid_levels' или 'already_open'.

    exit_mode:
      - 'ladder' (default) — классика TP1/TP2/TP3
      - 'tp1_trail' — для агрегированных каналов: после TP1 только trailing + timeout
    """
    symbol = normalize_symbol(symbol)
    signal = signal.upper().strip()
    exit_mode = (exit_mode or ("tp1_trail" if regime == "telegram_aggregate" else "ladder")).strip()

    import data_layer
    listed = data_layer.parse_listed_on(listed_on) if listed_on else []
    if not listed:
        listed, preferred, _ = data_layer.probe_listings(symbol)
        if preferred:
            exchange = preferred
        elif not exchange:
            exchange = 'bybit'
    exchange = (exchange or 'bybit').lower().strip()
    if exchange not in ('bybit', 'binance', 'bitunix'):
        exchange = 'bybit'
    if not listed:
        listed = [exchange]
    listed_csv = ','.join(listed)

    # Для tp1_trail TP2/TP3 — мягкие ориентиры на график (не жёсткий exit).
    # Геометрию entry/stop/tp1 всё равно проверяем строго.
    if exit_mode == "tp1_trail":
        if signal == "LONG":
            ok = stop < entry < tp1
        else:
            ok = stop > entry > tp1
        # placeholder ladder для UI/совместимости схемы
        step = abs(tp1 - entry) or (entry * 0.01)
        if signal == "LONG":
            tp2 = tp2 if tp2 and tp2 > tp1 else tp1 + step
            tp3 = tp3 if tp3 and tp3 > tp2 else tp2 + step
        else:
            tp2 = tp2 if tp2 and tp2 < tp1 else tp1 - step
            tp3 = tp3 if tp3 and tp3 < tp2 else tp2 - step
    else:
        if signal == 'LONG':
            ok = stop < entry < tp1 < tp2 < tp3
        else:
            ok = stop > entry > tp1 > tp2 > tp3
    if not ok:
        return None, 'invalid_levels'

    existing = db.get_trade(symbol)
    if existing:
        err = _resolve_existing(symbol, existing, trader_id)
        if err:
            return None, err

    if not candles_json:
        try:
            candles_json = data_layer.fetch_candles_json(symbol, exchange_id=exchange)
        except Exception:
            candles_json = None

    reasons_list = list(reasons or [])
    if exit_mode == "tp1_trail":
        reasons_list.append("Exit mode: TP1 + trailing/timeout (без жёстких TP2/TP3 канала)")

    trade = {
        "signal": signal,
        "entry": entry,
        "stop": stop,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "score": score,
        "regime": regime,
        "opened_at": datetime.now().isoformat(),
        "candles_json": candles_json,
        "entry_reasons_json": json.dumps(reasons_list, ensure_ascii=False),
        "trader_id": trader_id,
        "exchange": exchange,
        "listed_on": listed_csv,
        "exit_mode": exit_mode,
    }
    rowcount = db.insert_trade_if_not_exists(symbol, trade)
    if rowcount == 0:
        return None, 'already_open'
    return symbol, None


def _resolve_existing(symbol: str, existing: dict, trader_id) -> str | None:
    """None = можно открывать (старую закрыли); 'already_open' = отказ."""
    same_trader = (
        trader_id is not None
        and existing.get("trader_id") is not None
        and int(existing.get("trader_id")) == int(trader_id)
    )
    if same_trader:
        return "already_open"

    opened_at = existing.get("opened_at")
    age_h = 0.0
    if opened_at:
        try:
            age_h = (datetime.now() - datetime.fromisoformat(opened_at)).total_seconds() / 3600
        except (ValueError, TypeError):
            age_h = 0.0

    if age_h < REOPEN_AFTER_HOURS:
        return "already_open"

    # Разный источник + позиция старше окна — supersede
    try:
        import tracker
        entry = existing["entry"]
        side = existing["signal"]
        ex = existing.get("exchange") or "bybit"
        import data_layer
        ticker = data_layer.fetch_ticker(symbol, ex)
        price = float(ticker["last"]) if ticker and ticker.get("last") is not None else entry
        pnl = tracker.pnl_pct(side, entry, price)
        db.add_event(
            symbol, "superseded",
            f"Заменена новым сигналом другого источника (возраст {age_h:.1f}ч, PnL {pnl:+.1f}%)",
        )
        db.add_to_history(symbol, side, entry, "superseded", pnl, existing.get("trader_id"))
        db.remove_trade(symbol)
        print(f"[signal_ingest] {symbol} superseded (age {age_h:.1f}h, pnl {pnl:+.1f}%)")
    except Exception as e:
        print(f"[signal_ingest] supersede failed for {symbol}: {e}")
        return "already_open"
    return None
