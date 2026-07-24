"""Launch Chrome with CDP (if needed), open Heleket merchants, report login/dashboard state."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
TARGET = "https://dash.heleket.com/business/merchants"
OUT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_cdp_result.json")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "heleket-cdp-profile")


def cdp_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{CDP}/json/version", timeout=2) as r:
            print("CDP ok:", r.read()[:120])
            return True
    except Exception as e:
        print("CDP miss:", e)
        return False


def launch_chrome() -> None:
    os.makedirs(PROFILE, exist_ok=True)
    args = [
        CHROME,
        "--remote-debugging-port=9222",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        TARGET,
    ]
    print("Launching:", args)
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(30):
        if cdp_ready():
            return
        time.sleep(0.5)
    raise SystemExit("Chrome CDP failed to start")


def looks_like_login(text: str, url: str) -> bool:
    u = url.lower()
    t = text.lower()
    if "login" in u or "sign-in" in u or "signin" in u or "auth" in u:
        return True
    markers = ("sign in", "log in", "войти", "password", "пароль")
    if any(m in t for m in markers) and "create merchant" not in t and "merchants" not in t:
        return True
    return False


def main() -> int:
    if not cdp_ready():
        launch_chrome()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("start_url:", page.url)
        try:
            page.goto(TARGET, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            print("goto err:", e)
        time.sleep(2.5)
        url = page.url
        title = page.title()
        try:
            body = page.inner_text("body")
        except Exception:
            body = ""
        shot = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_merchants.png")
        try:
            page.screenshot(path=str(shot), full_page=True)
        except Exception as e:
            print("screenshot err:", e)

        clickables = []
        try:
            clickables = page.eval_on_selector_all(
                "button, a, [role=button]",
                "els => els.map(e => (e.innerText||e.textContent||'').trim()).filter(Boolean).slice(0,100)",
            )
        except Exception as e:
            print("clickables err:", e)

        need_login = looks_like_login(body, url)
        result = {
            "url": url,
            "title": title,
            "need_login": need_login,
            "body_snippet": body[:2000],
            "clickables": clickables,
            "screenshot": str(shot),
        }
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RESULT need_login=", need_login)
        print("url=", url)
        print("title=", title)
        print("clickables=", json.dumps(clickables, ensure_ascii=False)[:1500])
        return 3 if need_login else 0


if __name__ == "__main__":
    raise SystemExit(main())
