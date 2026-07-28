#!/usr/bin/env python3
import sqlite3, json
from pathlib import Path

for p in [
    Path("prod_trading_app.db"),
    Path("trading_app.db"),
    Path("../trading_app.db"),
]:
    if not p.exists():
        continue
    print("DB", p.resolve())
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    try:
        rows = c.execute(
            "SELECT * FROM open_trades WHERE symbol LIKE '%XRP%' LIMIT 3"
        ).fetchall()
        print("open_trades", len(rows))
        for r in rows:
            print(dict(r))
    except Exception as e:
        print("open_trades err", e)
    try:
        rows = c.execute(
            "SELECT id,symbol,signal,entry,tp1,tp2,tp3,sl,status FROM signals WHERE symbol LIKE '%XRP%' ORDER BY id DESC LIMIT 5"
        ).fetchall()
        print("signals", len(rows))
        for r in rows:
            print(dict(r))
    except Exception as e:
        print("signals err", e)
