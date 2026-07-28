import urllib.request, re
# search for displayPnl-ish polish multipliers or history pnl
b = urllib.request.urlopen("https://nowicki.trade/assets/index-DD4NJ7r0.js", timeout=30).read().decode("utf-8","replace")
for pat in ["1.22", "0.42", "92", "polishHistory", "displayPnl", "winrate", "PnL", "pnl"]:
    print(pat, b.count(pat))
# find *1.22 style
for m in re.finditer(r'.{0,30}1\.22.{0,30}', b):
    print("hit", m.group(0)); break
for m in re.finditer(r'.{0,20}\* ?15 ?\*.{0,20}|.{0,20}\*15\b.{0,20}', b):
    print("15hit", m.group(0)[:80]); break
print("sample mid", b[100000:100200])
