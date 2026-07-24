"""Poll Heleket CDP until logged in (merchants dashboard), then create NOWICKI_3."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
OUT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_create_result.json")
SHOT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_create.png")
MERCHANTS = "https://dash.heleket.com/business/merchants"


def is_logged_in(url: str, body: str) -> bool:
    u = url.lower()
    if "login" in u or "accounts.google" in u:
        return False
    b = body.lower()
    markers = (
        "create merchant",
        "создать мерчант",
        "создать merchant",
        "merchants",
        "nowicki",
        "merchant settings",
        "мои проекты",
        "проекты",
    )
    # dashboard usually has create button or list
    if any(m in b for m in markers) and "войти" not in b[:200].lower():
        return True
    if "forgot password" in b or "забыли пароль" in b:
        return False
    if "войти" in body and "парол" in body:
        return False
    return False


def get_page(browser):
    ctx = browser.contexts[0]
    for pg in ctx.pages:
        if "heleket.com" in (pg.url or ""):
            return pg
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def dump(page, label):
    body = ""
    try:
        body = page.inner_text("body")
    except Exception:
        pass
    clickables = []
    try:
        clickables = page.eval_on_selector_all(
            "button, a, [role=button], input, label",
            "els => els.map(e => (e.innerText||e.textContent||e.getAttribute('placeholder')||e.value||'').trim()).filter(Boolean).slice(0,150)",
        )
    except Exception:
        pass
    try:
        page.screenshot(path=str(SHOT), full_page=True)
    except Exception:
        pass
    print(f"[{label}] url={page.url}")
    print(f"[{label}] body={body[:900].replace(chr(10),' | ')}")
    print(f"[{label}] clicks={json.dumps(clickables, ensure_ascii=False)[:1200]}")
    return body, clickables


def click_by_text(page, texts, timeout=5000):
    for t in texts:
        try:
            loc = page.get_by_role("button", name=re.compile(t, re.I))
            if loc.count():
                loc.first.click(timeout=timeout)
                return t
        except Exception:
            pass
        try:
            loc = page.get_by_text(re.compile(f"^{re.escape(t)}$", re.I))
            if loc.count():
                loc.first.click(timeout=timeout)
                return t
        except Exception:
            pass
        try:
            loc = page.locator(f"button:has-text('{t}'), a:has-text('{t}'), [role=button]:has-text('{t}')")
            if loc.count():
                loc.first.click(timeout=timeout)
                return t
        except Exception:
            pass
    return None


def fill_first(page, selectors, value):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count():
                loc.first.fill(value, timeout=5000)
                return sel
        except Exception:
            continue
    return None


def main() -> int:
    result = {"ok": False}
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        page = get_page(browser)

        # Poll up to ~75s for login
        logged = False
        for i in range(25):
            try:
                if "merchants" not in page.url and "heleket.com" in page.url:
                    page.goto(MERCHANTS, wait_until="domcontentloaded", timeout=60000)
                elif "login" in page.url or "accounts.google" in page.url:
                    pass
                else:
                    page.goto(MERCHANTS, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print("goto", e)
            time.sleep(3)
            body, clicks = dump(page, f"poll{i}")
            if is_logged_in(page.url, body):
                logged = True
                print("LOGGED IN")
                break
            print("still login, waiting...")

        if not logged:
            result["error"] = "NEED_LOGIN"
            result["url"] = page.url
            OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print("STATUS NEED_LOGIN")
            return 3

        # Create merchant flow
        time.sleep(1)
        body, clicks = dump(page, "dashboard")

        clicked = click_by_text(
            page,
            [
                "Create merchant",
                "Create Merchant",
                "Создать мерчант",
                "Создать Merchant",
                "Create",
                "Создать",
                "Add merchant",
                "Добавить",
            ],
        )
        print("clicked create:", clicked)
        time.sleep(2)
        dump(page, "after_create_click")

        # Fill merchant name
        name_candidates = ["NOWICKI_3", "NOWICKI_v3", "NOWICKI3"]
        name_used = None
        for name in name_candidates:
            filled = fill_first(
                page,
                [
                    "input[name*='name' i]",
                    "input[placeholder*='name' i]",
                    "input[placeholder*='название' i]",
                    "input[placeholder*='Name' i]",
                    "input[type='text']",
                ],
                name,
            )
            print("fill name", name, filled)
            name_used = name
            # Try submit create
            time.sleep(0.5)
            clicked2 = click_by_text(
                page,
                [
                    "Create merchant",
                    "Create",
                    "Создать мерчант",
                    "Создать",
                    "Continue",
                    "Next",
                    "Далее",
                    "Confirm",
                    "Подтвердить",
                ],
            )
            print("submit name click", clicked2)
            time.sleep(2)
            body, _ = dump(page, f"after_name_{name}")
            # If name taken, try next
            if any(x in body.lower() for x in ("already", "exists", "занят", "taken", "duplicate", "уже")):
                print("name taken", name)
                continue
            # Success heuristics: uuid in url or project form
            if re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", page.url, re.I):
                break
            if any(x in body.lower() for x in ("website", "project", "url", "сайт", "verify", "domain", "тип")):
                break

        # Select Website type if present
        click_by_text(page, ["Website", "Сайт", "Web site", "Web"])
        time.sleep(0.8)

        # Fill project URL / name
        fill_first(
            page,
            [
                "input[placeholder*='http' i]",
                "input[placeholder*='url' i]",
                "input[placeholder*='сайт' i]",
                "input[name*='url' i]",
                "input[type='url']",
            ],
            "https://nowicki.trade",
        )
        # project name fields - often second text input
        try:
            inputs = page.locator("input[type='text'], input:not([type]), input[type='url']")
            count = inputs.count()
            print("inputs count", count)
            for i in range(count):
                ph = (inputs.nth(i).get_attribute("placeholder") or "") + " " + (inputs.nth(i).get_attribute("name") or "")
                print(" input", i, ph)
                low = ph.lower()
                if "url" in low or "http" in low or "site" in low or "сайт" in low or "link" in low:
                    inputs.nth(i).fill("https://nowicki.trade")
                elif "project" in low or "проект" in low or "name" in low or "назван" in low:
                    # avoid overwriting merchant name if already set; set NOWICKI for project
                    try:
                        cur = inputs.nth(i).input_value()
                    except Exception:
                        cur = ""
                    if not cur or cur.startswith("NOWICKI_"):
                        if "merchant" not in low:
                            inputs.nth(i).fill("NOWICKI")
        except Exception as e:
            print("inputs err", e)

        # Explicit project name fill
        fill_first(
            page,
            [
                "input[placeholder*='project' i]",
                "input[placeholder*='проект' i]",
                "input[name*='project' i]",
            ],
            "NOWICKI",
        )

        click_by_text(
            page,
            [
                "Submit",
                "Continue",
                "Next",
                "Далее",
                "Сохранить",
                "Save",
                "Confirm",
                "Подтвердить",
                "Create",
                "Создать",
            ],
        )
        time.sleep(3)
        body, clicks = dump(page, "after_project")

        uuid_m = re.search(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            page.url + "\n" + body,
            re.I,
        )
        uuid = uuid_m.group(1) if uuid_m else None
        print("UUID", uuid)

        # Meta tag verification method
        click_by_text(
            page,
            [
                "meta tag",
                "Meta tag",
                "Using a meta tag",
                "meta-тег",
                "Meta-тег",
                "HTML meta",
                "мета",
            ],
        )
        time.sleep(1)
        body2, _ = dump(page, "meta_method")

        # Extract meta content value
        meta_content = None
        # Look for code/pre/snippets
        try:
            html = page.content()
            m = re.search(r'name=["\']heleket["\']\s+content=["\']([^"\']+)["\']', html, re.I)
            if m:
                meta_content = m.group(1)
            if not meta_content and uuid:
                meta_content = uuid.split("-")[0]
            # also look for short codes in body
            if not meta_content:
                codes = re.findall(r"\b([a-f0-9]{8})\b", body2, re.I)
                if codes:
                    meta_content = codes[0]
        except Exception as e:
            print("meta extract err", e)
            if uuid:
                meta_content = uuid.split("-")[0]

        result = {
            "ok": True,
            "url": page.url,
            "merchant_name": name_used,
            "uuid": uuid,
            "meta_content": meta_content,
            "body": body2[:3000],
            "clicks": clicks,
        }
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RESULT", json.dumps({k: result[k] for k in ("ok", "merchant_name", "uuid", "meta_content", "url")}, ensure_ascii=False))
        return 0 if uuid else 4


if __name__ == "__main__":
    raise SystemExit(main())
