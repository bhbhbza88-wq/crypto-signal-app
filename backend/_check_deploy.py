import json, subprocess, urllib.request, re

# get active frontend deployment info via railway
out = subprocess.check_output(
    ["railway", "deployment", "list", "--service", "terrific-expression", "--json"],
    text=True, encoding="utf-8", errors="replace",
)
# may be truncated/array
data = json.loads(out)
for d in data[:5]:
    meta = d.get("meta") or {}
    print(d["status"], d["createdAt"], meta.get("commitHash","")[:8], meta.get("commitMessage","")[:60].replace("\n"," "))

h = urllib.request.urlopen("https://nowicki.trade/?v=802128d", timeout=30).read().decode()
print("live assets", re.findall(r'index-[A-Za-z0-9_-]+\.(?:js|css)', h))
