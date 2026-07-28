import urllib.request, re

h = urllib.request.urlopen("https://nowicki.trade/", timeout=30).read().decode("utf-8", "replace")
m = re.findall(r'/assets/[^"\'>\s]+\.js', h)
print("js", m[:5])
if not m:
    raise SystemExit("no js")
b = urllib.request.urlopen("https://nowicki.trade" + m[0], timeout=30).read().decode("utf-8", "replace")
print("bundle_len", len(b))
for pat in ("LEVERAGE", "OPEN_POS", "1.22", "0.42", "*15", "15*"):
    print(pat, "count=", b.count(pat))
# look for leveraged calc pattern
idxs = [m.start() for m in re.finditer(r"\*15|15\*|LEVERAGE", b)]
print("idxs", idxs[:10])
for i in idxs[:3]:
    print("ctx:", b[max(0, i - 50) : i + 60].replace("\n", " "))
