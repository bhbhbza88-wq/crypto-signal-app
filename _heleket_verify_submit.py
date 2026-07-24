"""Wait until live meta matches, then Check + Submit moderation in Heleket CDP."""
from __future__ import annotations

import re
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

EXPECTED = "03719a7e"
UUID = "03719a7e-a2fc-4421-93c6-7e2df9ad8b22"
URL = f"https://dash.heleket.com/business/create?merchant_uuid={UUID}"
SHOT = r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_moderation.png"


def live_meta() -> str | None:
    req = urllib.request.Request("https://nowicki.trade/", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        t = r.read().decode("utf-8", "replace")
    m = re.search(r'name=["\']heleket["\']\s+content=["\']([^"\']+)["\']', t)
    return m.group(1) if m else None


def main() -> int:
    meta = None
    for i in range(40):
        try:
            meta = live_meta()
        except Exception as e:
            print("fetch err", e)
            meta = None
        print(f"live_meta[{i}]={meta}")
        if meta == EXPECTED:
            break
        time.sleep(8)
    if meta != EXPECTED:
        print("META_NOT_LIVE", meta)
        return 2

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = next((x for x in ctx.pages if "heleket" in x.url), ctx.pages[0])
        if UUID not in page.url:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(1)

        # Click Check / Проверить
        clicked = page.evaluate(
            """() => {
              const btns=[...document.querySelectorAll('button,a,[role=button]')];
              const b=btns.find(x=>/проверить|check/i.test((x.innerText||'').trim()));
              if(!b) return 'no-check';
              b.click();
              return (b.innerText||'').trim();
            }"""
        )
        print("check_click", clicked)
        time.sleep(5)
        body = page.inner_text("body")
        print("after_check", body[:1200].replace("\n", " | "))

        confirmed = bool(re.search(r"confirm|подтвержд|verified|успеш", body, re.I))
        print("confirmed_hint", confirmed)

        # Submit for moderation
        clicked2 = page.evaluate(
            """() => {
              const btns=[...document.querySelectorAll('button,a,[role=button]')];
              const b=btns.find(x=>/отправить на модерацию|submit for moderation|moderation/i.test((x.innerText||'').trim()));
              if(!b) return 'no-submit';
              b.click();
              return (b.innerText||'').trim();
            }"""
        )
        print("submit_click", clicked2)
        time.sleep(4)
        body2 = page.inner_text("body")
        print("after_submit", body2[:1500].replace("\n", " | "))
        page.screenshot(path=SHOT, full_page=True)

        status = "unknown"
        if re.search(r"moderation|модерац", body2, re.I):
            status = "moderation"
        print("STATUS", status)
        print("URL", page.url)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
