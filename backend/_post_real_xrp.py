#!/usr/bin/env python3
"""Настоящий пост: XRP из prod DB + BingX AI + пересылка в news."""
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

# BingX + дешёвая AI
os.environ["OPEN_POS_AI"] = "1"
os.environ["OPEN_POS_STYLE"] = "bingx"
os.environ["OPENROUTER_MODEL_IMAGE_EDIT"] = "google/gemini-3.1-flash-lite-image"
os.environ["AUTO_FORWARD_TO_NEWS"] = "1"


async def main():
    import data_layer
    import telegram_bot

    # сброс дневного лимита — это «первый» настоящий пост
    telegram_bot._last_premium_message = None
    telegram_bot._last_forward_date = None

    db = Path("prod_trading_app.db")
    if not db.exists():
        raise SystemExit("нет prod_trading_app.db — скачай с Railway")

    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    row = c.execute("SELECT * FROM open_trades LIMIT 1").fetchone()
    if not row:
        raise SystemExit("open_trades пусто")
    r = dict(row)

    reasons = []
    try:
        reasons = json.loads(r.get("entry_reasons_json") or "[]")
    except Exception:
        pass

    signal = {
        "symbol": r["symbol"],
        "signal": r["signal"],
        "entry": float(r["entry"]),
        "stop": float(r["stop"]),
        "tp1": float(r["tp1"]),
        "tp2": float(r["tp2"]),
        "tp3": float(r["tp3"]),
        "score": float(r["score"] or 0),
        "exchange": r.get("exchange") or "bybit",
        "listed_on": r.get("listed_on") or "",
        "entry_reasons": reasons,
        "opened_at": r.get("opened_at"),
    }

    # live mark для точного PnL на карточке
    try:
        ticker = data_layer.fetch_ticker(signal["symbol"], "bybit")
        mark = float(ticker["last"]) if ticker and ticker.get("last") else None
    except Exception as e:
        print("[real] ticker err:", e)
        mark = None

    entry = signal["entry"]
    if mark and mark > 0:
        move = (mark - entry) / entry
        pnl = 12.0 * 15 * move
        roi = move * 15 * 100
        print(f"[real] {signal['symbol']} LONG entry={entry} mark={mark}")
        print(f"[real] move={move*100:.3f}% pnl={pnl:.4f}USDT roi={roi:.2f}% (15x, margin=12)")
    else:
        print(f"[real] {signal['symbol']} entry={entry} mark=UNKNOWN")

    print("[real] публикуем ТВХ (BingX AI flash-lite)...")
    await telegram_bot.notify_new_signal(signal)
    print("[real] готово (пост + попытка пересылки в news)")


if __name__ == "__main__":
    asyncio.run(main())
