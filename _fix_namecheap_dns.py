#!/usr/bin/env python3
"""Cancel unfinished ALIAS row; ensure www CNAME; verify page state."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

TARGET = "2uuatnpq.up.railway.app"
OUT = Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_dns_fix")
ADV = "https://ap.www.namecheap.com/domains/domaincontrolpanel/nowicki.trade/advancedns"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = next((x for x in ctx.pages if "namecheap" in x.url), ctx.new_page())
        page.bring_to_front()
        page.goto(ADV, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # Cancel unfinished edit (red X)
        page.evaluate(
            """() => {
              // click cancel/remove on dirty new row with empty host
              const cancels = [...document.querySelectorAll('a,button')].filter(b => {
                const s=((b.className||'')+(b.title||'')+(b.getAttribute('data-original-title')||'')+(b.getAttribute('data-ng-click')||'')).toLowerCase();
                return (s.includes('cancel') || s.includes('remove') || s.includes('icon-remove') || s.includes('close')) && b.offsetParent;
              });
              // Prefer cancel on editing row
              for (const c of cancels) {
                const row = c.closest('tr') || c.parentElement;
                if (row && /ALIAS/i.test(row.innerText||'')) { c.click(); return 'alias-cancel'; }
              }
              if (cancels[0]) { cancels[0].click(); return 'first-cancel'; }
              return null;
            }"""
        )
        page.wait_for_timeout(800)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

        body = page.inner_text("body")
        has_root = TARGET in body or "2uuatnpq.up.railway.app" in body
        has_www = ("www" in body.lower()) and ("railway.app" in body.lower())
        print(f"has_root={has_root} has_www_guess={has_www}", flush=True)

        # Add www CNAME if missing a www host row to railway
        if "www" not in body.split("HOST RECORDS")[-1].split("MAIL SETTINGS")[0].lower() or True:
            # More precise check
            need_www = page.evaluate(
                """(target) => {
                  const text = document.body.innerText;
                  // look for a www host line near railway
                  return !/www[\\s\\S]{0,40}railway\\.app/i.test(text);
                }""",
                TARGET,
            )
            print(f"need_www={need_www}", flush=True)
            if need_www:
                page.evaluate(
                    """() => {
                      const a=[...document.querySelectorAll('a')].find(x=>(x.getAttribute('data-ng-click')||'').includes('hostRecordsList.addRecord') || ((x.textContent||'').includes('ADD NEW RECORD') && (x.getAttribute('data-ng-click')||'').includes('hostRecords')));
                      if (a) { a.click(); return true; }
                      const b=[...document.querySelectorAll('a')].find(x=>(x.textContent||'').trim().toUpperCase()==='ADD NEW RECORD');
                      if (b) { b.click(); return true; }
                      return false;
                    }"""
                )
                page.wait_for_timeout(600)
                # set CNAME
                page.evaluate(
                    """() => {
                      const s=[...document.querySelectorAll('select')].find(x=>[...x.options].some(o=>/CNAME/i.test(o.text)));
                      if (s) {
                        const o=[...s.options].find(x=>/CNAME/i.test(x.text));
                        s.value=o.value; s.dispatchEvent(new Event('change',{bubbles:true}));
                        return o.text;
                      }
                      return null;
                    }"""
                )
                page.wait_for_timeout(400)
                # If type dropdown is custom, click
                try:
                    if page.get_by_text("A Record", exact=True).count():
                        page.get_by_text("A Record", exact=True).last.click(timeout=1500)
                        page.wait_for_timeout(300)
                        if page.get_by_text("CNAME Record", exact=True).count():
                            page.get_by_text("CNAME Record", exact=True).last.click(timeout=1500)
                except Exception:
                    pass
                page.evaluate(
                    """(t) => {
                      const ins=[...document.querySelectorAll('input')].filter(i=>i.offsetParent&&(i.type==='text'||!i.type)&&!i.value);
                      if (ins.length>=2) {
                        ins[0].value='www';
                        ins[0].dispatchEvent(new Event('input',{bubbles:true}));
                        ins[0].dispatchEvent(new Event('change',{bubbles:true}));
                        ins[1].value=t;
                        ins[1].dispatchEvent(new Event('input',{bubbles:true}));
                        ins[1].dispatchEvent(new Event('change',{bubbles:true}));
                        return true;
                      }
                      return false;
                    }""",
                    TARGET,
                )
                page.wait_for_timeout(300)
                page.evaluate(
                    """() => {
                      const b=[...document.querySelectorAll('a,button')].find(x=>{
                        const s=((x.className||'')+(x.getAttribute('data-ng-click')||'')+(x.title||'')).toLowerCase();
                        return (s.includes('saverecord') || s.includes('icon-check') || (s.includes('save') && !s.includes('all'))) && x.offsetParent;
                      });
                      if (b) { b.click(); return true; }
                      return false;
                    }"""
                )
                page.wait_for_timeout(2000)

        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT / "h_final.png"), full_page=True)
        body = page.inner_text("body")
        (OUT / "h_final.txt").write_text(body[:15000], encoding="utf-8")
        result = {
            "ok": "2uuatnpq.up.railway.app" in body,
            "root_cname": "2uuatnpq.up.railway.app" in body,
            "has_verify_txt": "_railway-verify" in body,
        }
        (OUT / "status.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
