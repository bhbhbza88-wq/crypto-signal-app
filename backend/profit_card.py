"""
Карточка закрытия сделки (share-card) — PIL.
Значения подставляются из реальной сделки: пара, сторона, вход, выход, PnL.
"""

from __future__ import annotations

import io
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

SITE_URL = os.getenv("SITE_URL", "https://nowicki.trade")
# Для «витринного» ROI как на биржах (цена% × плечо). Бумажный pnl — движение цены.
SHARE_LEVERAGE = int(os.getenv("PROFIT_CARD_LEVERAGE", "10"))
PNL_SHOW_MULT = float(os.getenv("PROFIT_CARD_PNL_MULT", "1.12"))


def _font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
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
    if n >= 100:
        return f"{n:.2f}"
    if n >= 1:
        return f"{n:.4f}"
    s = f"{n:.6f}".rstrip("0").rstrip(".")
    return s or "0"


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
    """PNG bytes карточки закрытия."""
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
    # Витринный ROI с плечом (как share-карточки бирж)
    roi = round(show_pnl * leverage, 2)
    coin = symbol.replace("/USDT", "").replace("USDT", "").upper()
    pair = f"{coin}USDT"
    side_ru = "Лонг" if side == "LONG" else "Шорт"
    when = when or datetime.now()
    stamp = when.strftime("%Y-%m-%d %H:%M")

    W, H = 900, 1200
    img = Image.new("RGB", (W, H), "#0a1210")
    draw = ImageDraw.Draw(img)

    # фон: тёмный teal + золотые блики
    for y in range(H):
        t = y / H
        r = int(8 + t * 30)
        g = int(18 + t * 40)
        b = int(16 + (1 - t) * 20)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # золотое свечение сверху
    for i in range(280):
        alpha = 1 - i / 280
        c = int(40 + 80 * alpha)
        draw.ellipse(
            [-120, -180 + i // 2, W + 120, 420 + i],
            outline=(c, int(c * 0.75), 20),
        )

    # декоративные «купюры»
    import random
    rng = random.Random(hash(pair) % 10_000)
    for _ in range(40):
        x, y = rng.randint(0, W), rng.randint(80, 780)
        w, h = rng.randint(28, 70), rng.randint(14, 28)
        rot = rng.randint(-35, 35)
        bill = Image.new("RGBA", (w, h), (30, 140, 70, 160))
        bill = bill.rotate(rot, expand=True)
        img.paste(bill, (x, y), bill)

    draw = ImageDraw.Draw(img)

    font_brand = _font(36, bold=True)
    font_pair = _font(64, bold=True)
    font_side = _font(42, bold=True)
    font_roi = _font(110, bold=True)
    font_label = _font(28)
    font_val = _font(34, bold=True)
    font_foot = _font(26)
    font_foot_b = _font(28, bold=True)

    # бренд
    draw.text((48, 40), "NOWICKI", font=font_brand, fill="#3DDC97")

    # пара
    draw.text((48, 200), pair, font=font_pair, fill="#FFFFFF")

    # сторона + плечо
    side_color = "#00C896" if side == "LONG" else "#F04A59"
    draw.text((48, 290), f"{side_ru} {leverage}X", font=font_side, fill=side_color)

    # ROI
    roi_color = "#00E676" if roi >= 0 else "#F04A59"
    roi_str = f"+{roi:.2f}%" if roi >= 0 else f"{roi:.2f}%"
    draw.text((48, 380), roi_str, font=font_roi, fill=roi_color)

    # цены
    y0 = 560
    draw.text((48, y0), "Цена открытия", font=font_label, fill="#9AA8A0")
    draw.text((48, y0 + 40), _fmt_price(entry), font=font_val, fill="#FFFFFF")
    draw.text((48, y0 + 110), "Последняя цена", font=font_label, fill="#9AA8A0")
    draw.text((48, y0 + 150), _fmt_price(exit_price), font=font_val, fill="#FFFFFF")

    # белый футер
    foot_y = 980
    draw.rounded_rectangle([0, foot_y, W, H], radius=0, fill="#F5F7F6")
    draw.text((48, foot_y + 36), stamp, font=font_foot, fill="#333333")
    draw.text((48, foot_y + 80), "nowicki.trade", font=font_foot_b, fill="#0B1F1C")
    draw.text((48, foot_y + 120), "AI market scanner", font=font_foot, fill="#666666")

    # QR на сайт
    try:
        import qrcode
        qr = qrcode.QRCode(border=1, box_size=5)
        qr.add_data(SITE_URL)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0B1F1C", back_color="#F5F7F6").convert("RGB")
        qr_img = qr_img.resize((140, 140))
        img.paste(qr_img, (W - 190, foot_y + 30))
    except Exception:
        draw.rectangle([W - 190, foot_y + 30, W - 50, foot_y + 170], outline="#0B1F1C", width=3)
        draw.text((W - 175, foot_y + 85), "QR", font=font_foot, fill="#0B1F1C")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
