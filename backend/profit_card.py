"""
Карточка закрытия: статичный фон (assets/pnl_card_bg.png) + текст поверх.
Раскладка как у Binance Futures share.
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHARE_LEVERAGE = int(os.getenv("PROFIT_CARD_LEVERAGE", "10"))
PNL_SHOW_MULT = float(os.getenv("PROFIT_CARD_PNL_MULT", "1.12"))

BG_PATH = Path(__file__).resolve().parent / "assets" / "pnl_card_bg.png"

WHITE = (255, 255, 255)
GREY = (132, 142, 156)
GREEN = (14, 203, 129)
RED = (246, 70, 93)


def _font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\seguisb.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _fmt_price(v: float) -> str:
    """Как на Binance share — фиксированная точность, без обрезки нулей."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 1000:
        return f"{n:.2f}"
    if n >= 100:
        return f"{n:.4f}"
    if n >= 1:
        return f"{n:.7f}"
    return f"{n:.8f}"


def _exit_from_pnl(side: str, entry: float, pnl_pct: float) -> float:
    if side.upper() == "LONG":
        return entry * (1 + pnl_pct / 100.0)
    return entry * (1 - pnl_pct / 100.0)


@lru_cache(maxsize=1)
def _load_bg() -> Image.Image:
    if not BG_PATH.exists():
        raise FileNotFoundError(f"Нет фона карточки: {BG_PATH}")
    return Image.open(BG_PATH).convert("RGB")


def render_profit_card(
    symbol: str,
    side: str,
    entry: float,
    pnl_pct: float,
    exit_price: float | None = None,
    leverage: int | None = None,
    when: datetime | None = None,
) -> bytes:
    side = (side or "LONG").upper()
    leverage = leverage or SHARE_LEVERAGE
    entry = float(entry)
    pnl_pct = float(pnl_pct)
    if exit_price is None:
        exit_price = _exit_from_pnl(side, entry, pnl_pct)
    else:
        exit_price = float(exit_price)

    win = pnl_pct > 0
    show_pnl = round(pnl_pct * PNL_SHOW_MULT, 2) if win else round(pnl_pct, 2)
    # ROI на карточке = движение цены × плечо (как Binance ROE)
    roi = round(show_pnl * leverage, 2)

    coin = symbol.replace("/USDT", "").replace("USDT", "").upper()
    pair_line = f"{coin}USDT Бессрочный"
    side_ru = "Лонг" if side == "LONG" else "Шорт"
    side_color = GREEN if side == "LONG" else RED
    roi_color = GREEN if roi >= 0 else RED
    roi_str = f"+{roi:.2f}%" if roi >= 0 else f"{roi:.2f}%"

    img = _load_bg().copy()
    W, H = img.size
    draw = ImageDraw.Draw(img)

    # раскладка по первому референсу: блок текста НИЖЕ, не прилипает к верху
    pad = int(W * 0.07)
    col2_x = int(W * 0.48)

    font_pair = _font(max(28, int(H * 0.045)), bold=True)
    font_side = _font(max(22, int(H * 0.034)), bold=False)
    font_roi = _font(max(52, int(H * 0.110)), bold=True)
    font_label = _font(max(18, int(H * 0.028)), bold=False)
    font_val = _font(max(22, int(H * 0.036)), bold=True)

    # опустили весь блок ~на 8–10% вниз относительно прошлой версии
    draw.text((pad, int(H * 0.175)), pair_line, font=font_pair, fill=WHITE)

    y_side = int(H * 0.240)
    side_text = f"{side_ru} "
    draw.text((pad, y_side), side_text, font=font_side, fill=side_color)
    sw = draw.textlength(side_text, font=font_side)
    draw.text((pad + sw, y_side), f"| {leverage}x", font=font_side, fill=GREY)

    draw.text((pad, int(H * 0.365)), roi_str, font=font_roi, fill=roi_color)

    y_lab = int(H * 0.600)
    y_val = int(H * 0.655)
    draw.text((pad, y_lab), "Цена входа", font=font_label, fill=GREY)
    draw.text((col2_x, y_lab), "Последняя цена", font=font_label, fill=GREY)
    draw.text((pad, y_val), _fmt_price(entry), font=font_val, fill=WHITE)
    draw.text((col2_x, y_val), _fmt_price(exit_price), font=font_val, fill=WHITE)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
