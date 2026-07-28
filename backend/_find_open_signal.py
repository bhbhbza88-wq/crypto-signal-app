#!/usr/bin/env python3
import sqlite3
from pathlib import Path

for p in [
    Path("trading_app.db"),
    Path("../trading_app.db"),
    Path("prod_trading_app.db"),
    Path("/tmp/trading_app.db"),
]:
    if not p.exists():
        continue
    print("===", p.resolve(), p.stat().st_size)
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("tables:", tables)
    for t in tables:
        if any(x in t.lower() for x in ("signal", "trade", "position", "open")):
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})").fetchall()]
            print(f"\n{t}: {cols}")
            try:
                rows = c.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 5").fetchall()
                for r in rows:
                    print(dict(r))
            except Exception as e:
                print("err", e)
