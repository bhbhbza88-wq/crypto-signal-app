"""
Публичная лента сайта = то же, что уходит в @papayaqq.

Правила как в telegram_bot.notify_signal_closed:
  - крупные минусы (> PUBLIC_CHANNEL_MAX_LOSS_PCT) не показываем
  - сырой PnL в ответе; фронт приукрашивает тем же polish, что и канал
"""
from __future__ import annotations

import os

import database as db

PUBLIC_CHANNEL_MAX_LOSS_PCT = float(os.getenv("PUBLIC_CHANNEL_MAX_LOSS_PCT", "3.0") or "3.0")


def would_post_to_channel(pnl) -> bool:
    try:
        p = float(pnl)
    except (TypeError, ValueError):
        return False
    if p < 0 and abs(p) > PUBLIC_CHANNEL_MAX_LOSS_PCT:
        return False
    return True


def load_channel_feed(limit: int = 500, days: int | None = 30) -> list[dict]:
    """Сделки витрины: как в канале результатов (без крупных минусов)."""
    limit = max(1, min(int(limit or 500), 5000))
    # Берём с запасом — после фильтра крупных минусов останется меньше.
    fetch_limit = min(limit * 3, 5000)
    rows = db.load_history(limit=fetch_limit, days=days)
    out = []
    for r in rows:
        row = dict(r)
        if not would_post_to_channel(row.get("pnl")):
            continue
        row["source"] = "papayaqq"
        out.append(row)
        if len(out) >= limit:
            break
    return out


def summarize_trades(trades: list[dict]) -> dict:
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
        "winrate": round(wins / total * 100, 1) if total else 0,
        "tp1": tp1s,
        "tp2_plus": max(0, wins - tp1s),
        "stops": losses,
        "breakeven": bes,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2) if total else 0,
        "best": {"symbol": best["symbol"], "pnl": best["pnl"]},
        "worst": {"symbol": worst["symbol"], "pnl": worst["pnl"]},
    }
