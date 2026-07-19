"""
Витринный fill истории за ~месяц для сайта.

Реальные сделки из БД не трогаем и в Telegram не шлём.
На /api/history и в month-бакете /api/stats подмешиваем детерминированные
синтетические закрытия, чтобы лента выглядела плотной. Сырой PnL такой же,
как у живых сделок — фронт приукрасит через polish (×1.22 / ×0.42).
"""
from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from datetime import datetime, timedelta

# Цель: почти каждый день есть сделки, всего ~90–120 за 30 дней.
TARGET_PER_DAY = (3, 5)  # min/max синтетики на день (сверх реальных)
WIN_RATE = 0.72  # сырой винрейт до polish → на сайте ~84% после bump

_SYMBOLS = [
    ("BTC/USDT", 65000, 0.6),
    ("ETH/USDT", 3400, 0.8),
    ("SOL/USDT", 145, 1.2),
    ("BNB/USDT", 580, 0.9),
    ("XRP/USDT", 0.62, 1.1),
    ("ADA/USDT", 0.45, 1.3),
    ("AVAX/USDT", 28, 1.4),
    ("LINK/USDT", 14, 1.2),
    ("DOT/USDT", 7.2, 1.3),
    ("NEAR/USDT", 5.1, 1.5),
    ("APT/USDT", 9.4, 1.4),
    ("ARB/USDT", 0.85, 1.6),
    ("OP/USDT", 1.9, 1.5),
    ("SUI/USDT", 2.1, 1.5),
    ("DOGE/USDT", 0.16, 1.4),
    ("LTC/USDT", 85, 1.0),
    ("ATOM/USDT", 6.8, 1.3),
    ("FIL/USDT", 4.2, 1.5),
    ("INJ/USDT", 22, 1.6),
    ("TIA/USDT", 5.5, 1.7),
]


def _rng_for(day: str, salt: str = "") -> random.Random:
    h = hashlib.sha256(f"{day}|{salt}|nowicki-showcase".encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _result_for(pnl: float, rng: random.Random) -> str:
    if abs(pnl) < 0.15:
        return "be"
    if pnl < 0:
        return "sl"
    roll = rng.random()
    if roll < 0.45:
        return "tp1"
    if roll < 0.78:
        return "tp2"
    return "tp3"


def _make_trade(day: str, idx: int, rng: random.Random) -> dict:
    sym, px, vol = _SYMBOLS[rng.randrange(len(_SYMBOLS))]
    # лёгкий дрейф цены от «базы»
    entry = round(px * (1 + rng.uniform(-0.04, 0.04)), 6 if px < 10 else 4)
    side = "LONG" if rng.random() < 0.62 else "SHORT"
    win = rng.random() < WIN_RATE
    if win:
        # сырой плюс: 0.6% … 4.8% (после polish ×1.22 → ~0.7–5.9)
        pnl = round(rng.uniform(0.6, 4.8) * (0.85 + 0.3 * vol / 1.5), 2)
    else:
        # сырой минус: −0.4% … −2.8% (после polish ×0.42 → мягче)
        pnl = -round(rng.uniform(0.4, 2.8) * (0.85 + 0.25 * vol / 1.5), 2)
    hour = rng.choice([8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 21, 22])
    minute = rng.choice([0, 5, 12, 18, 25, 33, 40, 47, 55])
    # отрицательный id — не пересекается с AUTOINCREMENT
    sid = -(int(hashlib.md5(f"{day}-{idx}-{sym}".encode()).hexdigest()[:7], 16) % 900_000_000 + 1000)
    return {
        "id": sid,
        "date": day,
        "time": f"{hour:02d}:{minute:02d}",
        "symbol": sym,
        "signal": side,
        "entry": entry,
        "result": _result_for(pnl, rng),
        "pnl": pnl,
        "trader_id": None,
        "showcase": True,
    }


def generate_fill(days: int = 30) -> list[dict]:
    """Синтетика за последние `days` календарных дней (включая сегодня)."""
    days = max(1, min(int(days or 30), 90))
    today = datetime.now().date()
    out: list[dict] = []
    for offset in range(days):
        d = today - timedelta(days=offset)
        day = d.strftime("%Y-%m-%d")
        rng = _rng_for(day)
        # выходные чуть реже
        lo, hi = TARGET_PER_DAY
        if d.weekday() >= 5:
            lo, hi = 2, 4
        n = rng.randint(lo, hi)
        for i in range(n):
            out.append(_make_trade(day, i, _rng_for(day, str(i))))
    return out


def merge_public_history(real: list[dict], days: int = 30, limit: int = 500) -> list[dict]:
    """
    Реальные сделки + синтетика.
    Если в конкретный день уже много реальных — синтетику почти не добавляем.
    """
    days = max(1, min(int(days or 30), 90))
    limit = max(1, min(int(limit or 500), 5000))
    real = list(real or [])
    by_day: dict[str, int] = defaultdict(int)
    for t in real:
        if t.get("date"):
            by_day[str(t["date"])] += 1

    fill = []
    for t in generate_fill(days=days):
        day = t["date"]
        already_real = by_day[day]  # только реальные на старте дня; ниже учтём fill
        already_fill = sum(1 for x in fill if x["date"] == day)
        total_day = already_real + already_fill
        if total_day >= TARGET_PER_DAY[1]:
            continue
        # добираем хотя бы до минимума, иначе докидываем до max с вероятностью
        if total_day < TARGET_PER_DAY[0] or (
            total_day < TARGET_PER_DAY[1] and _rng_for(day, f"x{already_fill}").random() < 0.75
        ):
            fill.append(t)

    merged = []
    for t in real:
        row = dict(t)
        row["showcase"] = False
        merged.append(row)
    merged.extend(fill)

    def _key(t):
        return (str(t.get("date") or ""), str(t.get("time") or ""), int(t.get("id") or 0))

    merged.sort(key=_key, reverse=True)
    return merged[:limit]


def summarize_trades(trades: list[dict]) -> dict:
    """Тот же формат, что _summarize / _stats_bucket."""
    if not trades:
        return {
            "total": 0, "winrate": 0, "tp1": 0, "tp2_plus": 0,
            "stops": 0, "breakeven": 0, "total_pnl": 0, "avg_pnl": 0,
            "best": None, "worst": None,
        }
    total = len(trades)
    wins = sum(1 for t in trades if float(t.get("pnl") or 0) > 0)
    losses = sum(1 for t in trades if t.get("result") == "sl")
    bes = sum(1 for t in trades if t.get("result") in ("be", "potential"))
    tp1s = sum(1 for t in trades if t.get("result") == "tp1")
    total_pnl = sum(float(t.get("pnl") or 0) for t in trades)
    best = max(trades, key=lambda x: float(x.get("pnl") or 0))
    worst = min(trades, key=lambda x: float(x.get("pnl") or 0))
    return {
        "total": total,
        "winrate": round(wins / total * 100, 1),
        "tp1": tp1s,
        "tp2_plus": max(0, wins - tp1s),
        "stops": losses,
        "breakeven": bes,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2),
        "best": {"symbol": best["symbol"], "pnl": best["pnl"]},
        "worst": {"symbol": worst["symbol"], "pnl": worst["pnl"]},
    }
