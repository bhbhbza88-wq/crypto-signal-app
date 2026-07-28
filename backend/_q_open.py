#!/usr/bin/env python3
import sqlite3, json
from pathlib import Path

p = Path("trading_app.db")
c = sqlite3.connect(str(p))
c.row_factory = sqlite3.Row
n = c.execute("SELECT COUNT(*) FROM open_trades").fetchone()[0]
print("open_trades count:", n)
rows = c.execute("SELECT symbol,signal,entry,stop,tp1,tp2,tp3,score,opened_at,exchange,listed_on,entry_reasons_json FROM open_trades").fetchall()
for r in rows:
    d = dict(r)
    d.pop("entry_reasons_json", None)
    print(d)
    er = r["entry_reasons_json"]
    if er:
        try:
            print("reasons:", json.loads(er)[:5])
        except Exception:
            pass
