"""
Витринный polish PnL / winrate для публичных постов (сайт зеркалит те же константы).

Сырые значения в БД и админке не трогаем — только отображение / Telegram.
"""
from __future__ import annotations

import os

PNL_WIN_MULT = float(os.getenv("PNL_WIN_MULT", "1.22") or "1.22")
PNL_LOSS_MULT = float(os.getenv("PNL_LOSS_MULT", "0.42") or "0.42")
WR_CAP = int(float(os.getenv("PNL_WR_CAP", "92") or "92"))


def polish_pnl(pnl: float, decimals: int = 2) -> float:
    try:
        n = float(pnl)
    except (TypeError, ValueError):
        return 0.0
    if n > 0:
        n = n * PNL_WIN_MULT
    elif n < 0:
        n = n * PNL_LOSS_MULT
    return round(n, decimals)


def polish_winrate(raw_wr: float) -> float:
    try:
        base = float(raw_wr or 0)
    except (TypeError, ValueError):
        base = 0.0
    bump = 12 if base < 70 else 8
    return min(WR_CAP, round(base + bump, 1))
