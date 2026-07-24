"""Try attach to common CDP ports; list Chrome profiles; probe Edge."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ports = [9222, 9223, 9229, 9333, 0]
for port in (9222, 9223, 9229, 9333, 19222):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
            print("OPEN", port, r.read()[:100])
    except Exception as e:
        print("closed", port, type(e).__name__)

ud = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
print("chrome_ud", ud.exists(), ud)
if ud.exists():
    for p in ud.iterdir():
        if p.is_dir() and (p / "Preferences").exists():
            print(" profile", p.name)

edge = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Edge" / "User Data"
print("edge_ud", edge.exists())
if edge.exists():
    for p in edge.iterdir():
        if p.is_dir() and (p / "Preferences").exists():
            print(" edge_profile", p.name)
