import urllib.request, re
h = urllib.request.urlopen("https://nowicki.trade/", timeout=30).read().decode("utf-8","replace")
print("scripts:", re.findall(r'/assets/[^"\']+', h)[:10])
# also try cache bust
h2 = urllib.request.urlopen(urllib.request.Request("https://nowicki.trade/", headers={"Cache-Control":"no-cache"}), timeout=30).read().decode("utf-8","replace")
print("nocache:", re.findall(r'/assets/[^"\']+', h2)[:10])
