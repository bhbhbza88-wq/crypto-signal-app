import urllib.request, re
h = urllib.request.urlopen("https://nowicki.trade/").read().decode()
js = re.findall(r'/assets/[^"\']+\.js', h)
print("entry", js)
# find shared from entry imports by downloading entry
b = urllib.request.urlopen("https://nowicki.trade" + js[0]).read().decode()
shares = re.findall(r'shared-[A-Za-z0-9_-]+\.js', b)
apps = re.findall(r'App-[A-Za-z0-9_-]+\.js', b)
print("shared", shares[:3], "app", apps[:3])
for name in set(shares[:1] + apps[:1]):
    body = urllib.request.urlopen("https://nowicki.trade/assets/" + name).read().decode()
    print(name, "U=15" if "U=15" in body or "=15;" in body else "no U", "*100*15" if "*100*15" in body else "", "1.22" if "1.22" in body else "", "15x label" if "15x" in body else "")
