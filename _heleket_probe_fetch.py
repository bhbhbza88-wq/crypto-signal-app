import urllib.request
import re
import pathlib

out = pathlib.Path(r"C:\Users\Dell\Desktop\crypto-signal-app\_heleket_probe")
out.mkdir(exist_ok=True)

urls = [
    ("https://nowicki.trade/", "home.html"),
    ("https://nowicki.trade/support.html", "support.html"),
    ("https://nowicki.trade/app/pricing", "pricing.html"),
]

patterns = [
    "heleket",
    "5d6c84b2",
    "Kupyansk",
    "bhbhbza",
    "support.html",
    "Premium",
    "$29",
    "$75",
    "$299",
    "Plans",
    "Customer support",
    "Products",
]

for url, name in urls:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        body = r.read()
        status = r.status
        final = r.geturl()
    path = out / name
    path.write_bytes(body)
    text = body.decode("utf-8", "replace")
    print("===", name, "STATUS", status, "FINAL", final, "LEN", len(body))
    for pat in patterns:
        print(f"  {pat}:", pat.lower() in text.lower())
    metas = re.findall(r"<meta[^>]+>", text, flags=re.I)
    print("  metas:")
    for m in metas[:25]:
        print("   ", m)
    title = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    print("  title:", title.group(1).strip() if title else None)
    print("  head snippet:")
    print(text[:1200].encode("ascii", "backslashreplace").decode())
    print()
