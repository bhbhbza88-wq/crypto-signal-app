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
BYBIT_PATH = _ASSETS / "bybit.jpg"
BINGX_PATH = _ASSETS / "bingx.jpg"

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
) -> dict:
    """Реалистичные цифры «только что открыли / уже чуть в плюсе»."""
    side = (side or "LONG").upper()
    lev = int(leverage or SHARE_LEVERAGE)
    entry = float(entry)
    rng = random.Random(f"{_coin(symbol)}:{side}:{round(entry, 6)}:{lev}")

    # небольшое движение цены в нашу сторону (0.3% … 1.8% без плеча)
    move_pct = rng.uniform(0.004, 0.018)
    if side == "LONG":
        mark = entry * (1 + move_pct)
        liq = entry * (1 - 0.85 / max(lev, 1))
    else:
        mark = entry * (1 - move_pct)
        liq = entry * (1 + 0.85 / max(lev, 1))

    if stop and float(stop) > 0:
        # SL на карточке чуть ближе к стопу сигнала
        sl = float(stop)
    else:
        sl = entry * (0.97 if side == "LONG" else 1.03)

    # маржа ~ 5–25 USDT, notional = margin * lev
    margin = rng.uniform(5.5, 22.0)
    notional = margin * lev
    holdings = notional  # в USDT на Bybit «Холдинги»
    pnl_usdt = notional * move_pct if side == "LONG" else notional * move_pct
    # для short move_pct уже «в нашу сторону»
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
        "style": "bybit" if rng.random() < 0.55 else "bingx",
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


def _clear(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill=BG):
    draw.rectangle(box, fill=fill)


def _render_bybit_pil(m: dict) -> bytes:
    """PIL overlay на Bybit-шаблоне (1179×996). Координаты откалиброваны по bands."""
    img = Image.open(BYBIT_PATH).convert("RGB")
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
        _clear(draw, box)
        x0, y0, x1, y1 = box
        if align == "right":
            tw = draw.textlength(text, font=font)
            draw.text((x1 - tw - 4, y0 + 2), text, font=font, fill=fill)
        else:
            draw.text((x0 + 2, y0 + 2), text, font=font, fill=fill)

    # symbol
    put((30, 30, 560, 95), m["pair"], _font(40, bold=True), WHITE)

    # side badge — только бейдж, не трогаем «Кросс»
    _clear(draw, (34, 105, 155, 155), fill=side_bg)
    draw.text((50, 114), side_ru, font=_font(22, bold=True), fill=WHITE)

    # leverage number only (оставляем «Кросс» и иконку карандаша)
    put((248, 110, 340, 152), f"{m['leverage']}X", _font(22), GREY)

    # unrealized pnl + approx $
    put((30, 215, 430, 285), pnl_s, _font(46, bold=True), pnl_color)
    put((30, 288, 300, 325), dollar, _font(20), GREY)

    # ROI right-aligned
    put((780, 220, 1145, 285), roi_s, _font(34, bold=True), pnl_color, align="right")

    # holdings / margin / ratio (values ~ y 430–475)
    put((30, 425, 300, 480), _fmt_bybit(m["holdings"], 3), _font(28, bold=True), WHITE)
    put((350, 425, 620, 480), _fmt_bybit(m["margin"], 4), _font(28, bold=True), WHITE)
    put((820, 425, 1145, 480), f"{m['margin_ratio']:.2f}%", _font(28, bold=True), WHITE, align="right")

    # entry / mark / liq (values ~ y 575–635)
    put((30, 575, 320, 640), _fmt_bybit(m["entry"]), _font(28, bold=True), WHITE)
    put((350, 575, 650, 640), _fmt_bybit(m["mark"]), _font(28, bold=True), WHITE)
    put((800, 575, 1145, 640), _fmt_bybit(m["liq"]), _font(28, bold=True), ORANGE, align="right")

    # realized pnl
    put((780, 665, 1145, 710), f"{m['realized']:.8f}", _font(20), RED, align="right")

    # TP/SL
    tpsl = f"-- / {_fmt_bybit(m['sl'])}"
    put((780, 730, 1100, 775), tpsl, _font(22), WHITE, align="right")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _render_bingx_pil(m: dict) -> bytes:
    """Грубый PIL fallback для BingX (лучше AI)."""
    img = Image.open(BINGX_PATH).convert("RGB")
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

    # side letter box ~ top-left of position block
    sx0, sy0 = int(W * 0.04), int(H * 0.18)
    _clear(draw, (sx0, sy0, sx0 + 70, sy0 + 70), fill=GREEN if is_long else RED)
    draw.text((sx0 + 18, sy0 + 12), "B" if is_long else "S", font=_font(42, bold=True), fill=WHITE)

    # title
    _clear(draw, (sx0 + 90, sy0, int(W * 0.75), sy0 + 55))
    draw.text((sx0 + 95, sy0 + 5), f"{m['pair']} Бессрочный", font=_font(40, bold=True), fill=WHITE)

    # leverage pill text
    _clear(draw, (sx0 + 90, sy0 + 60, sx0 + 420, sy0 + 110))
    draw.text((sx0 + 100, sy0 + 68), f"Кросс {m['leverage']}X >", font=_font(26), fill=GREY)

    # pnl
    _clear(draw, (sx0, sy0 + 160, int(W * 0.85), sy0 + 260))
    draw.text((sx0, sy0 + 170), pnl_line, font=_font(56, bold=True), fill=color)

    # grid values — approximate thirds
    cols = [sx0, int(W * 0.36), int(W * 0.66)]
    y1, y2 = sy0 + 360, sy0 + 520
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
        _clear(draw, (cols[i], y1, cols[i] + 280, y1 + 55))
        draw.text((cols[i], y1 + 5), text, font=_font(34, bold=True), fill=WHITE)
    for i, text in enumerate(row2):
        _clear(draw, (cols[i], y2, cols[i] + 280, y2 + 55))
        draw.text((cols[i], y2 + 5), text, font=_font(34, bold=True), fill=WHITE)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_open_position_card(
    symbol: str,
    side: str,
    entry: float,
    leverage: int | None = None,
    stop: float | None = None,
    style: str | None = None,
) -> bytes:
    """
    PNG открытой позиции под монету.
    style: 'bybit' | 'bingx' | None (случайный по seed).
    """
    m = build_position_metrics(
        symbol=symbol, side=side, entry=entry, leverage=leverage, stop=stop
    )
    use_style = (style or m["style"]).lower()
    if use_style not in ("bybit", "bingx"):
        use_style = "bybit"
    m["style"] = use_style

    path = BYBIT_PATH if use_style == "bybit" else BINGX_PATH
    if not path.exists():
        raise FileNotFoundError(f"Нет шаблона open position: {path}")

    use_ai = os.getenv("OPEN_POS_AI", os.getenv("PROFIT_CARD_AI", "0")).strip().lower() in (
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
                timeout=float(os.getenv("OPEN_POS_AI_TIMEOUT", "120") or "120"),
            )
            img = Image.open(io.BytesIO(edited)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
        except Exception as e:
            print(f"[open_position_card] AI edit failed ({use_style}): {e} — fallback PIL")

    if use_style == "bingx":
        return _render_bingx_pil(m)
    return _render_bybit_pil(m)
