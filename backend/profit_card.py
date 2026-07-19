"""
Карточка закрытия: статичный фон (assets/pnl_card_bg.png) + текст поверх.
Раскладка как у Binance Futures share.
Шрифты с кириллицей — backend/assets/fonts (DejaVu), иначе системные.
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHARE_LEVERAGE = int(os.getenv("PROFIT_CARD_LEVERAGE", "10"))

# re-export for any old imports
from display_polish import polish_pnl  # noqa: E402
PNL_SHOW_MULT = float(os.getenv("PNL_WIN_MULT", "1.22") or "1.22")

_ASSETS = Path(__file__).resolve().parent / "assets"
BG_PATH = _ASSETS / "pnl_card_bg.png"
_FONT_REG = _ASSETS / "fonts" / "card-regular.ttf"
_FONT_BOLD = _ASSETS / "fonts" / "card-bold.ttf"

WHITE = (255, 255, 255)
GREY = (132, 142, 156)
GREEN = (14, 203, 129)
RED = (246, 70, 93)


@lru_cache(maxsize=8)
def _font(size: int, bold: bool = False):
    """Всегда шрифт с кириллицей — иначе на Railway подписи превращаются в □□□."""
    bundled = _FONT_BOLD if bold else _FONT_REG
    candidates = [
        str(bundled),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\seguisb.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    # load_default() без кириллицы — лучше громко упасть, чем слать □□□
    raise RuntimeError(
        "Нет TTF с кириллицей для profit_card. "
        "Положи DejaVu в backend/assets/fonts/card-regular.ttf и card-bold.ttf"
    )


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

    show_pnl = polish_pnl(pnl_pct, decimals=2)
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

    # Эмблема Binance справа сверху — весь текст держим в левой половине.
    # (Как на эталонном share: пара/ROI не залезают на ромбы.)
    pad = int(W * 0.078)
    text_max_w = int(W * 0.50)
    col2_x = int(W * 0.50)

    def fit_font(text: str, start: int, bold: bool, min_size: int = 14) -> ImageFont.FreeTypeFont:
        size = start
        while size >= min_size:
            f = _font(size, bold=bold)
            if draw.textlength(text, font=f) <= text_max_w:
                return f
            size -= 1
        return _font(min_size, bold=bold)

    font_pair = fit_font(pair_line, max(24, int(H * 0.038)), bold=True, min_size=18)
    font_side = _font(max(18, int(H * 0.030)), bold=False)
    font_roi = fit_font(roi_str, max(44, int(H * 0.095)), bold=True, min_size=28)
    font_label = _font(max(16, int(H * 0.026)), bold=False)
    font_val = _font(max(20, int(H * 0.033)), bold=True)

    # Вертикаль как на эталоне: пара → лонг → ROI → цены, с зазором от логотипа
    y_pair = int(H * 0.235)
    y_side = int(H * 0.295)
    y_roi = int(H * 0.400)
    y_lab = int(H * 0.655)
    y_val = int(H * 0.710)

    draw.text((pad, y_pair), pair_line, font=font_pair, fill=WHITE)

    side_text = f"{side_ru} "
    draw.text((pad, y_side), side_text, font=font_side, fill=side_color)
    sw = draw.textlength(side_text, font=font_side)
    draw.text((pad + sw, y_side), f"| {leverage}x", font=font_side, fill=GREY)

    draw.text((pad, y_roi), roi_str, font=font_roi, fill=roi_color)

    draw.text((pad, y_lab), "Цена входа", font=font_label, fill=GREY)
    draw.text((col2_x, y_lab), "Последняя цена", font=font_label, fill=GREY)
    draw.text((pad, y_val), _fmt_price(entry), font=font_val, fill=WHITE)
    draw.text((col2_x, y_val), _fmt_price(exit_price), font=font_val, fill=WHITE)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
