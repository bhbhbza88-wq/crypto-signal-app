"""Один тестовый outlook-пост в @nowicki_news (с графиком).

Usage:
  railway run -- python outlook_test_post.py
  railway run -- python outlook_test_post.py SOL
  railway run -- python outlook_test_post.py SOL analysis
  railway run -- python outlook_test_post.py SOL update
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
    args = [a.strip() for a in sys.argv[1:] if a.strip()]
    symbol = None
    post_type = None
    for a in args:
        low = a.lower()
        if low in ("analysis", "update"):
            post_type = low
        else:
            symbol = a
    print(
        f"configured={market_outlook.is_configured()} "
        f"symbol={symbol or 'auto-top'} type={post_type or 'auto'}",
        flush=True,
    )
    ok = await market_outlook.publish_test(symbol, post_type=post_type)
    print("OK" if ok else "FAIL", flush=True)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
