"""
USDT-M / swap venues via ccxt (OKX, Bitget, BingX) + helpers for market lists.

Наше приложение хранит символы как BTC/USDT; у OKX/Bitget/BingX в ccxt
часто BTC/USDT:USDT — адаптер мапит туда-обратно.
"""

from __future__ import annotations

import time
import threading
import ccxt

_MARKETS_TTL = 3600


def _unified_base_quote(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    if ":" in s:
        s = s.split(":", 1)[0]
    if "/" not in s and s.endswith("USDT"):
        s = s[:-4] + "/USDT"
    return s


class CcxtSwapAdapter:
    """Обёртка над ccxt swap/linear: fetch_* принимают BTC/USDT."""

    def __init__(self, exchange_id: str, client):
        self.id = exchange_id
        self.ex = client
        self._lock = threading.Lock()
        self._ts = 0.0
        self._unified: list[str] = []
        self._to_ccxt: dict[str, str] = {}

    def _refresh_markets(self, force: bool = False):
        now = time.time()
        with self._lock:
            if not force and self._unified and (now - self._ts) < _MARKETS_TTL:
                return
        try:
            markets = self.ex.load_markets(reload=force)
        except Exception as e:
            print(f"[{self.id}] load_markets: {e}")
            return
        to_ccxt = {}
        for sym, m in (markets or {}).items():
            if not isinstance(m, dict):
                continue
            if m.get("active") is False:
                continue
            # perpetual / swap USDT-settled (or quote USDT)
            is_swap = bool(m.get("swap") or (m.get("linear") and m.get("contract")))
            if not is_swap and m.get("type") not in ("swap", "future"):
                # bybit-style linear sometimes type=swap already handled
                if not (m.get("linear") and m.get("contract")):
                    continue
            settle = (m.get("settle") or m.get("quote") or "").upper()
            quote = (m.get("quote") or "").upper()
            if settle not in ("USDT", "") and quote != "USDT":
                continue
            if quote and quote != "USDT" and settle != "USDT":
                continue
            uni = _unified_base_quote(m.get("symbol") or sym)
            if not uni.endswith("/USDT"):
                continue
            # предпочитаем :USDT variant если есть
            if uni not in to_ccxt or ":" in sym:
                to_ccxt[uni] = sym
        with self._lock:
            self._to_ccxt = to_ccxt
            self._unified = sorted(to_ccxt.keys())
            self._ts = time.time()

    def list_unified_symbols(self, force: bool = False) -> list[str]:
        self._refresh_markets(force=force)
        with self._lock:
            return list(self._unified)

    def has_symbol(self, symbol: str) -> bool:
        uni = _unified_base_quote(symbol)
        self._refresh_markets()
        with self._lock:
            return uni in self._to_ccxt

    def _resolve(self, symbol: str) -> str | None:
        uni = _unified_base_quote(symbol)
        self._refresh_markets()
        with self._lock:
            if uni in self._to_ccxt:
                return self._to_ccxt[uni]
        # fallbacks
        for cand in (uni, f"{uni}:USDT", uni.replace("/", "-") + "-SWAP"):
            try:
                # don't call market() if unknown — just try ticker later
                pass
            except Exception:
                pass
        return f"{uni}:USDT"

    def fetch_ticker(self, symbol: str):
        resolved = self._resolve(symbol)
        if not resolved:
            return None
        t = self.ex.fetch_ticker(resolved)
        if t and not t.get("symbol"):
            t["symbol"] = _unified_base_quote(symbol)
        elif t:
            t = dict(t)
            t["symbol"] = _unified_base_quote(symbol)
        return t

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100, since=None):
        resolved = self._resolve(symbol)
        if not resolved:
            return None
        kwargs = {"limit": limit}
        if since is not None:
            kwargs["since"] = since
        return self.ex.fetch_ohlcv(resolved, timeframe, **kwargs)


def build_okx():
    return CcxtSwapAdapter(
        "okx",
        ccxt.okx({
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
            "timeout": 20000,
        }),
    )


def build_bitget():
    return CcxtSwapAdapter(
        "bitget",
        ccxt.bitget({
            "options": {"defaultType": "swap", "defaultSubType": "linear"},
            "enableRateLimit": True,
            "timeout": 20000,
        }),
    )


def build_bingx():
    return CcxtSwapAdapter(
        "bingx",
        ccxt.bingx({
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
            "timeout": 20000,
        }),
    )
