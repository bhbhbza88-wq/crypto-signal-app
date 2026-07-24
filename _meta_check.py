import re, urllib.request
req = urllib.request.Request("https://nowicki.trade/", headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=20) as r:
    t = r.read().decode("utf-8", "replace")
m = re.search(r'name=["\']heleket["\']\s+content=["\']([^"\']+)["\']', t)
print("live_meta", m.group(1) if m else None)
