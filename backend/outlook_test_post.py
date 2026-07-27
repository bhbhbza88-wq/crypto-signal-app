"""Один тестовый outlook-пост в @nowicki_news (с графиком).

Usage:
  railway run -- python outlook_test_post.py
  railway run -- python outlook_test_post.py SOL
"""
from __future__ import annotations

import asyncio
import os
import sys

# railway run тянет DATA_DIR=/data — локально пишем рядом со скриптом
if not os.path.isdir(os.getenv("DATA_DIR") or ""):
    os.environ["DATA_DIR"] = os.path.dirname(os.path.abspath(__file__)) or "."

import database as db
import market_outlook


async def main() -> None:
    db.init_db()
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or None
    print(f"configured={market_outlook.is_configured()} symbol={symbol or 'auto-top'}")
    ok = await market_outlook.publish_test(symbol)
    print("OK" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
