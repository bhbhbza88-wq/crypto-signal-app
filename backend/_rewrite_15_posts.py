#!/usr/bin/env python3
"""Rewrite last 15 outlook posts with new logic."""
import asyncio
import sys
import time

sys.stdout.reconfigure(line_buffering=True)

import market_outlook


async def main():
    print("Checking recent posts...", flush=True)
    recent = market_outlook._recent_posts()
    print(f"Total: {len(recent)} posts", flush=True)
    
    items = sorted(
        recent.items(),
        key=lambda kv: float((kv[1] or {}).get("ts") or 0),
        reverse=True
    )[:15]
    
    for sym, meta in items:
        age_h = (time.time() - float(meta.get("ts") or 0)) / 3600.0
        print(
            f"{sym}: {age_h:.1f}h {meta.get('bias')} "
            f"msg={meta.get('message_id')} "
            f"body={str(meta.get('body') or '')[:60]}...",
            flush=True,
        )
    
    print("\n--- Rewriting 15 posts with new logic ---", flush=True)
    result = await market_outlook.rewrite_and_edit_recent_posts(limit=15)
    
    print(
        f"\nResult: edited={result['edited']} "
        f"skipped={result['skipped']} failed={result['failed']}",
        flush=True,
    )
    
    for d in result.get("details", []):
        status = d.get("status")
        sym = d.get("symbol")
        if status == "ok":
            print(f"  ✓ {sym}: rewritten", flush=True)
        else:
            print(f"  ✗ {sym}: {status}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
