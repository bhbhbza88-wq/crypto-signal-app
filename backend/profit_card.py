"""
Карточка закрытия: пул реальных шарингов (Bitunix / BingX / Binance).
Текст сделки меняет AI image-edit (Gemini Flash Image via OpenRouter) —
без чёрных прямоугольников поверх арта. PIL-оверлей — только fallback.
"""

from __future__ import annotations

import io
import json
import os
import random
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHARE_LEVERAGE = int(os.getenv("PROFIT_CARD_LEVERAGE", "15"))

# re-export for any old imports
from display_polish import polish_pnl  # noqa: E402
PNL_SHOW_MULT = float(os.getenv("PNL_WIN_MULT", "1.22") or "1.22")

_ASSETS = Path(__file__).resolve().parent / "assets"
BG_PATH = _ASSETS / "pnl_card_bg.png"
BYBIT_BG_PATH = _ASSETS / "bybit_pnl_card_bg.png"
TEMPLATES_DIR = _ASSETS / "pnl_templates"
MANIFEST_PATH = TEMPLATES_DIR / "manifest.json"
_FONT_REG = _ASSETS / "fonts" / "NotoSans-Regular.ttf"
_FONT_MED = _ASSETS / "fonts" / "NotoSans-Medium.ttf"
_FONT_SEMI = _ASSETS / "fonts" / "NotoSans-SemiBold.ttf"
_FONT_REG_LEGACY = _ASSETS / "fonts" / "card-regular.ttf"
_FONT_BOLD_LEGACY = _ASSETS / "fonts" / "card-bold.ttf"

WHITE = (255, 255, 255)
GREY = (132, 142, 156)
GREEN = (14, 203, 129)
RED = (246, 70, 93)
BINGX_PINK = (255, 77, 141)


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False, weight: str | None = None):
    """Кириллица: Noto Sans. weight=regular|medium|semibold; bold=True → semibold (не Heavy)."""
    w = (weight or ("semibold" if bold else "regular")).lower()
    if w in ("bold", "heavy", "black"):
        w = "semibold"
    bundled = {
        "regular": _FONT_REG,
        "medium": _FONT_MED,
        "semibold": _FONT_SEMI,
    }.get(w, _FONT_REG)
    legacy = _FONT_BOLD_LEGACY if w != "regular" else _FONT_REG_LEGACY
    win = {
        "regular": r"C:\Windows\Fonts\segoeui.ttf",
        "medium": r"C:\Windows\Fonts\seguisb.ttf",
        "semibold": r"C:\Windows\Fonts\seguisb.ttf",
    }.get(w, r"C:\Windows\Fonts\segoeui.ttf")
    candidates = [
        str(bundled),
        str(legacy),
        f"/usr/share/fonts/truetype/noto/NotoSans-{w.capitalize()}.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        win,
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    raise RuntimeError(
        "Нет TTF с кириллицей для profit_card. "
        "Нужны NotoSans-Regular/Medium/SemiBold в backend/assets/fonts/"
    )


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
        return f"{n:.7f}"
    return f"{n:.8f}"


def _fmt_share_price(v: float) -> str:
    n = float(v)
    if n >= 100:
        s = f"{n:.2f}"
    elif n >= 1:
        s = f"{n:.4f}"
    elif n >= 0.1:
        s = f"{n:.5f}"
    elif n >= 0.01:
        s = f"{n:.5f}"
    else:
        s = f"{n:.6f}"
    if "." in s:
        s = s.rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def _exit_from_pnl(side: str, entry: float, pnl_pct: float) -> float:
    if side.upper() == "LONG":
        return entry * (1 + pnl_pct / 100.0)
    return entry * (1 - pnl_pct / 100.0)


@lru_cache(maxsize=1)
def _load_bg() -> Image.Image:
    if not BG_PATH.exists():
        raise FileNotFoundError(f"Нет фона карточки: {BG_PATH}")
    return Image.open(BG_PATH).convert("RGB")


def _bg_for_text() -> Image.Image:
    return _load_bg().copy()


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
    roi = round(show_pnl * leverage, 2)

    coin = symbol.replace("/USDT", "").replace("USDT", "").upper()
    pair_line = f"{coin}USDT Бессрочный"
    side_ru = "Лонг" if side == "LONG" else "Шорт"
    side_color = GREEN if side == "LONG" else RED
    roi_color = GREEN if roi >= 0 else RED
    roi_str = f"+{roi:.2f}%" if roi >= 0 else f"{roi:.2f}%"

    img = _bg_for_text()
    W, H = img.size
    draw = ImageDraw.Draw(img)

    pad = int(W * 0.070)
    text_max_w = max(120, int(W * 0.52) - pad)
    col2_x = int(W * 0.48)

    def fit_font(
        text: str, start: int, bold: bool = False, min_size: int = 14, weight: str | None = None,
    ) -> ImageFont.FreeTypeFont:
        size = start
        while size >= min_size:
            f = _font(size, bold=bold, weight=weight)
            if draw.textlength(text, font=f) <= text_max_w:
                return f
            size -= 1
        return _font(min_size, bold=bold, weight=weight)

    font_pair = fit_font(pair_line, max(22, int(H * 0.034)), bold=False, min_size=14)
    font_side = _font(max(16, int(H * 0.026)), weight="regular")
    font_roi = fit_font(roi_str, max(40, int(H * 0.082)), bold=True, min_size=20)
    font_label = _font(max(14, int(H * 0.022)), weight="regular")
    font_val = _font(max(18, int(H * 0.028)), weight="medium")

    y_pair = int(H * 0.235)
    y_side = int(H * 0.300)
    y_roi = int(H * 0.430)
    y_lab = int(H * 0.665)
    y_val = int(H * 0.720)

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


# ── Пул шаблонов Bitunix / BingX / Binance (только текст поверх фото) ──

@lru_cache(maxsize=1)
def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"layouts": {}, "templates": []}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def list_share_templates(family: str | None = None) -> list[dict]:
    items = list(_load_manifest().get("templates") or [])
    if family:
        fam = family.lower().strip()
        items = [t for t in items if t.get("family") == fam]
    return items


def _sample_fill(img: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0)
    crop = img.crop((x0, y0, x1, y1)).resize((1, 1), Image.Resampling.BOX)
    return crop.getpixel((0, 0))[:3]


def _px(frac: float, total: int) -> int:
    return int(round(frac * total))


# Вымышленные ники для шарингов (не светим реальные User-*/email с шаблонов)
_FAKE_USERS = (
    "nova_rx", "apexloop", "orbitfox", "silverchart", "km_pulse",
    "driftline", "quark_tv", "northwire", "pixelbay", "frostedge",
    "lunatrade", "hexavolt", "cinderfx", "blueorbit", "zincwave",
)


def _fake_username(seed: str = "") -> str:
    import hashlib
    h = int(hashlib.md5((seed or "nowicki").encode()).hexdigest()[:8], 16)
    return _FAKE_USERS[h % len(_FAKE_USERS)]


# Footer crop отключён — оставляем карточку целиком (реф/QR как на шаблоне).
def _crop_share_footer(img: Image.Image, family: str) -> Image.Image:
    return img


def _pnl_edit_prompt(
    *,
    family: str,
    pair: str,
    side: str,
    leverage: int,
    roi_str: str,
    entry_str: str,
    exit_str: str,
    fake_user: str,
) -> str:
    is_long = side.upper() == "LONG"
    side_ru = "Лонг" if is_long else "Шорт"
    return (
        "You are editing a BingX PnL share screenshot from the owner's personal account.\n"
        "CRITICAL RULES:\n"
        "- Change ONLY the trade data text (pair, side, leverage, PnL %, prices, date).\n"
        "- Do NOT redraw, crop, stretch, or cover the artwork/mascot.\n"
        "- Do NOT add black rectangles, panels, or overlays.\n"
        "- Keep BingX logo, mascot artwork, layout, fonts and native look.\n"
        "- ALL TEXT MUST BE IN RUSSIAN.\n"
        "- Side color MUST be: Лонг = bright green (#0ECB81). "
        "Шорт = red/pink. Never paint Лонг in red/pink.\n"
        "- PnL % color: green if positive (+), red/pink if negative (−).\n"
        "\n"
        "KEEP FOOTER EXACTLY AS-IS (owner branding):\n"
        "- Keep email exactly: bh***8@gmail.com\n"
        "- Keep referral code exactly: A3NVWY\n"
        "- Keep the QR code unchanged\n"
        "- Keep the avatar/icon unchanged\n"
        "- Only update the date under the email to today's date MM-DD if needed\n"
        "\n"
        "Set the trade fields to EXACTLY these Russian labels + values:\n"
        "- Header: Нереализованная П/У\n"
        f"- Symbol/pair: {pair}\n"
        f"- Side: {side_ru}\n"
        f"- Leverage: {leverage}X\n"
        f"- Main PnL percent: {roi_str}\n"
        f"- Последняя цена {exit_str}\n"
        f"- Цена входа {entry_str}\n"
        "Return the edited image only."
    )


def render_template_card(
    template_file: str,
    family: str,
    symbol: str,
    side: str,
    entry: float,
    pnl_pct: float,
    exit_price: float | None = None,
    leverage: int | None = None,
) -> bytes:
    """Шаблон: AI меняет текст/ник (карточка целиком, без обрезки футера)."""
    side = (side or "LONG").upper()
    leverage = leverage or SHARE_LEVERAGE
    entry = float(entry)
    pnl_pct = float(pnl_pct)
    if exit_price is None:
        exit_price = _exit_from_pnl(side, entry, pnl_pct)
    else:
        exit_price = float(exit_price)

    path = TEMPLATES_DIR / template_file
    if not path.exists():
        raise FileNotFoundError(path)

    show_pnl = polish_pnl(pnl_pct, decimals=2)
    # polish_pnl уже включает плечо 15x — на карточке ROI = этот % (не умножать снова)
    roi = round(show_pnl, 2)
    coin = symbol.replace("/USDT", "").replace("USDT", "").upper()
    pair = f"{coin}USDT"
    roi_str = f"+{roi:.2f}%" if roi >= 0 else f"{roi:.2f}%"
    entry_str = _fmt_share_price(entry)
    exit_str = _fmt_share_price(exit_price)
    fake_user = _fake_username(f"{template_file}:{pair}:{side}:{leverage}")

    # Default OFF: Gemini/Flux image-edit burns OpenRouter credits fast.
    # Для BingX включаем дешёвую модель по умолчанию (чёрный фон скрывает артефакты).
    ai_default = "1" if family.lower() == "bingx" else "0"
    use_ai = os.getenv("PROFIT_CARD_AI", ai_default).strip().lower() in ("1", "true", "yes", "on")
    if use_ai:
        try:
            import ai_client

            # Prefer cheap flash-lite for BingX share cards
            prev_model = os.environ.get("OPENROUTER_MODEL_IMAGE_EDIT")
            if family.lower() == "bingx" and not prev_model:
                os.environ["OPENROUTER_MODEL_IMAGE_EDIT"] = "google/gemini-3.1-flash-lite-image"
            try:
                raw = path.read_bytes()
                # Prefer original HQ jpeg/png without recompress if available
                prompt = _pnl_edit_prompt(
                    family=family,
                    pair=pair,
                    side=side,
                    leverage=leverage,
                    roi_str=roi_str,
                    entry_str=entry_str,
                    exit_str=exit_str,
                    fake_user=fake_user,
                )
                edited = ai_client.edit_image_bytes_sync(
                    image_bytes=raw,
                    prompt=prompt,
                    media_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg",
                    timeout=float(os.getenv("PROFIT_CARD_AI_TIMEOUT", "120") or "120"),
                )
            finally:
                if prev_model is None and "OPENROUTER_MODEL_IMAGE_EDIT" in os.environ:
                    # leave set for session consistency on bingx
                    pass
            img = Image.open(io.BytesIO(edited)).convert("RGB")
            img = _crop_share_footer(img, family)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=False, compress_level=1)
            return buf.getvalue()
        except Exception as e:
            print(f"[profit_card] AI edit failed ({template_file}): {e} — fallback PIL")

    png = _render_template_card_pil(
        template_file=template_file,
        family=family,
        symbol=symbol,
        side=side,
        entry=entry,
        pnl_pct=pnl_pct,
        exit_price=exit_price,
        leverage=leverage,
    )
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img = _crop_share_footer(img, family)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _render_template_card_pil(
    template_file: str,
    family: str,
    symbol: str,
    side: str,
    entry: float,
    pnl_pct: float,
    exit_price: float | None = None,
    leverage: int | None = None,
) -> bytes:
    """Fallback: старый PIL-оверлей (только если AI недоступен)."""
    side = (side or "LONG").upper()
    leverage = leverage or SHARE_LEVERAGE
    entry = float(entry)
    pnl_pct = float(pnl_pct)
    if exit_price is None:
        exit_price = _exit_from_pnl(side, entry, pnl_pct)
    else:
        exit_price = float(exit_price)

    path = TEMPLATES_DIR / template_file
    layout = (_load_manifest().get("layouts") or {}).get(family) or {}
    if not layout:
        raise ValueError(f"нет layout для family={family}")

    show_pnl = polish_pnl(pnl_pct, decimals=2)
    roi = round(show_pnl, 2)  # polish_pnl уже с плечом
    coin = symbol.replace("/USDT", "").replace("USDT", "").upper()
    pair = f"{coin}USDT"
    is_long = side == "LONG"
    side_ru = "Лонг" if is_long else "Шорт"
    side_color = GREEN if is_long else (BINGX_PINK if family == "bingx" else RED)
    roi_color = GREEN if roi >= 0 else (BINGX_PINK if family == "bingx" else RED)
    roi_str = f"+{roi:.2f}%" if roi >= 0 else f"{roi:.2f}%"

    img = Image.open(path).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)

    clear_x1 = _px(float(layout.get("clear_x1", 0.52)), W)
    clear_y0 = _px(float(layout.get("clear_y0", 0.10 if family != "binance" else 0.20)), H)
    clear_y1 = _px(float(layout.get("clear_y1", 0.78 if family != "binance" else 0.78)), H)
    # Тёмный фон шарингов — чистый чёрный чище «жирной» подложки из сэмпла.
    fill = _sample_fill(img, (8, clear_y0, min(40, max(8, clear_x1 // 4)), clear_y1))
    if sum(fill) / 3 < 48:
        fill = (0, 0, 0)
    else:
        fill = tuple(max(0, min(255, c - 8)) for c in fill)

    if family == "binance":
        upper_x1 = _px(float(layout.get("clear_x1", 0.72)), W)
        prices_y0 = _px(float(layout.get("prices_clear_y0", 0.58)), H)
        draw.rectangle((0, clear_y0, upper_x1, prices_y0), fill=fill)
        draw.rectangle((0, prices_y0, W - 1, clear_y1), fill=fill)
    else:
        draw.rectangle((0, clear_y0, min(W - 1, clear_x1), clear_y1), fill=fill)

    def fxy(key, default=(0.06, 0.2)):
        xy = layout.get(key) or default
        return _px(float(xy[0]), W), _px(float(xy[1]), H)

    def fsize(key, default=0.04):
        return max(12, _px(float(layout.get(key, default)), H))

    # Лёгкий набор: Regular / Medium; ROI — SemiBold (не DejaVu Bold).
    font_pair = _font(fsize("pair_size", 0.034), weight="medium")
    font_side = _font(fsize("side_size", 0.024), weight="regular")
    font_roi = _font(fsize("roi_size", 0.078), weight="semibold")
    font_price = _font(fsize("price_size", 0.022), weight="regular")
    font_price_val = _font(fsize("price_size", 0.022), weight="medium")

    px, py = fxy("pair_xy")
    sx, sy = fxy("side_xy")
    rx, ry = fxy("roi_xy")
    p1x, p1y = fxy("price1_xy")
    p2x, p2y = fxy("price2_xy")

    if family == "binance":
        pair_line = f"{pair} Бессрочный"
        draw.text((px, py), pair_line, font=font_pair, fill=WHITE)
        draw.text((sx, sy), f"{side_ru} ", font=font_side, fill=side_color)
        sw = draw.textlength(f"{side_ru} ", font=font_side)
        draw.text((sx + sw, sy), f"| {leverage}x", font=font_side, fill=GREY)
        draw.text((rx, ry), roi_str, font=font_roi, fill=roi_color)
        font_lab = _font(fsize("label_size", 0.022), weight="regular")
        l1 = layout.get("label1_xy") or [0.07, 0.665]
        l2 = layout.get("label2_xy") or [0.48, 0.665]
        draw.text((_px(l1[0], W), _px(l1[1], H)), "Цена входа", font=font_lab, fill=GREY)
        draw.text((_px(l2[0], W), _px(l2[1], H)), "Средняя цена закрытия", font=font_lab, fill=GREY)
        draw.text((p1x, p1y), _fmt_price(entry).replace(".", ","), font=font_price_val, fill=WHITE)
        draw.text((p2x, p2y), _fmt_price(exit_price).replace(".", ","), font=font_price_val, fill=WHITE)
    elif family == "bitunix":
        draw.text((px, py), pair, font=font_pair, fill=WHITE)
        pair_w = draw.textlength(pair, font=font_pair)
        sep = " | "
        draw.text((px + pair_w, py), sep, font=font_pair, fill=WHITE)
        sep_w = draw.textlength(sep, font=font_pair)
        side_line = f"{side_ru} {leverage}X"
        draw.text((px + pair_w + sep_w, py), side_line, font=font_pair, fill=side_color)
        draw.text((rx, ry), roi_str, font=font_roi, fill=roi_color)
        e_s, x_s = _fmt_share_price(entry), _fmt_share_price(exit_price)
        draw.text((p1x, p1y), f"Цена открытия {e_s}", font=font_price, fill=WHITE)
        draw.text((p2x, p2y), f"Цена закрытия {x_s}", font=font_price, fill=WHITE)
    else:
        # BingX-style
        if "header_xy" in layout:
            hx, hy = fxy("header_xy")
            font_h = _font(fsize("header_size", 0.022), weight="regular")
            draw.text((hx, hy), "Реализованная П/У", font=font_h, fill=(168, 168, 168))
        draw.text((px, py), pair, font=font_pair, fill=WHITE)
        draw.text((sx, sy), side_ru, font=font_side, fill=side_color)
        sw = draw.textlength(side_ru, font=font_side)
        draw.text((sx + sw + 10, sy), f"|  {leverage}X", font=font_side, fill=(200, 200, 200))
        draw.text((rx, ry), roi_str, font=font_roi, fill=roi_color)
        e_s, x_s = _fmt_share_price(entry), _fmt_share_price(exit_price)
        font_lab = _font(fsize("price_size", 0.022), weight="regular")
        draw.text((p1x, p1y), "Цена закрытия", font=font_lab, fill=GREY)
        lab_w = draw.textlength("Цена закрытия  ", font=font_lab)
        draw.text((p1x + lab_w, p1y), x_s, font=font_price_val, fill=WHITE)
        draw.text((p2x, p2y), "Цена входа", font=font_lab, fill=GREY)
        lab2_w = draw.textlength("Цена входа  ", font=font_lab)
        draw.text((p2x + lab2_w, p2y), e_s, font=font_price_val, fill=WHITE)

        if layout.get("footer_clear") and layout.get("footer_clear_box"):
            box = layout["footer_clear_box"]
            fx0, fy0 = _px(float(box[0]), W), _px(float(box[1]), H)
            fx1, fy1 = _px(float(box[2]), W), _px(float(box[3]), H)
            draw.rectangle((fx0, fy0, fx1, fy1), fill=(0, 0, 0))
            fpx, fpy = fxy("footer_xy", (0.11, 0.905))
            font_f = _font(fsize("footer_size", 0.022), weight="medium")
            draw.text((fpx, fpy), pair, font=font_f, fill=WHITE)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_share_card(
    symbol: str,
    side: str,
    entry: float,
    pnl_pct: float,
    exit_price: float | None = None,
    leverage: int | None = None,
    family: str | None = None,
    template_file: str | None = None,
) -> bytes:
    """ТОЛЬКО 2 карточки пользователя: bingx_close_win / bingx_close_loss."""
    win = float(pnl_pct) >= 0
    if template_file:
        pick_file = template_file
    elif win:
        pick_file = "bingx_close_win.png"   # улыбающийся маскот, зелёная кепка
    else:
        pick_file = "bingx_close_loss.png"  # плачущий маскот, красный козырёк

    try:
        return render_template_card(
            template_file=pick_file,
            family="bingx",
            symbol=symbol,
            side=side,
            entry=entry,
            pnl_pct=pnl_pct,
            exit_price=exit_price,
            leverage=leverage or SHARE_LEVERAGE,
        )
    except Exception as e:
        print(f"[profit_card] template {pick_file} failed: {e}")
        return render_profit_card(
            symbol=symbol, side=side, entry=entry, pnl_pct=pnl_pct,
            exit_price=exit_price, leverage=leverage,
        )


# ── Bybit-style карточка ─────────────────────────────────────────────
_BYBIT_ROW_SYMBOL_Y = (180, 226)
_BYBIT_ROW_PNL_Y = (312, 388)
_BYBIT_ROW_ENTRY_Y = (474, 513)
_BYBIT_ROW_EXIT_Y = (574, 613)
_BYBIT_ROW_DURATION_Y = (669, 718)
_BYBIT_MIN_CLEAR_X = {"symbol": 409, "pnl": 268, "entry": 139, "exit": 151, "duration": 249}
_BYBIT_X0 = 30
_BYBIT_SYMBOL_XY = (50, 183)
_BYBIT_PILL_Y = (186, 222)
_BYBIT_PILL_GAP = 14
_BYBIT_PNL_XY = (53, 316)
_BYBIT_ENTRY_XY = (48, 477)
_BYBIT_EXIT_XY = (48, 577)
_BYBIT_DURATION_XY = (49, 675)
_BYBIT_CROP_H = 838


@lru_cache(maxsize=1)
def _load_bybit_bg() -> Image.Image:
    if not BYBIT_BG_PATH.exists():
        raise FileNotFoundError(f"Нет фона Bybit-карточки: {BYBIT_BG_PATH}")
    return Image.open(BYBIT_BG_PATH).convert("RGB")


def _draw_topleft(draw, xy, text, font, fill) -> tuple[int, int]:
    x, y = xy
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text((x - l, y - t), text, font=font, fill=fill)
    return (r - l, b - t)


def _fmt_bybit_price(v: float) -> str:
    n = float(v)
    if n >= 1000:
        s = f"{n:.2f}"
    elif n >= 1:
        s = f"{n:.4f}"
    elif n >= 0.01:
        s = f"{n:.6f}"
    else:
        s = f"{n:.8f}"
    if "." in s:
        s = s.rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def fmt_duration_ru(total_minutes: float) -> str:
    m = max(1, int(round(total_minutes)))
    if m < 60:
        return f"{m} мин."
    hours, mins = divmod(m, 60)
    if hours < 24:
        return f"{hours} ч. {mins} мин."
    days, hours = divmod(hours, 24)
    return f"{days} д. {hours} ч."


def render_bybit_card(
    symbol: str,
    side: str,
    entry: float,
    exit_price: float,
    pnl_usdt: float,
    duration_minutes: float = 60.0,
) -> bytes:
    side = (side or "LONG").upper()
    entry = float(entry)
    exit_price = float(exit_price)
    pnl_usdt = float(pnl_usdt)

    coin = symbol.replace("/USDT", "").replace("USDT", "").upper()
    pair_line = f"{coin}USDT"
    side_ru = "Лонг" if side == "LONG" else "Шорт"
    side_color = GREEN if side == "LONG" else RED
    pnl_str = f"+{pnl_usdt:.2f}" if pnl_usdt >= 0 else f"{pnl_usdt:.2f}"

    img = _load_bybit_bg().copy()
    draw = ImageDraw.Draw(img)

    font_symbol = _font(38, weight="semibold")
    font_pill = _font(18, weight="regular")
    font_pnl = _font(58, weight="semibold")
    font_price = _font(26, weight="medium")
    font_duration = _font(20, weight="regular")

    def clear_row(y0, y1, x1, min_key):
        x1 = max(x1 + 4, _BYBIT_MIN_CLEAR_X[min_key])
        draw.rectangle((_BYBIT_X0, y0, x1, y1), fill=(0, 0, 0))

    sym_measure_w = draw.textlength(pair_line, font=font_symbol)
    pill_l, pill_t, pill_r, pill_b = draw.textbbox((0, 0), side_ru, font=font_pill)
    pill_text_w, pill_text_h = pill_r - pill_l, pill_b - pill_t
    pill_pad_x, pill_h = 18, _BYBIT_PILL_Y[1] - _BYBIT_PILL_Y[0]
    pill_x0 = _BYBIT_SYMBOL_XY[0] + sym_measure_w + _BYBIT_PILL_GAP
    natural_w = pill_text_w + pill_pad_x * 2
    stretch_w = (_BYBIT_MIN_CLEAR_X["symbol"] - 4) - pill_x0
    pill_total_w = max(natural_w, stretch_w)
    row1_end_x = pill_x0 + pill_total_w
    clear_row(*_BYBIT_ROW_SYMBOL_Y, row1_end_x, "symbol")

    _draw_topleft(draw, _BYBIT_SYMBOL_XY, pair_line, font_symbol, WHITE)
    pill_x1 = pill_x0 + pill_total_w
    pill_y0, pill_y1 = _BYBIT_PILL_Y
    draw.rounded_rectangle(
        (pill_x0, pill_y0, pill_x1, pill_y1), radius=pill_h // 2,
        outline=side_color, width=2,
    )
    text_y = pill_y0 + (pill_h - pill_text_h) // 2
    text_x = pill_x0 + (pill_total_w - pill_text_w) // 2
    draw.text((text_x - pill_l, text_y - pill_t), side_ru, font=font_pill, fill=side_color)

    pnl_w = draw.textlength(pnl_str, font=font_pnl)
    clear_row(*_BYBIT_ROW_PNL_Y, _BYBIT_PNL_XY[0] + pnl_w, "pnl")
    _draw_topleft(draw, _BYBIT_PNL_XY, pnl_str, font_pnl, GREEN)

    entry_str, exit_str = _fmt_bybit_price(entry), _fmt_bybit_price(exit_price)
    clear_row(*_BYBIT_ROW_ENTRY_Y, _BYBIT_ENTRY_XY[0] + draw.textlength(entry_str, font=font_price), "entry")
    _draw_topleft(draw, _BYBIT_ENTRY_XY, entry_str, font_price, WHITE)
    clear_row(*_BYBIT_ROW_EXIT_Y, _BYBIT_EXIT_XY[0] + draw.textlength(exit_str, font=font_price), "exit")
    _draw_topleft(draw, _BYBIT_EXIT_XY, exit_str, font_price, WHITE)

    duration_line = f"Срок {fmt_duration_ru(duration_minutes)}"
    dur_w = draw.textlength(duration_line, font=font_duration)
    clear_row(*_BYBIT_ROW_DURATION_Y, _BYBIT_DURATION_XY[0] + dur_w, "duration")
    _draw_topleft(draw, _BYBIT_DURATION_XY, duration_line, font_duration, GREY)

    img = img.crop((0, 0, img.width, _BYBIT_CROP_H))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
