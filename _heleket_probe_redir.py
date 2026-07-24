import urllib.request
import http.client
from urllib.parse import urlparse

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def head_or_get(url, follow=True):
    parsed = urlparse(url)
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=30)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    headers = {"User-Agent": "Mozilla/5.0 (compatible; HeleketModBot/1.0)"}
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read(8000)
    loc = resp.getheader("Location")
    print(f"URL={url}")
    print(f"  status={resp.status} location={loc} len={len(body)} ctype={resp.getheader('Content-Type')}")
    text = body.decode("utf-8", "replace")
    print(f"  Available services={('Available services' in text)} Products table={('<table>' in text)} id=root={('id=\"root\"' in text)} heleket={('heleket' in text)}")
    print(f"  title snippet={text[text.find('<title>'):text.find('</title>')+8] if '<title>' in text else 'n/a'}")
    print()
    conn.close()
    if follow and loc and resp.status in (301, 302, 303, 307, 308):
        next_url = loc if loc.startswith("http") else f"{parsed.scheme}://{parsed.netloc}{loc}"
        head_or_get(next_url, follow=True)

for u in [
    "https://nowicki.trade/support.html",
    "https://nowicki.trade/support",
    "https://nowicki.trade/",
]:
    head_or_get(u, follow=True)
