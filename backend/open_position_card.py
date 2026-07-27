"""
Карточка открытой позиции (Bybit / BingX) для публикации ТВХ.
Меняем только текст на реальном скриншоте — AI image-edit (как profit_card)
или PIL clear+draw fallback.
"""

from __future__ import annotations

import io
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_ASSETS = Path(__file__).resolve().parent / "assets" / "open_position"


def _template_path(style: str) -> Path:
    """Предпочитаем PNG-исходник; fallback на jpg."""
    name = "bybit" if style == "bybit" else "bingx"
    png = _ASSETS / f"{name}.png"
    jpg = _ASSETS / f"{name}.jpg"
    if png.exists():
        return png
    return jpg


BYBIT_PATH = _template_path("bybit")
BINGX_PATH = _template_path("bingx")

# reuse fonts from profit_card assets
_FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_REG = _FONTS / "NotoSans-Regular.ttf"
_FONT_MED = _FONTS / "NotoSans-Medium.ttf"
_FONT_SEMI = _FONTS / "NotoSans-SemiBold.ttf"

WHITE = (255, 255, 255)
GREY = (132, 142, 156)
GREEN = (14, 203, 129)
RED = (246, 70, 93)
ORANGE = (246, 166, 64)
BG = (0, 0, 0)

SHARE_LEVERAGE = int(os.getenv("OPEN_POS_LEVERAGE", os.getenv("PROFIT_CARD_LEVERAGE", "15")) or "15")


def _font(size: int, bold: bool = False):
    path = _FONT_SEMI if bold else _FONT_MED
    for p in (
        path,
        _FONT_REG,
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if p and os.path.exists(str(p)):
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _coin(symbol: str) -> str:
    return symbol.replace("/USDT", "").replace("USDT", "").upper()


def _fmt_bybit(v: float, max_decimals: int = 4) -> str:
    n = float(v)
    if abs(n) >= 1000:
        return f"{n:.2f}"
    if abs(n) >= 100:
        return f"{n:.2f}"
    if abs(n) >= 1:
        s = f"{n:.{max_decimals}f}".rstrip("0").rstrip(".")
        return s if "." in s else s + ".0"
    return f"{n:.6f}".rstrip("0").rstrip(".")


def _fmt_bingx_price(v: float) -> str:
    """BingX RU: пробел — тысячи, запятая — десятичная."""
    n = float(v)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1000:
        whole = int(n)
        frac = n - whole
        w = f"{whole:,}".replace(",", " ")
        return f"{sign}{w},{f'{frac:.2f}'[2:]}"
    if n >= 1:
        return f"{sign}{n:.2f}".replace(".", ",")
    return f"{sign}{n:.4f}".rstrip("0").replace(".", ",")

def build_position_metrics(
    *,
    symbol: str,
    side: str,
    entry: float,
    leverage: int | None = None,
    stop: float | None = None,
    mark_price: float | None = None,
    margin: float | None = None,
) -> dict:
    """Реалистичные цифры открытой позиции (плечо + mark → PnL/ROI)."""
    side = (side or "LONG").upper()
    lev = int(leverage or SHARE_LEVERAGE)
    entry = float(entry)
    rng = random.Random(f"{_coin(symbol)}:{side}:{round(entry, 6)}:{lev}")

    if mark_price is not None and float(mark_price) > 0:
        mark = float(mark_price)
        if side == "LONG":
            move_pct = (mark - entry) / entry
        else:
            move_pct = (entry - mark) / entry
    else:
        # небольшое движение цены в нашу сторону (0.3% … 1.8% без плеча)
        move_pct = rng.uniform(0.004, 0.018)
        if side == "LONG":
            mark = entry * (1 + move_pct)
        else:
            mark = entry * (1 - move_pct)

    if side == "LONG":
        liq = entry * (1 - 0.85 / max(lev, 1))
    else:
        liq = entry * (1 + 0.85 / max(lev, 1))

    if stop and float(stop) > 0:
        sl = float(stop)
    else:
        sl = entry * (0.97 if side == "LONG" else 1.03)

    # маржа ~ 5–25 USDT, notional = margin * lev
    if margin is None or float(margin) <= 0:
        margin = rng.uniform(5.5, 22.0)
    else:
        margin = float(margin)
    notional = margin * lev
    holdings = notional  # в USDT на Bybit «Холдинги»
    pnl_usdt = notional * move_pct
    roi_pct = move_pct * lev * 100.0
    margin_ratio = rng.uniform(8.0, 22.0)
    realized = -rng.uniform(0.01, 0.08)  # комиссия

    return {
        "symbol": _coin(symbol),
        "pair": f"{_coin(symbol)}USDT",
        "side": side,
        "leverage": lev,
        "entry": entry,
        "mark": mark,
        "liq": liq,
        "sl": sl,
        "margin": margin,
        "holdings": holdings,
        "pnl_usdt": pnl_usdt,
        "roi_pct": roi_pct,
        "margin_ratio": margin_ratio,
        "realized": realized,
        "style": "bingx",
    }


def _open_edit_prompt(m: dict, style: str) -> str:
    is_long = m["side"] == "LONG"
    side_ru = "Лонг" if is_long else "Шорт"
    side_letter = "B" if is_long else "S"
    pnl = m["pnl_usdt"]
    roi = m["roi_pct"]
    pnl_s = f"+{pnl:.4f}" if pnl >= 0 else f"{pnl:.4f}"
    roi_s = f"+{roi:.2f}%" if roi >= 0 else f"{roi:.2f}%"
    dollar = f"≈ +${abs(pnl):.3f}" if pnl >= 0 else f"≈ −${abs(pnl):.3f}"

    if style == "bybit":
        return (
            "You are editing a Bybit mobile open-position screenshot (Russian UI).\n"
            "CRITICAL RULES:\n"
            "- Change ONLY the numeric text values and the side badge text/color.\n"
            "- Do NOT redraw, move, or modify any UI elements, buttons, icons, layout, or background.\n"
            "- Do NOT add black boxes, rectangles, or overlays.\n"
            "- Keep all original fonts, sizes, spacing, and alignment EXACTLY as in the template.\n"
            "- Keep the EXACT same resolution and sharpness as the input. Do NOT re-render, upscale, downscale, or redraw the screenshot.\n"
            "- Change ONLY the glyph pixels of the listed numbers/labels; leave every other pixel untouched.\n"
            "- For color changes: Long/Лонг badge = bright green (#0ECB81). Short/Шорт badge = red/pink.\n"
            "- Positive PnL/ROI = green. Negative = red. Liquidation price = orange.\n"
            "\n"
            "Replace ONLY these specific text values with EXACT values below:\n"
            f"1. Top left pair name: {m['pair']}\n"
            f"2. Side badge text: {side_ru} (color: {'green' if is_long else 'red'})\n"
            f"3. Leverage number: {m['leverage']}X\n"
            f"4. Large PnL value (center): {pnl_s}\n"
            f"5. Small dollar approximation below PnL: {dollar}\n"
            f"6. ROI percentage (top right): {roi_s}\n"
            f"7. Холдинги (USDT) value: {_fmt_bybit(m['holdings'], 3)}\n"
            f"8. Маржа (USDT) value: {_fmt_bybit(m['margin'], 4)}\n"
            f"9. Коэффициент маржи value: {m['margin_ratio']:.2f}%\n"
            f"10. Цена открытия value: {_fmt_bybit(m['entry'])}\n"
            f"11. Цена маркировки value: {_fmt_bybit(m['mark'])}\n"
            f"12. Прогн. цена ликв. value (orange text): {_fmt_bybit(m['liq'])}\n"
            f"13. Реализованный PnL value (red text): {m['realized']:.8f}\n"
            f"14. Позиция TP/SL value: -- / {_fmt_bybit(m['sl'])}\n"
            "\n"
            "IMPORTANT: Use EXACT decimal formatting as shown above. Do NOT round differently.\n"
            "Return only the edited image with changed text values. No explanations."
        )

    # bingx
    pnl_bing = f"+{pnl:.4f}".replace(".", ",") if pnl >= 0 else f"{pnl:.4f}".replace(".", ",")
    roi_bing = f"+{roi:.2f}%".replace(".", ",") if roi >= 0 else f"{roi:.2f}%".replace(".", ",")
    return (
        "You are editing a BingX mobile open-position screenshot (Russian UI).\n"
        "CRITICAL RULES:\n"
        "- Change ONLY the numeric text values, side letter, and side icon color.\n"
        "- Do NOT redraw, move, or modify any UI elements, buttons, icons, or background.\n"
        "- Do NOT add black boxes or overlays.\n"
        "- Keep all original fonts, sizes, spacing EXACTLY as in template.\n"
        "- Side icon: B in green square for Long, S in red square for Short.\n"
        "- Positive PnL = green text. Negative = red text.\n"
        "- BingX Russian format: space as thousands separator, comma as decimal (e.g. 1 572,85).\n"
        "\n"
        "Replace ONLY these text values with EXACT values below:\n"
        f"1. Side icon letter: {side_letter} (color: {'green square background' if is_long else 'red square background'})\n"
        f"2. Title line: {m['pair']} Бессрочный\n"
        f"3. Leverage pill text: Кросс {m['leverage']}X\n"
        f"4. Нереализованный PNL line: {pnl_bing} [{roi_bing}]\n"
        f"5. Кол-во позиции (USDT): {_fmt_bingx_price(m['holdings'])}\n"
        f"6. Маржа (USDT): {_fmt_bingx_price(m['margin'])}\n"
        f"7. Коэффициент маржи: {m['margin_ratio']:.2f}%\n".replace(".", ",")
        + f"8. Ср. цена: {_fmt_bingx_price(m['entry'])}\n"
        f"9. Справедл. цена: {_fmt_bingx_price(m['mark'])}\n"
        f"10. Цена ликв.: {_fmt_bingx_price(m['liq'])}\n"
        "\n"
        "IMPORTANT: Use EXACT formatting as shown (spaces for thousands, commas for decimals).\n"
        "Return only the edited image. No explanations."
    )


def _sample_bg(img: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    """Цвет заливки из пикселей рамки бокса — без чёрных прямоугольников."""
    x0, y0, x1, y1 = box
    w, h = img.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    pts = []
    for x, y in (
        (x0, y0), (x1 - 1, y0), (x0, y1 - 1), (x1 - 1, y1 - 1),
        ((x0 + x1) // 2, y0), ((x0 + x1) // 2, y1 - 1),
        (x0, (y0 + y1) // 2), (x1 - 1, (y0 + y1) // 2),
    ):
        if 0 <= x < w and 0 <= y < h:
            pts.append(img.getpixel((x, y))[:3])
    if not pts:
        return BG
    # медиана по каналам
    pts.sort(key=lambda c: sum(c))
    return pts[len(pts) // 2]


def _clear_sampled(img: Image.Image, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]):
    draw.rectangle(box, fill=_sample_bg(img, box))


def _render_bybit_pil(m: dict) -> bytes:
    """PIL overlay на Bybit HQ-шаблоне — только цифры, фон сэмплируется с исходника."""
    path = _template_path("bybit")
    img = Image.open(path).convert("RGB")
    base = img.copy()  # для сэмпла фона до правок
    draw = ImageDraw.Draw(img)
    is_long = m["side"] == "LONG"
    side_ru = "Лонг" if is_long else "Шорт"
    side_bg = GREEN if is_long else RED
    pnl = m["pnl_usdt"]
    roi = m["roi_pct"]
    pnl_color = GREEN if pnl >= 0 else RED
    pnl_s = f"+{pnl:.4f}" if pnl >= 0 else f"{pnl:.4f}"
    roi_s = f"+{roi:.2f}%" if roi >= 0 else f"{roi:.2f}%"
    dollar = f"≈ +${abs(pnl):.3f}" if pnl >= 0 else f"≈ −${abs(pnl):.3f}"

    def put(box, text, font, fill, align="left"):
        _clear_sampled(base, draw, box)
        x0, y0, x1, y1 = box
        if align == "right":
            tw = draw.textlength(text, font=font)
            draw.text((x1 - tw - 3, y0 + 1), text, font=font, fill=fill)
        else:
            draw.text((x0 + 3, y0 + 1), text, font=font, fill=fill)

    # pair (XRPUSDT) — верхний левый угол
    put((48, 32, 350, 78), m["pair"], _font(40, bold=True), WHITE)

    # side badge (Лонг/Шорт) зеленый/красный прямоугольник
    badge = (48, 102, 144, 148)
    draw.rectangle(badge, fill=side_bg)
    font_b = _font(22, bold=True)
    tw = draw.textlength(side_ru, font=font_b)
    draw.text((48 + (96 - tw) / 2, 113), side_ru, font=font_b, fill=WHITE)

    # leverage (15X) — справа от badge, только цифру меняем
    put((288, 110, 348, 143), f"{m['leverage']}X", _font(20), (195, 195, 195))

    # PnL (большая зеленая/красная цифра в центре)
    put((48, 248, 330, 298), pnl_s, _font(46, bold=True), pnl_color)
    # $ approximation (мелкий серый текст под PnL)
    put((48, 302, 240, 336), dollar, _font(18), GREY)

    # ROI (процент справа вверху)
    put((855, 253, 1140, 302), roi_s, _font(34, bold=True), pnl_color, align="right")

    # holdings / margin / margin_ratio (первая строка цифр)
    put((48, 448, 225, 488), _fmt_bybit(m["holdings"], 3), _font(26, bold=True), WHITE)
    put((402, 448, 565, 488), _fmt_bybit(m["margin"], 4), _font(26, bold=True), WHITE)
    put((982, 448, 1140, 488), f"{m['margin_ratio']:.2f}%", _font(26, bold=True), WHITE, align="right")

    # entry / mark / liq (вторая строка цифр)
    put((48, 588, 205, 628), _fmt_bybit(m["entry"]), _font(26, bold=True), WHITE)
    put((402, 588, 565, 628), _fmt_bybit(m["mark"]), _font(26, bold=True), WHITE)
    put((982, 588, 1140, 628), _fmt_bybit(m["liq"]), _font(26, bold=True), ORANGE, align="right")

    # realized PnL (мелкий красный текст)
    put((885, 703, 1110, 732), f"{m['realized']:.8f}", _font(18), RED, align="right")

    # TP/SL (последняя строка)
    tpsl = f"-- / {_fmt_bybit(m['sl'])}"
    put((885, 758, 1065, 792), tpsl, _font(20), WHITE, align="right")

    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=3)
    return buf.getvalue()


def _render_bingx_pil(m: dict) -> bytes:
    """PIL overlay на BingX HQ-шаблоне."""
    path = _template_path("bingx")
    img = Image.open(path).convert("RGB")
    base = img.copy()
    draw = ImageDraw.Draw(img)
    W, H = img.size
    is_long = m["side"] == "LONG"
    pnl = m["pnl_usdt"]
    roi = m["roi_pct"]
    color = GREEN if pnl >= 0 else RED
    pnl_line = (
        f"+{pnl:.4f} [+{roi:.2f}%]".replace(".", ",")
        if pnl >= 0
        else f"{pnl:.4f} [{roi:.2f}%]".replace(".", ",")
    )

    def put(box, text, font, fill, align="left"):
        _clear_sampled(base, draw, box)
        x0, y0, x1, y1 = box
        if align == "right":
            tw = draw.textlength(text, font=font)
            draw.text((x1 - tw - 3, y0 + 1), text, font=font, fill=fill)
        else:
            draw.text((x0 + 3, y0 + 1), text, font=font, fill=fill)

    # side letter (B/S в квадрате)
    sx0, sy0 = 50, 50
    draw.rectangle((sx0, sy0, sx0 + 54, sy0 + 54), fill=GREEN if is_long else RED)
    draw.text((sx0 + 13, sy0 + 5), "B" if is_long else "S", font=_font(36, bold=True), fill=WHITE)

    # заголовок и leverage
    put((122, 50, 785, 98), f"{m['pair']} Бессрочный", _font(34, bold=True), WHITE)
    put((122, 108, 385, 148), f"Кросс {m['leverage']}X >", _font(24), GREY)

    # PnL line (right-aligned)
    put((525, 203, 1160, 278), pnl_line, _font(40, bold=True), color, align="right")

    # три колонки данных
    cols = [50, 432, 822]
    y1, y2 = 382, 522
    row1 = [
        _fmt_bingx_price(m["holdings"]),
        _fmt_bingx_price(m["margin"]),
        f"{m['margin_ratio']:.2f}%".replace(".", ","),
    ]
    row2 = [
        _fmt_bingx_price(m["entry"]),
        _fmt_bingx_price(m["mark"]),
        _fmt_bingx_price(m["liq"]),
    ]
    for i, text in enumerate(row1):
        put((cols[i], y1, cols[i] + 278, y1 + 48), text, _font(30, bold=True), WHITE)
    for i, text in enumerate(row2):
        fill = ORANGE if i == 2 else WHITE
        put((cols[i], y2, cols[i] + 278, y2 + 48), text, _font(30, bold=True), fill)

    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=3)
    return buf.getvalue()

def render_open_position_card(
    symbol: str,
    side: str,
    entry: float,
    leverage: int | None = None,
    stop: float | None = None,
    style: str | None = None,
    mark_price: float | None = None,
    margin: float | None = None,
) -> bytes:
    """
    PNG открытой позиции под монету.
    style: 'bybit' | 'bingx' | None (случайный по seed).
    """
    m = build_position_metrics(
        symbol=symbol,
        side=side,
        entry=entry,
        leverage=leverage,
        stop=stop,
        mark_price=mark_price,
        margin=margin,
    )
    # Только BingX (чёрный фон — без видимых артефактов AI)
    forced = (os.getenv("OPEN_POS_STYLE", "bingx") or "bingx").strip().lower()
    use_style = (style or forced or m["style"] or "bingx").lower()
    if use_style != "bingx":
        use_style = "bingx"
    m["style"] = use_style

    path = _template_path(use_style)
    if not path.exists():
        raise FileNotFoundError(f"Нет шаблона open position: {path}")

    # AI по умолчанию включён — дешёвая flash-lite модель
    use_ai = os.getenv("OPEN_POS_AI", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if use_ai:
        try:
            import ai_client

            media = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            edited = ai_client.edit_image_bytes_sync(
                image_bytes=path.read_bytes(),
                prompt=_open_edit_prompt(m, use_style),
                media_type=media,
                model=os.getenv("OPENROUTER_MODEL_IMAGE_EDIT", "google/gemini-3.1-flash-lite-image"),
                timeout=float(os.getenv("OPEN_POS_AI_TIMEOUT", "120") or "120"),
                preserve_source=True,
            )
            img = Image.open(io.BytesIO(edited))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG", compress_level=6)
            return buf.getvalue()
        except Exception as e:
            print(f"[open_position_card] AI edit failed ({use_style}): {e} — fallback PIL")

    if use_style == "bingx":
        return _render_bingx_pil(m)
    return _render_bybit_pil(m)
