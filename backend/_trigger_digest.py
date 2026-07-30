#!/usr/bin/env python3
"""Trigger morning digest via Railway API."""
import os
import httpx

API_URL = os.getenv("RAILWAY_API_URL") or "https://crypto-signal-app-production.up.railway.app"

resp = httpx.post(f"{API_URL}/api/digest/trigger", json={"time_of_day": "morning"}, timeout=60.0)
print(resp.status_code)
print(resp.text)
