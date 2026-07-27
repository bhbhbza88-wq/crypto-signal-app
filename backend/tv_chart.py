"""
График для outlook-постов.

1) Если задан CHART_IMG_API_KEY — реальный скрин TradingView (chart-img.com).
2) Иначе — тёмный свечной график по Bybit OHLCV (EMA + уровни), без внешних ключей.
"""

from __future__ import annotations

import io
import os
from typing import Any

import httpx
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from data_layer import build_features, fetch_ohlcv_raw

CHART_IMG_API_KEY = (os.getenv("CHART_IMG_API_KEY") or "").strip()
CHART_INTERVAL = (os.getenv("OUTLOOK_CHART_INTERVAL", "240") or "240").strip()  # TV: 240 = 4h
CHART_THEME = (os.getenv("OUTLOOK_CHART_THEME", "dark") or "dark").strip()
CHART_WIDTH = int(os.getenv("OUTLOOK_CHART_WIDTH", "800") or "800")
CHART_HEIGHT = int(os.getenv("OUTLOOK_CHART_HEIGHT", "450") or "450")
EXCHANGE_TV = (os.getenv("OUTLOOK_TV_EXCHANGE", "BYBIT") or "BYBIT").strip().upper()


def _tv_symbol(unified: str) -> str:
    """BTC/USDT → BYBIT:BTCUSDT.P (linear perp на TV)."""
    base = unified.replace("/USDT", "").replace("USDT", "").upper().strip()
    # Perp на TV для Bybit обычно SYMBOLUSDT.P
    return f"{EXCHANGE_TV}:{base}USDT.P"


def fetch_tradingview_png(symbol: str) -> bytes | None:
    """Скрин TradingView через chart-img. Нужен CHART_IMG_API_KEY."""
    if not CHART_IMG_API_KEY:
        return None
    tv_sym = _tv_symbol(symbol)
    url = "https://api.chart-img.com/v1/tradingview/advanced-chart"
    params = {
        "symbol": tv_sym,
        "interval": CHART_INTERVAL,
        "theme": CHART_THEME,
        "width": str(min(1280, max(640, CHART_WIDTH))),
        "height": str(min(720, max(360, CHART_HEIGHT))),
        "format": "png",
        "style": "candle",
        "studies": ["EMA:21", "EMA:50", "Volume"],
    }
    headers = {
        "x-api-key": CHART_IMG_API_KEY,
        "Authorization": f"Bearer {CHART_IMG_API_KEY}",
    }
    try:
        with httpx.Client(timeout=60) as client:
            r = client.get(url, params=params, headers=headers)
            if r.status_code != 200 or not r.content or len(r.content) < 500:
                print(f"[tv_chart] chart-img {r.status_code}: {r.text[:200]}", flush=True)
                return None
            ctype = (r.headers.get("content-type") or "").lower()
            if "image" not in ctype and r.content[:8] != b"\x89PNG\r\n\x1a\n":
                print(f"[tv_chart] chart-img not image: {ctype}", flush=True)
                return None
            return r.content
    except Exception as e:
        print(f"[tv_chart] chart-img fail: {e}", flush=True)
        return None


def _font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf" if not bold else r"C:\Windows\Fonts\segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else None,
    ]
    for p in candidates:
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _fmt(v: float) -> str:
    n = float(v)
    if n >= 1000:
        return f"{n:.2f}"
    if n >= 1:
        return f"{n:.4f}".rstrip("0").rstrip(".")
    if n >= 0.01:
        return f"{n:.5f}".rstrip("0").rstrip(".")
    return f"{n:.8f}".rstrip("0").rstrip(".")


def render_candle_png(
    symbol: str,
    *,
    exchange_id: str = "bybit",
    levels: dict[str, Any] | None = None,
    bars: int = 90,
    timeframe: str = "4h",
) -> bytes | None:
    """Тёмный свечной график с EMA21/50 и уровнями (fallback без TV API)."""
    raw = fetch_ohlcv_raw(symbol, timeframe, limit=max(120, bars + 40), exchange_id=exchange_id)
    if not raw or len(raw) < 40:
        return None
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = build_features(pd.DataFrame(raw, columns=cols)).tail(bars).reset_index(drop=True)
    if len(df) < 20:
        return None

    W, H = CHART_WIDTH, CHART_HEIGHT
    pad_l, pad_r, pad_t, pad_b = 56, 16, 36, 48
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b

    highs = df["high"].astype(float)
    lows = df["low"].astype(float)
    y_min = float(lows.min())
    y_max = float(highs.max())
    lv = levels or {}
    for k in ("support", "resistance", "invalidation", "ema21", "ema50", "target_1", "target_2"):
        v = lv.get(k)
        if v is not None:
            try:
                y_min = min(y_min, float(v))
                y_max = max(y_max, float(v))
            except (TypeError, ValueError):
                pass
    pad_y = (y_max - y_min) * 0.08 or y_max * 0.01
    y_min -= pad_y
    y_max += pad_y
    if y_max <= y_min:
        y_max = y_min * 1.01 + 1e-9

    def yx(price: float) -> int:
        return int(pad_t + (1 - (price - y_min) / (y_max - y_min)) * plot_h)

    def xx(i: int) -> int:
        n = max(1, len(df) - 1)
        return int(pad_l + (i / n) * plot_w)

    bg = (19, 23, 34)
    grid = (35, 41, 58)
    text_c = (180, 188, 208)
    green = (14, 203, 129)
    red = (246, 70, 93)
    ema21_c = (41, 98, 255)
    ema50_c = (255, 152, 0)
    support_c = (64, 150, 255)
    resist_c = (64, 150, 255)
    inv_c = (255, 82, 82)
    tgt_c = (180, 180, 200)

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    font_sm = _font(13)
    font_md = _font(15, bold=True)

    for g in range(5):
        yy = pad_t + int(plot_h * g / 4)
        draw.line([(pad_l, yy), (W - pad_r, yy)], fill=grid, width=1)
        price = y_max - (y_max - y_min) * g / 4
        draw.text((6, yy - 7), _fmt(price), font=font_sm, fill=text_c)

    for col, color in (("ema21", ema21_c), ("ema50", ema50_c)):
        pts = []
        for i, row in df.iterrows():
            v = row.get(col)
            if pd.isna(v):
                continue
            pts.append((xx(int(i)), yx(float(v))))
        if len(pts) >= 2:
            draw.line(pts, fill=color, width=2)

    candle_w = max(2, int(plot_w / len(df) * 0.65))
    for i, row in df.iterrows():
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        x = xx(int(i))
        color = green if c >= o else red
        draw.line([(x, yx(h)), (x, yx(l))], fill=color, width=1)
        y1, y2 = yx(max(o, c)), yx(min(o, c))
        if y2 - y1 < 1:
            y2 = y1 + 1
        draw.rectangle([x - candle_w // 2, y1, x + candle_w // 2, y2], fill=color)

    def level_line(key: str, color: tuple, label: str, width: int = 1):
        v = (levels or {}).get(key)
        if v is None:
            return
        try:
            p = float(v)
        except (TypeError, ValueError):
            return
        y = yx(p)
        # dashed-ish
        x0 = pad_l
        while x0 < W - pad_r:
            x1 = min(x0 + 10, W - pad_r)
            draw.line([(x0, y), (x1, y)], fill=color, width=width)
            x0 += 16
        draw.text((pad_l + 4, y - 14), f"{label} {_fmt(p)}", font=font_sm, fill=color)

    level_line("resistance", resist_c, "R", 2)
    level_line("target_1", tgt_c, "T1")
    level_line("target_2", tgt_c, "T2")
    level_line("support", support_c, "S", 2)
    level_line("invalidation", inv_c, "INV", 2)

    coin = symbol.replace("/USDT", "")
    title = f"{coin}USDT · BYBIT · {timeframe.upper()}"
    draw.text((pad_l, 8), title, font=font_md, fill=(230, 234, 242))
    draw.text((W - 200, 10), "Telegram: nowicki_news", font=font_sm, fill=(90, 100, 120))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def chart_for_symbol(
    symbol: str,
    *,
    exchange_id: str = "bybit",
    levels: dict[str, Any] | None = None,
) -> tuple[bytes | None, str]:
    """
    Возвращает (png_bytes, source_tag).
    source_tag: 'tradingview' | 'bybit_render' | ''
    """
    png = fetch_tradingview_png(symbol)
    if png:
        return png, "tradingview"
    png = render_candle_png(symbol, exchange_id=exchange_id, levels=levels)
    if png:
        return png, "bybit_render"
    return None, ""
