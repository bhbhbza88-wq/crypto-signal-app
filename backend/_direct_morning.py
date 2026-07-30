#!/usr/bin/env python3
"""Post morning digest directly via bot token (без Railway API)."""
import asyncio
import os
import sys

os.chdir(r"c:\Users\Dell\Desktop\crypto-signal-app\backend")
sys.path.insert(0, r"c:\Users\Dell\Desktop\crypto-signal-app\backend")

# Railway env vars
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "7726330699:AAHqKrAWmjsAq_rJFfvSqoZYqTJVlJHzQJc")
os.environ.setdefault("TELEGRAM_NEWS_TARGET_CHANNEL", "nowicki_news")
os.environ.setdefault("GEMINI_API_KEY", "AIzaSyD6bXmYbsC0YNbK9gm9j1xHO3gTj_VW-ow")
os.environ.setdefault("DATA_FEED_API_KEY", "sk-data-tTIFqM1hcVSgK2c5MrKQR9U7")

import market_digest

asyncio.run(market_digest.post_digest_now("morning"))
print("✅ Morning digest posted!", flush=True)
