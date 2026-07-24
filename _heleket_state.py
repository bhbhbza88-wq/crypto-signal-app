"""Relaunch Chrome CDP with existing profile and inspect Heleket login state."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# force utf-8 stdout
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
TARGET = "https://dash.heleket.com/business/merchants"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "heleket-cdp-profile")
OUT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_state.json")
SHOT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_state.png")


def cdp_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{CDP}/json/version", timeout=2) as r:
            r.read()
            return True
    except Exception:
        return False


def launch() -> None:
    os.makedirs(PROFILE, exist_ok=True)
    args = [
        CHROME,
        "--remote-debugging-port=9222",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        TARGET,
    ]
    print("launch", PROFILE)
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if cdp_ready():
            print("cdp ready")
            return
        time.sleep(0.5)
    raise SystemExit("cdp start fail")


def main() -> int:
    if not cdp_ready():
        launch()
    else:
        print("cdp already up")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "heleket.com" in (pg.url or ""):
                page = pg
                break
        if page is None:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("start", page.url)
        page.goto(TARGET, wait_until="domcontentloaded", timeout=90000)
        time.sleep(3)
        url = page.url
        title = page.title()
        body = ""
        try:
            body = page.inner_text("body")
        except Exception as e:
            print("body_err", e)
        clickables = []
        try:
            clickables = page.eval_on_selector_all(
                "button, a, [role=button]",
                "els => els.map(e => (e.innerText||e.textContent||'').trim()).filter(Boolean).slice(0,100)",
            )
        except Exception as e:
            print("click_err", e)
        try:
            page.screenshot(path=str(SHOT), full_page=True)
        except Exception as e:
            print("shot_err", e)
        data = {"url": url, "title": title, "body": body[:5000], "clickables": clickables}
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("URL", url)
        print("TITLE", title)
        print("BODY", body[:1200].replace("\n", " | "))
        print("CLICKABLES", json.dumps(clickables, ensure_ascii=False)[:1500])
        low = (url + " " + body).lower()
        if "login" in url.lower() or "accounts.google" in url.lower() or ("вход" in body.lower() and "create merchant" not in body.lower() and "создать" not in body.lower() and "merchant" not in body.lower()):
            print("STATUS NEED_LOGIN")
            return 3
        print("STATUS OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
