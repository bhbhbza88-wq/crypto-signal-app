"""
Bitunix USDT-M futures public API (ccxt пока не поддерживает Bitunix).

База: https://fapi.bitunix.com
Интерфейс методов совместим с тем, что ждёт data_layer (fetch_ticker / fetch_ohlcv).
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
import json
import threading

BASE = "https://fapi.bitunix.com"
_PAIRS_TTL = 3600
_pairs_cache = {"ts": 0.0, "symbols": [], "raw": []}
_pairs_lock = threading.Lock()

# ccxt-style intervals → Bitunix
_INTERVAL = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
    "1d": "1d", "3d": "3d", "1w": "1w",
}


def _to_bitunix_symbol(symbol: str) -> str:
    s = (symbol or "").upper().strip().replace("/", "")
    return s


def _to_unified(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    if "/" in s:
        return s
    if s.endswith("USDT"):
        return f"{s[:-4]}/USDT"
    return s


def _get(path: str, params: dict | None = None, timeout: int = 15):
    qs = urllib.parse.urlencode(params or {})
    url = f"{BASE}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(url, headers={"User-Agent": "NOWICKI/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        print(f"[bitunix] GET {path}: {e}")
        return None
    if not isinstance(body, dict) or body.get("code") not in (0, "0", None):
        # code 0 = ok; some endpoints omit code
        if isinstance(body, dict) and body.get("code") not in (0, "0"):
            print(f"[bitunix] GET {path}: code={body.get('code')} msg={body.get('msg')}")
            return None
    return body


def load_futures_pairs(force: bool = False) -> list[dict]:
    """Список фьючерсных пар Bitunix (OPEN + API supported, quote USDT)."""
    now = time.time()
    with _pairs_lock:
        if not force and _pairs_cache["raw"] and (now - _pairs_cache["ts"]) < _PAIRS_TTL:
            return list(_pairs_cache["raw"])

    body = _get("/api/v1/futures/market/trading_pairs")
    rows = (body or {}).get("data") or []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        status = str(r.get("symbolStatus") or "OPEN").upper()
        if status != "OPEN":
            continue
        if r.get("isApiSupported") is False:
            continue
        quote = str(r.get("quote") or "USDT").upper()
        if quote != "USDT":
            continue
        sym = str(r.get("symbol") or "").upper()
        if not sym.endswith("USDT"):
            continue
        out.append(r)

    symbols = sorted({_to_unified(r["symbol"]) for r in out})
    with _pairs_lock:
        _pairs_cache["ts"] = now
        _pairs_cache["raw"] = out
        _pairs_cache["symbols"] = symbols
    return out


def list_unified_symbols(force: bool = False) -> list[str]:
    load_futures_pairs(force=force)
    with _pairs_lock:
        return list(_pairs_cache["symbols"])


def has_symbol(symbol: str) -> bool:
    uni = _to_unified(symbol)
    return uni in set(list_unified_symbols())


class BitunixFutures:
    """Минимальный ccxt-подобный клиент для data_layer.get_exchange('bitunix')."""

    id = "bitunix"

    def fetch_ticker(self, symbol: str):
        raw = _to_bitunix_symbol(symbol)
        body = _get("/api/v1/futures/market/tickers", {"symbols": raw})
        rows = (body or {}).get("data") or []
        row = None
        for r in rows:
            if str(r.get("symbol") or "").upper() == raw:
                row = r
                break
        if not row and len(rows) == 1:
            row = rows[0]
        if not row:
            return None
        last = row.get("lastPrice") or row.get("last") or row.get("markPrice")
        try:
            last_f = float(last)
        except (TypeError, ValueError):
            return None
        return {
            "symbol": _to_unified(raw),
            "last": last_f,
            "close": last_f,
            "bid": None,
            "ask": None,
            "info": row,
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100, since=None):
        raw = _to_bitunix_symbol(symbol)
        interval = _INTERVAL.get(timeframe, timeframe)
        params = {"symbol": raw, "interval": interval, "limit": int(limit)}
        if since is not None:
            params["startTime"] = int(since)
        body = _get("/api/v1/futures/market/kline", params)
        rows = (body or {}).get("data") or []
        out = []
        for r in rows:
            try:
                ts = int(r.get("time") or r.get("t") or 0)
                o = float(r["open"])
                h = float(r["high"])
                l = float(r["low"])
                c = float(r["close"])
                # Bitunix: baseVol / quoteVol — для объёма берём baseVol (как у ccxt обычно base)
                v = float(r.get("baseVol") or r.get("quoteVol") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            out.append([ts, o, h, l, c, v])
        # API часто отдаёт newest-first
        out.sort(key=lambda x: x[0])
        if limit and len(out) > limit:
            out = out[-limit:]
        return out


bitunix = BitunixFutures()
