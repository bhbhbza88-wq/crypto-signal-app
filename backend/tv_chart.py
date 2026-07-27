"""
График для outlook-постов.

1) Если задан CHART_IMG_API_KEY — реальный скрин TradingView (chart-img.com).
2) Иначе — TradingView-like dark chart по Bybit OHLCV (свечи + трендлайны).
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from data_layer import build_features, fetch_ohlcv_raw

CHART_IMG_API_KEY = (os.getenv("CHART_IMG_API_KEY") or "").strip()
CHART_INTERVAL = (os.getenv("OUTLOOK_CHART_INTERVAL", "360") or "360").strip()  # TV: 360 = 6h
CHART_THEME = (os.getenv("OUTLOOK_CHART_THEME", "dark") or "dark").strip()
CHART_WIDTH = int(os.getenv("OUTLOOK_CHART_WIDTH", "1200") or "1200")
CHART_HEIGHT = int(os.getenv("OUTLOOK_CHART_HEIGHT", "675") or "675")
EXCHANGE_TV = (os.getenv("OUTLOOK_TV_EXCHANGE", "BYBIT") or "BYBIT").strip().upper()
WATERMARK = (os.getenv("OUTLOOK_CHART_WATERMARK") or "Telegram: nowicki_news").strip()
# Bybit ccxt TF for our renderer (6h ≈ Fed-style)
RENDER_TF = (os.getenv("OUTLOOK_CHART_TF", "6h") or "6h").strip()


def _tv_symbol(unified: str) -> str:
    base = unified.replace("/USDT", "").replace("USDT", "").upper().strip()
    return f"{EXCHANGE_TV}:{base}USDT.P"


def fetch_tradingview_png(symbol: str) -> bytes | None:
    if not CHART_IMG_API_KEY:
        return None
    tv_sym = _tv_symbol(symbol)
    url = "https://api.chart-img.com/v1/tradingview/advanced-chart"
    params = {
        "symbol": tv_sym,
        "interval": CHART_INTERVAL,
        "theme": "dark",
        "width": str(min(1280, max(800, CHART_WIDTH))),
        "height": str(min(720, max(450, CHART_HEIGHT))),
        "format": "png",
        "style": "candle",
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
                return None
            return r.content
    except Exception as e:
        print(f"[tv_chart] chart-img fail: {e}", flush=True)
        return None


def _font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
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
        return f"{n:,.2f}"
    if n >= 1:
        return f"{n:.4f}".rstrip("0").rstrip(".")
    if n >= 0.01:
        return f"{n:.5f}".rstrip("0").rstrip(".")
    return f"{n:.8f}".rstrip("0").rstrip(".")


def _pretty_name(symbol: str) -> str:
    base = symbol.replace("/USDT", "").upper()
    names = {
        "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB",
        "XRP": "XRP", "DOGE": "Dogecoin", "ADA": "Cardano", "AVAX": "Avalanche",
        "LINK": "Chainlink", "DOT": "Polkadot", "NEAR": "NEAR", "SUI": "Sui",
        "APT": "Aptos", "WLD": "Worldcoin", "PEPE": "Pepe", "ARB": "Arbitrum",
        "OP": "Optimism", "INJ": "Injective", "TIA": "Celestia", "SEI": "Sei",
    }
    return f"{names.get(base, base)} / TetherUS"


def _macro_trendline(df: pd.DataFrame, kind: str) -> tuple[int, float, int, float] | None:
    """Две точки: экстремум левой половины + правой → трендлайн как у Fed."""
    n = len(df)
    if n < 20:
        return None
    mid = n // 2
    left = df.iloc[:mid]
    right = df.iloc[mid:]
    if kind == "high":
        i1 = int(left["high"].astype(float).idxmax())
        i2 = int(right["high"].astype(float).idxmax())
        y1 = float(df.loc[i1, "high"])
        y2 = float(df.loc[i2, "high"])
    else:
        i1 = int(left["low"].astype(float).idxmin())
        i2 = int(right["low"].astype(float).idxmin())
        y1 = float(df.loc[i1, "low"])
        y2 = float(df.loc[i2, "low"])
    if abs(i2 - i1) < 5:
        return None
    return i1, y1, i2, y2


def render_candle_png(
    symbol: str,
    *,
    exchange_id: str = "bybit",
    levels: dict[str, Any] | None = None,
    bars: int = 80,
    timeframe: str | None = None,
) -> bytes | None:
    """TradingView-like dark chart: свечи, OHLC, трендлайны, правая шкала, watermark."""
    tf = timeframe or RENDER_TF
    raw = None
    for try_tf in (tf, "4h", "1h"):
        raw = fetch_ohlcv_raw(symbol, try_tf, limit=max(140, bars + 50), exchange_id=exchange_id)
        if raw and len(raw) >= 40:
            tf = try_tf
            break
    if not raw or len(raw) < 40:
        return None

    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = build_features(pd.DataFrame(raw, columns=cols)).tail(bars).reset_index(drop=True)
    if len(df) < 25:
        return None

    # 2× supersample → smoother lines (TV look)
    scale = 2
    W = max(1000, CHART_WIDTH) * scale
    H = max(560, CHART_HEIGHT) * scale
    pad_l, pad_r, pad_t, pad_b = 18 * scale, 78 * scale, 52 * scale, 36 * scale
    vol_h = int(H * 0.14)
    plot_h = H - pad_t - pad_b - vol_h - 8 * scale
    plot_w = W - pad_l - pad_r
    vol_top = pad_t + plot_h + 6 * scale

    highs = df["high"].astype(float)
    lows = df["low"].astype(float)
    closes = df["close"].astype(float)
    vols = df["volume"].astype(float)

    y_min = float(lows.min())
    y_max = float(highs.max())
    pad_y = (y_max - y_min) * 0.06 or y_max * 0.01
    y_min -= pad_y
    y_max += pad_y
    if y_max <= y_min:
        y_max = y_min * 1.01 + 1e-9

    def yx(price: float) -> int:
        return int(pad_t + (1.0 - (price - y_min) / (y_max - y_min)) * plot_h)

    def xx(i: float) -> int:
        n = max(1, len(df) - 1)
        return int(pad_l + (float(i) / n) * plot_w)

    def line_y_at(i1, y1, i2, y2, i):
        if i2 == i1:
            return y1
        return y1 + (y2 - y1) * (i - i1) / (i2 - i1)

    bg = (19, 23, 34)
    grid = (42, 46, 57)
    text_muted = (120, 130, 150)
    text_main = (209, 212, 220)
    green = (8, 153, 129)
    red = (242, 54, 69)
    line_blue = (41, 98, 255)

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    font_xs = _font(12 * scale)
    font_sm = _font(13 * scale)
    font_lg = _font(16 * scale, bold=True)
    font_price = _font(13 * scale, bold=True)
    font_wm = _font(22 * scale)

    for g in range(6):
        frac = g / 5
        yy = pad_t + int(plot_h * frac)
        draw.line([(pad_l, yy), (W - pad_r, yy)], fill=grid, width=scale)
        price = y_max - (y_max - y_min) * frac
        label = _fmt(price)
        draw.text((W - pad_r + 8 * scale, yy - 7 * scale), label, font=font_xs, fill=text_muted)

    ts_col = df["timestamp"]
    step = max(1, len(df) // 6)
    for i in range(0, len(df), step):
        x = xx(i)
        draw.line([(x, pad_t), (x, pad_t + plot_h)], fill=grid, width=scale)
        try:
            ts = int(ts_col.iloc[i])
            if ts > 10_000_000_000:
                ts //= 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            lbl = dt.strftime("%d %b")
        except Exception:
            lbl = ""
        if lbl:
            draw.text((x - 14 * scale, H - 22 * scale), lbl, font=font_xs, fill=text_muted)

    vmax = float(vols.max()) or 1.0
    candle_gap = plot_w / max(1, len(df))
    candle_w = max(2 * scale, int(candle_gap * 0.68))
    for i, row in df.iterrows():
        o, c = float(row["open"]), float(row["close"])
        v = float(row["volume"])
        x = xx(int(i))
        vh = int((v / vmax) * (vol_h - 4 * scale))
        vol_color = (8, 90, 80) if c >= o else (120, 40, 50)
        draw.rectangle(
            [x - candle_w // 2, vol_top + vol_h - vh, x + candle_w // 2, vol_top + vol_h],
            fill=vol_color,
        )

    # Fed-style blue trendlines (upper highs + lower lows), extended right
    for kind in ("high", "low"):
        tl = _macro_trendline(df, kind)
        if not tl:
            continue
        i1, y1, i2, y2 = tl
        i_end = len(df) - 1 + 12
        y_end = line_y_at(i1, y1, i2, y2, i_end)
        # start a bit before first anchor for longer line
        i_start = max(0, i1 - 2)
        y_start = line_y_at(i1, y1, i2, y2, i_start)
        draw.line(
            [(xx(i_start), yx(y_start)), (W - pad_r, yx(y_end))],
            fill=line_blue,
            width=2 * scale,
        )

    # invalidation hairline
    inv = (levels or {}).get("invalidation")
    if inv is not None:
        try:
            p = float(inv)
            if y_min <= p <= y_max:
                y = yx(p)
                x0 = pad_l
                while x0 < W - pad_r:
                    draw.line([(x0, y), (min(x0 + 8 * scale, W - pad_r), y)], fill=(200, 60, 70), width=scale)
                    x0 += 14 * scale
        except (TypeError, ValueError):
            pass

    for i, row in df.iterrows():
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        x = xx(int(i))
        color = green if c >= o else red
        draw.line([(x, yx(h)), (x, yx(l))], fill=color, width=scale)
        y1, y2 = yx(max(o, c)), yx(min(o, c))
        if y2 <= y1:
            y2 = y1 + scale
        draw.rectangle([x - candle_w // 2, y1, x + candle_w // 2, y2], fill=color)

    last = df.iloc[-1]
    last_c = float(closes.iloc[-1])
    last_o = float(last["open"])
    py = yx(last_c)
    badge = _fmt(last_c)
    bw = int(draw.textlength(badge, font=font_price)) + 14 * scale
    bh = 22 * scale
    badge_color = green if last_c >= last_o else red
    draw.rounded_rectangle(
        [W - pad_r + 4 * scale, py - bh // 2, W - pad_r + 4 * scale + bw, py + bh // 2],
        radius=3 * scale,
        fill=badge_color,
    )
    draw.text((W - pad_r + 11 * scale, py - 8 * scale), badge, font=font_price, fill=(255, 255, 255))
    lx = xx(len(df) - 1)
    x0 = lx
    while x0 < W - pad_r:
        draw.line([(x0, py), (min(x0 + 6 * scale, W - pad_r), py)], fill=badge_color, width=scale)
        x0 += 11 * scale

    o = float(last["open"]); h = float(last["high"]); l = float(last["low"]); c = float(last["close"])
    chg = c - o
    chg_pct = (chg / o * 100) if o else 0
    chg_color = green if chg >= 0 else red
    title = f"{_pretty_name(symbol)} · {tf} · {exchange_id.capitalize()}"
    draw.text((pad_l, 10 * scale), title, font=font_lg, fill=text_main)
    ohlc = f"O{_fmt(o)}  H{_fmt(h)}  L{_fmt(l)}  C{_fmt(c)}  "
    draw.text((pad_l, 30 * scale), ohlc, font=font_sm, fill=text_muted)
    chg_s = f"{chg:+.2f} ({chg_pct:+.2f}%)" if c >= 1 else f"{chg:+.6f} ({chg_pct:+.2f}%)"
    ohlc_w = draw.textlength(ohlc, font=font_sm)
    draw.text((pad_l + ohlc_w, 30 * scale), chg_s, font=font_sm, fill=chg_color)

    if WATERMARK:
        tw = draw.textlength(WATERMARK, font=font_wm)
        wx = int((W - tw) / 2)
        wy = int(pad_t + plot_h * 0.52)
        draw.text((wx + scale, wy + scale), WATERMARK, font=font_wm, fill=(28, 32, 44))
        draw.text((wx, wy), WATERMARK, font=font_wm, fill=(72, 80, 100))

    draw.text((pad_l, H - 18 * scale), "TV", font=font_xs, fill=(60, 68, 88))

    # downsample for antialias
    out = img.resize((W // scale, H // scale), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def chart_for_symbol(
    symbol: str,
    *,
    exchange_id: str = "bybit",
    levels: dict[str, Any] | None = None,
) -> tuple[bytes | None, str]:
    # Prefer our styled renderer for consistent Fed-like look (dark + trendlines).
    # Real TV screenshot only if OUTLOOK_FORCE_TV=1 and API key set.
    force_tv = (os.getenv("OUTLOOK_FORCE_TV", "0") or "0").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if force_tv:
        png = fetch_tradingview_png(symbol)
        if png:
            return png, "tradingview"
    png = render_candle_png(symbol, exchange_id=exchange_id, levels=levels)
    if png:
        return png, "bybit_render"
    png = fetch_tradingview_png(symbol)
    if png:
        return png, "tradingview"
    return None, ""
