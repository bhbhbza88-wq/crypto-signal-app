"""
Карточка закрытия — стиль Binance Futures share:
чёрный фон edge-to-edge, пара, шорт/лонг | плечо, крупный ROI, цена входа / последняя.
"""

from __future__ import annotations

import io
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

SHARE_LEVERAGE = int(os.getenv("PROFIT_CARD_LEVERAGE", "10"))
PNL_SHOW_MULT = float(os.getenv("PROFIT_CARD_PNL_MULT", "1.12"))

# точные цвета как на референсе
BG = (0, 0, 0)
WHITE = (255, 255, 255)
GREY = (140, 145, 155)
GREEN = (14, 203, 129)   # binance green
RED = (246, 70, 93)      # binance red / short


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
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 1000:
        return f"{n:.2f}"
    if n >= 100:
        return f"{n:.4f}"
    if n >= 1:
        return f"{n:.7f}".rstrip("0").rstrip(".") if n < 10 else f"{n:.4f}"
    # мелкие альты — больше знаков, как на бирже
    s = f"{n:.8f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s


def _exit_from_pnl(side: str, entry: float, pnl_pct: float) -> float:
    if side.upper() == "LONG":
        return entry * (1 + pnl_pct / 100.0)
    return entry * (1 - pnl_pct / 100.0)


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
    roi = round(show_pnl * leverage, 2)

    coin = symbol.replace("/USDT", "").replace("USDT", "").upper()
    pair_line = f"{coin}USDT Бессрочный"
    side_ru = "Лонг" if side == "LONG" else "Шорт"
    side_color = GREEN if side == "LONG" else RED
    roi_color = GREEN if roi >= 0 else RED
    roi_str = f"+{roi:.2f}%" if roi >= 0 else f"{roi:.2f}%"

    # квадрат / чуть вертикальнее — без белых полей, фон на весь кадр
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # лёгкий тёмный геометрический узор справа сверху (как у Binance)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    cx, cy = W - 80, 120
    for i, size in enumerate((520, 420, 320, 220)):
        a = 18 - i * 3
        od.rectangle(
            [cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2],
            outline=(40, 44, 52, max(a, 6)),
            width=3,
        )
    # ромб
    s = 380
    od.polygon(
        [(cx, cy - s // 2), (cx + s // 2, cy), (cx, cy + s // 2), (cx - s // 2, cy)],
        outline=(45, 50, 60, 40),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_pair = _font(52, bold=True)
    font_side = _font(40, bold=True)
    font_roi = _font(120, bold=True)
    font_label = _font(32)
    font_val = _font(40, bold=True)

    pad = 72
    y = 100

    draw.text((pad, y), pair_line, font=font_pair, fill=WHITE)
    y += 78

    # «Шорт | 25x»
    side_text = f"{side_ru} "
    draw.text((pad, y), side_text, font=font_side, fill=side_color)
    sw = draw.textlength(side_text, font=font_side)
    rest = f"| {leverage}x"
    draw.text((pad + sw, y), rest, font=font_side, fill=GREY)
    y += 100

    draw.text((pad, y), roi_str, font=font_roi, fill=roi_color)
    y += 180

    # две колонки: цена входа | последняя цена
    col2_x = W // 2 + 20
    draw.text((pad, y), "Цена входа", font=font_label, fill=GREY)
    draw.text((col2_x, y), "Последняя цена", font=font_label, fill=GREY)
    y += 52
    draw.text((pad, y), _fmt_price(entry), font=font_val, fill=WHITE)
    draw.text((col2_x, y), _fmt_price(exit_price), font=font_val, fill=WHITE)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
