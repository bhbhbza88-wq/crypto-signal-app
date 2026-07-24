"""Complete Heleket merchant create: Continue → meta → extract UUID → Check → Submit."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
OUT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_final.json")
SHOT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_final.png")
META_OUT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_meta.txt")


def dump(page, label):
    body = ""
    try:
        body = page.inner_text("body")
    except Exception:
        pass
    try:
        page.screenshot(path=str(SHOT), full_page=True)
    except Exception:
        pass
    print(f"[{label}] {page.url}")
    print(f"[{label}] {body[:1500].replace(chr(10),' | ')}")
    return body


def click_text(page, *texts):
    for t in texts:
        for getter in (
            lambda t: page.get_by_role("button", name=re.compile(f"^{re.escape(t)}$", re.I)),
            lambda t: page.get_by_text(re.compile(f"^{re.escape(t)}$", re.I)),
            lambda t: page.locator(f"button:has-text('{t}')"),
        ):
            try:
                loc = getter(t)
                if loc.count():
                    loc.first.click(timeout=8000)
                    print("clicked", t)
                    return t
            except Exception as e:
                print("click fail", t, e)
    return None


def extract_uuid(text: str):
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", text, re.I)
    return m.group(1) if m else None


def extract_meta(html: str, body: str, uuid: str | None):
    m = re.search(r'name=["\']heleket["\']\s+content=["\']([^"\']+)["\']', html, re.I)
    if m:
        return m.group(1)
    m = re.search(r"content=[\"']([a-f0-9]{6,12})[\"']", html, re.I)
    if m:
        return m.group(1)
    # short code near heleket
    m = re.search(r"heleket[^\n]{0,80}?([a-f0-9]{8})", body, re.I)
    if m:
        return m.group(1)
    if uuid:
        return uuid.split("-")[0]
    codes = re.findall(r"\b([a-f0-9]{8})\b", body)
    return codes[0] if codes else None


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "heleket.com" in (pg.url or ""):
                page = pg
                break
        if not page:
            page = ctx.pages[0]

        dump(page, "start")

        # Ensure fields still filled
        try:
            page.locator("input[name='merchant_name'], input[placeholder*='название мерчанта' i]").first.fill("NOWICKI_3")
        except Exception:
            pass
        try:
            page.get_by_text("Вебсайт").click(timeout=3000)
        except Exception:
            pass
        try:
            page.locator("input[name='project_url'], input[placeholder*='URL' i]").first.fill("https://nowicki.trade")
        except Exception:
            pass
        try:
            page.locator("input[name='project_name'], input[placeholder*='проекта' i]").first.fill("NOWICKI")
        except Exception:
            pass

        # Click Continue
        clicked = click_text(page, "Продолжить", "Continue", "Next")
        if not clicked:
            # force JS click on red continue
            page.evaluate(
                """() => {
                const btns=[...document.querySelectorAll('button')];
                const b=btns.find(x=>/продолжить|continue/i.test(x.innerText||''));
                if(b){b.click(); return b.innerText;}
                return 'none';
            }"""
            )
            print("js continue")
        time.sleep(3)
        body = dump(page, "step2")

        uuid = extract_uuid(page.url + "\n" + body)
        html = page.content()
        if not uuid:
            uuid = extract_uuid(html)
        print("UUID", uuid)

        # Choose meta tag verification
        click_text(
            page,
            "Using a meta tag on the site",
            "Using a meta tag",
            "Meta tag",
            "meta tag",
            "Мета-тег",
            "мета-тег",
            "HTML-тег",
            "HTML meta",
        )
        # Also try radio/label containing meta
        try:
            page.locator("label:has-text('meta'), label:has-text('Meta'), label:has-text('мета'), label:has-text('Мета')").first.click(timeout=3000)
            print("clicked meta label")
        except Exception:
            pass
        try:
            page.evaluate(
                """() => {
                const els=[...document.querySelectorAll('label,button,div,span,p,li')];
                const el=els.find(e=>/meta\\s*-?\\s*tag|мета-?тег|html.?meta|name=[\"']heleket/i.test(e.innerText||''));
                if(el){el.click(); return (el.innerText||'').slice(0,80);} return 'no-meta';
            }"""
            )
        except Exception as e:
            print("meta js", e)
        time.sleep(2)
        body = dump(page, "after_meta_select")
        html = page.content()
        if not uuid:
            uuid = extract_uuid(page.url + "\n" + body + "\n" + html)
        meta = extract_meta(html, body, uuid)
        print("META", meta, "UUID", uuid)

        # Save interim so parent can update site even if check fails later
        META_OUT.write_text(f"uuid={uuid}\nmeta={meta}\nurl={page.url}\n", encoding="utf-8")
        OUT.write_text(
            json.dumps({"uuid": uuid, "meta": meta, "url": page.url, "body": body[:4000]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # If still on step1 somehow, stop
        if "create" in page.url and "Шаг 1" in body:
            print("STILL_STEP1")
            return 5

        print("DONE_PARTIAL")
        return 0 if uuid and meta else 4


if __name__ == "__main__":
    raise SystemExit(main())
