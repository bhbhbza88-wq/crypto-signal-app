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
BYBIT_BG_PATH = _ASSETS / "bybit_pnl_card_bg.png"
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


def _bg_for_text() -> Image.Image:
    """Эталонный фон Binance как есть: эмблема справа (левый край ~0.566 у строки пары,
    ~0.643 у ROI). Текст держим левее — сдвигать/перерисовывать фон не нужно."""
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
    # ROI на карточке = движение цены × плечо (как Binance ROE)
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

    # Текст как на эталоне: заканчивается ~0.46–0.52 ширины, эмблема начинается с ~0.566.
    pad = int(W * 0.070)
    text_max_w = max(120, int(W * 0.52) - pad)
    col2_x = int(W * 0.48)

    def fit_font(text: str, start: int, bold: bool, min_size: int = 14) -> ImageFont.FreeTypeFont:
        size = start
        while size >= min_size:
            f = _font(size, bold=bold)
            if draw.textlength(text, font=f) <= text_max_w:
                return f
            size -= 1
        return _font(min_size, bold=bold)

    font_pair = fit_font(pair_line, max(26, int(H * 0.040)), bold=True, min_size=16)
    font_side = _font(max(18, int(H * 0.030)), bold=False)
    font_roi = fit_font(roi_str, max(46, int(H * 0.095)), bold=True, min_size=22)
    font_label = _font(max(16, int(H * 0.026)), bold=False)
    font_val = _font(max(20, int(H * 0.033)), bold=True)

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


# ── Bybit-style карточка (скрин из приложения с реф-плашкой) ──────────
# Фон — реальный скрин юзера (assets/bybit_pnl_card_bg.png), НЕ трогаем:
# лого, деньги/стрелки, сетку, футер с QR и реф-кодом. Перекрашиваем только
# 5 динамических зон (замерено по пикселям с оригинала).
# y-диапазоны зон подобраны по пикселям оригинала; x — считается динамически
# под фактическую ширину нового текста (см. render_bybit_card), чтобы не
# оставлять «пустой» чёрный шов там, где сетка фона просто вырезана без текста.
_BYBIT_ROW_SYMBOL_Y = (180, 226)
_BYBIT_ROW_PNL_Y = (312, 388)
_BYBIT_ROW_ENTRY_Y = (474, 513)
_BYBIT_ROW_EXIT_Y = (574, 613)
_BYBIT_ROW_DURATION_Y = (669, 718)

# Минимальный правый край очистки — правый край оригинального текста на
# скрине (замерено по пикселям). Гарантирует, что старые цифры не будут
# «торчать» из-под нового текста, даже если у нашего шрифта другая метрика.
_BYBIT_MIN_CLEAR_X = {"symbol": 393, "pnl": 268, "entry": 139, "exit": 151, "duration": 249}

_BYBIT_X0 = 30
_BYBIT_SYMBOL_XY = (50, 183)
_BYBIT_PILL_Y = (186, 222)
_BYBIT_PILL_GAP = 14
_BYBIT_PNL_XY = (53, 316)
_BYBIT_ENTRY_XY = (48, 477)
_BYBIT_EXIT_XY = (48, 577)
_BYBIT_DURATION_XY = (49, 675)


@lru_cache(maxsize=1)
def _load_bybit_bg() -> Image.Image:
    if not BYBIT_BG_PATH.exists():
        raise FileNotFoundError(f"Нет фона Bybit-карточки: {BYBIT_BG_PATH}")
    return Image.open(BYBIT_BG_PATH).convert("RGB")


def _draw_topleft(draw, xy, text, font, fill) -> tuple[int, int]:
    """Рисует текст так, чтобы видимый верх-лево глифов совпал с xy
    (компенсирует внутренние отступы шрифта у ascent)."""
    x, y = xy
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text((x - l, y - t), text, font=font, fill=fill)
    return (r - l, b - t)


def _fmt_bybit_price(v: float) -> str:
    """Короче, чем _fmt_price — как реально показывает Bybit (без лишних нулей)."""
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
    """'22 ч. 2 мин.' / '48 мин.' / '1 д. 6 ч.' — как подпись 'Срок' на Bybit."""
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
    """Карточка в стиле шаринга из приложения Bybit. Фон (лого/мешок денег/
    сетка/футер с QR и реф-кодом) — оригинальный скрин, не меняется.
    Меняются только: пара, Лонг/Шорт, P&L в USDT, цены входа/выхода, срок.
    """
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

    # Размеры подобраны так, чтобы ширина рендера ≈ ширине оригинального
    # текста на скрине (другой шрифт даёт другую метрику при том же px).
    font_symbol = _font(41, bold=True)
    font_pill = _font(20, bold=False)
    font_pnl = _font(66, bold=True)
    font_price = _font(28, bold=True)
    font_duration = _font(22, bold=False)

    def clear_row(y0, y1, x1, min_key):
        """Чистим под ширину нового текста, но не уже правого края оригинала
        (min_key) — иначе из-под нового текста «торчат» старые цифры/буквы
        (другой шрифт даёт другую метрику ширины)."""
        x1 = max(x1 + 4, _BYBIT_MIN_CLEAR_X[min_key])
        draw.rectangle((_BYBIT_X0, y0, x1, y1), fill=(0, 0, 0))

    # ── Пара + плашка Лонг/Шорт ──
    sym_measure_w = draw.textlength(pair_line, font=font_symbol)
    pill_l, pill_t, pill_r, pill_b = draw.textbbox((0, 0), side_ru, font=font_pill)
    pill_text_w, pill_text_h = pill_r - pill_l, pill_b - pill_t
    pill_pad_x, pill_h = 18, _BYBIT_PILL_Y[1] - _BYBIT_PILL_Y[0]
    pill_total_w = pill_text_w + pill_pad_x * 2
    row1_end_x = _BYBIT_SYMBOL_XY[0] + sym_measure_w + _BYBIT_PILL_GAP + pill_total_w
    clear_row(*_BYBIT_ROW_SYMBOL_Y, row1_end_x, "symbol")

    sym_w, _ = _draw_topleft(draw, _BYBIT_SYMBOL_XY, pair_line, font_symbol, WHITE)
    pill_x0 = _BYBIT_SYMBOL_XY[0] + sym_w + _BYBIT_PILL_GAP
    pill_x1 = pill_x0 + pill_total_w
    pill_y0, pill_y1 = _BYBIT_PILL_Y
    draw.rounded_rectangle(
        (pill_x0, pill_y0, pill_x1, pill_y1), radius=pill_h // 2,
        outline=side_color, width=2,
    )
    text_y = pill_y0 + (pill_h - pill_text_h) // 2
    draw.text((pill_x0 + pill_pad_x - pill_l, text_y - pill_t), side_ru, font=font_pill, fill=side_color)

    # ── P&L (USDT) ──
    pnl_w = draw.textlength(pnl_str, font=font_pnl)
    clear_row(*_BYBIT_ROW_PNL_Y, _BYBIT_PNL_XY[0] + pnl_w, "pnl")
    _draw_topleft(draw, _BYBIT_PNL_XY, pnl_str, font_pnl, GREEN)

    # ── Цена входа / выхода ──
    entry_str, exit_str = _fmt_bybit_price(entry), _fmt_bybit_price(exit_price)
    clear_row(*_BYBIT_ROW_ENTRY_Y, _BYBIT_ENTRY_XY[0] + draw.textlength(entry_str, font=font_price), "entry")
    _draw_topleft(draw, _BYBIT_ENTRY_XY, entry_str, font_price, WHITE)
    clear_row(*_BYBIT_ROW_EXIT_Y, _BYBIT_EXIT_XY[0] + draw.textlength(exit_str, font=font_price), "exit")
    _draw_topleft(draw, _BYBIT_EXIT_XY, exit_str, font_price, WHITE)

    # ── Срок ──
    duration_line = f"Срок {fmt_duration_ru(duration_minutes)}"
    dur_w = draw.textlength(duration_line, font=font_duration)
    clear_row(*_BYBIT_ROW_DURATION_Y, _BYBIT_DURATION_XY[0] + dur_w, "duration")
    _draw_topleft(draw, _BYBIT_DURATION_XY, duration_line, font_duration, GREY)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
