import urllib.request

for name in [
    "shared-Evur7k1z.js",
    "shared-BQKSG90e.js",
    "App-DXpLzT1O.js",
    "App-BXBeosej.js",
    "HistoryTable-DM92lzoY.js",
]:
    url = f"https://nowicki.trade/assets/{name}"
    try:
        r = urllib.request.urlopen(url, timeout=20)
        b = r.read().decode("utf-8", "replace")
        print(name, "OK", len(b), "1.22=", b.count("1.22"), "15=", b.count("*15"), "has15lit=", ",15," in b or "*15" in b or "=15" in b)
        if "1.22" in b:
            i = b.index("1.22")
            print("  ctx", b[i-40:i+50])
    except Exception as e:
        print(name, "FAIL", e)
