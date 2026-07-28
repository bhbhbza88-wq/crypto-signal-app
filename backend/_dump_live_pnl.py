import urllib.request, re

shared = urllib.request.urlopen("https://nowicki.trade/assets/shared-Evur7k1z.js").read().decode()
print("SHARED FULL:")
print(shared)
print("\n---APP live pnl snippets---")
app = urllib.request.urlopen("https://nowicki.trade/assets/App-DXpLzT1O.js").read().decode()
for m in re.finditer(r'.{0,80}\*100\*.{0,80}', app):
    print(m.group(0))
    print("---")
for m in re.finditer(r'.{0,60}\*15.{0,60}', app):
    print("15:", m.group(0))
