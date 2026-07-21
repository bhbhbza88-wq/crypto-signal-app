"""
Детерминированные regex-парсеры для типичных форматов крипто-каналов.
AI — fallback, когда ни один паттерн не сработал.

Возвращают тот же dict, что и AI-экстрактор:
  {is_signal, symbol, side, entry, stop, tp1, tp2?, tp3?}
"""
from __future__ import annotations

import re


def _f(raw: str) -> float:
    return float(str(raw).replace(",", ".").replace(" ", ""))


def _norm_sym(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.upper().strip().lstrip("#$")
    if s.endswith("/USDT"):
        s = s.replace("/USDT", "USDT")
    if "/" in s:
        s = s.replace("/", "")
    if not s.endswith("USDT"):
        s = f"{s}USDT"
    if not re.fullmatch(r"[A-Z]{2,15}USDT", s):
        return None
    return s


def _pack(symbol: str | None, side: str, entry: float, stop: float, tp1: float,
          tp2: float | None = None, tp3: float | None = None) -> dict | None:
    if not symbol or not side or entry <= 0 or stop <= 0 or tp1 <= 0:
        return None
    if side == "LONG" and not (stop < entry < tp1):
        return None
    if side == "SHORT" and not (stop > entry > tp1):
        return None
    out = {
        "is_signal": True,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "parser": "regex",
    }
    return out


def _parse_side(raw: str) -> str:
    u = raw.upper()
    if u in ("LONG", "BUY", "ЛОНГ", "ПОКУК"):
        return "LONG"
    return "SHORT"


# #BTCUSDT LONG ... Entry: 65000 ... SL: 64000 ... TP: 67000
_BK = re.compile(
    r"(?:#|\$)?(?P<sym>[A-Z]{2,15})\s*/?\s*USDT?\b"
    r".*?\b(?P<side>LONG|SHORT|BUY|SELL)\b"
    r".*?(?:Entry|Вход|ENTRY)\s*[:=\-]?\s*(?P<entry>\d+(?:[.,]\d+)?)"
    r".*?(?:SL|Stop(?:\s*Loss)?|Стоп)\s*[:=\-]?\s*(?P<stop>\d+(?:[.,]\d+)?)"
    r".*?(?:TP1?|Target|Take\s*Profit|Цель)\s*[:=\-]?\s*(?P<tp1>\d+(?:[.,]\d+)?)"
    r"(?:.*?(?:TP2|Target\s*2)\s*[:=\-]?\s*(?P<tp2>\d+(?:[.,]\d+)?))?"
    r"(?:.*?(?:TP3|Target\s*3)\s*[:=\-]?\s*(?P<tp3>\d+(?:[.,]\d+)?))?",
    re.IGNORECASE | re.DOTALL,
)

# LONG BTCUSDT Entry 1.23 SL 1.20 TP 1.30
_COMPACT = re.compile(
    r"\b(?P<side>LONG|SHORT|BUY|SELL)\b\s+"
    r"(?:#|\$)?(?P<sym>[A-Z]{2,15})\s*/?\s*USDT?\b\s+"
    r"(?:Entry|Вход)?\s*[:=\-]?\s*(?P<entry>\d+(?:[.,]\d+)?)\s+"
    r"(?:SL|Stop|Стоп)\s*[:=\-]?\s*(?P<stop>\d+(?:[.,]\d+)?)\s+"
    r"(?:TP1?|Target|Цель)\s*[:=\-]?\s*(?P<tp1>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

# Лонг ETH / Вход 2450 / Стоп 2400 / Цель 2550
_CYR = re.compile(
    r"\b(?P<side>ЛОНГ|ШОРТ|LONG|SHORT)\b"
    r".*?(?:#|\$)?(?P<sym>[A-Z]{2,15})"
    r".*?(?:Вход|Entry)\s*[:=\-]?\s*(?P<entry>\d+(?:[.,]\d+)?)"
    r".*?(?:Стоп|SL|Stop)\s*[:=\-]?\s*(?P<stop>\d+(?:[.,]\d+)?)"
    r".*?(?:Цель|TP1?|Target)\s*[:=\-]?\s*(?P<tp1>\d+(?:[.,]\d+)?)",
    re.IGNORECASE | re.DOTALL,
)

# Entry zone 1.20-1.22
_ZONE = re.compile(
    r"(?:#|\$)?(?P<sym>[A-Z]{2,15})\s*/?\s*USDT?\b"
    r".*?\b(?P<side>LONG|SHORT)\b"
    r".*?(?:Entry|Вход)\s*[:=\-]?\s*(?P<e1>\d+(?:[.,]\d+)?)\s*[-–—]\s*(?P<e2>\d+(?:[.,]\d+)?)"
    r".*?(?:SL|Stop|Стоп)\s*[:=\-]?\s*(?P<stop>\d+(?:[.,]\d+)?)"
    r".*?(?:TP1?|Target|Цель)\s*[:=\-]?\s*(?P<tp1>\d+(?:[.,]\d+)?)",
    re.IGNORECASE | re.DOTALL,
)


def parse_signal_text(text: str) -> dict | None:
    """Пробует regex-парсеры по очереди. None → звать AI."""
    if not text or not text.strip():
        return None
    t = text.replace("\u2013", "-").replace("\u2014", "-")
    t = re.sub(r"[ \t]+", " ", t)

    for rx in (_ZONE, _BK, _COMPACT, _CYR):
        m = rx.search(t)
        if not m:
            continue
        gd = m.groupdict()
        side = _parse_side(gd["side"])
        sym = _norm_sym(gd.get("sym"))
        if "e1" in gd and gd.get("e1"):
            entry = (_f(gd["e1"]) + _f(gd["e2"])) / 2
        else:
            entry = _f(gd["entry"])
        stop = _f(gd["stop"])
        tp1 = _f(gd["tp1"])
        tp2 = _f(gd["tp2"]) if gd.get("tp2") else None
        tp3 = _f(gd["tp3"]) if gd.get("tp3") else None
        packed = _pack(sym, side, entry, stop, tp1, tp2, tp3)
        if packed:
            return packed
    return None
