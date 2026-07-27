"""
?????? outlook: TradingView-like dark (???????/??????? ????? + ????? ??????????)
+ ???????/??????? ??????? ???????? ???????????.
OHLC/?????/???? = Bybit; ?????????? ? ???? = ????.
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
CHART_INTERVAL = (os.getenv("OUTLOOK_CHART_INTERVAL", "240") or "240").strip()
CHART_WIDTH = int(os.getenv("OUTLOOK_CHART_WIDTH", "1200") or "1200")
CHART_HEIGHT = int(os.getenv("OUTLOOK_CHART_HEIGHT", "675") or "675")
EXCHANGE_TV = (os.getenv("OUTLOOK_TV_EXCHANGE", "BYBIT") or "BYBIT").strip().upper()
WATERMARK = (os.getenv("OUTLOOK_CHART_WATERMARK") or "Telegram: nowicki_news").strip()
RENDER_TF = (os.getenv("OUTLOOK_CHART_TF", "4h") or "4h").strip()
RENDER_BARS = int(os.getenv("OUTLOOK_CHART_BARS", "120") or "120")


def _tv_symbol(unified: str) -> str:
    base = unified.replace("/USDT", "").replace("USDT", "").upper().strip()
    return f"{EXCHANGE_TV}:{base}USDT.P"


def fetch_tradingview_png(symbol: str) -> bytes | None:
    if not CHART_IMG_API_KEY:
        return None
    url = "https://api.chart-img.com/v1/tradingview/advanced-chart"
    params = {
        "symbol": _tv_symbol(symbol),
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
        "APT": "Aptos", "WLD": "Worldcoin", "ARB": "Arbitrum", "OP": "Optimism",
    }
    return f"{names.get(base, base)} / TetherUS"


def _macro_trendline(df: pd.DataFrame, kind: str) -> tuple[int, float, int, float] | None:
    n = len(df)
    if n < 20:
        return None
    mid = n // 2
    left, right = df.iloc[:mid], df.iloc[mid:]
    if kind == "high":
        i1 = int(left["high"].astype(float).idxmax())
        i2 = int(right["high"].astype(float).idxmax())
        y1, y2 = float(df.loc[i1, "high"]), float(df.loc[i2, "high"])
    else:
        i1 = int(left["low"].astype(float).idxmin())
        i2 = int(right["low"].astype(float).idxmin())
        y1, y2 = float(df.loc[i1, "low"]), float(df.loc[i2, "low"])
    if abs(i2 - i1) < 5:
        return None
    return i1, y1, i2, y2


def _draw_direction_path(
    draw: ImageDraw.ImageDraw,
    *,
    xx,
    yx,
    pad_l: int,
    pad_r: int,
    pad_t: int,
    plot_h: int,
    W: int,
    scale: int,
    last_i: int,
    last_c: float,
    target: float,
    bias: str,
    n_bars: int,
):
    """??????? ???? ????? / ??????? ???? ? ????."""
    if last_c <= 0:
        return
    dist = abs(target - last_c) / last_c
    if dist < 0.003 or dist > 0.12:
        # soft fallback target ~1.5%
        target = last_c * (1.015 if bias != "short" else 0.985)

    going_up = bias != "short"
    if going_up and target < last_c:
        target = last_c * 1.015
    if not going_up and target > last_c:
        target = last_c * 0.985

    color = (46, 204, 113) if going_up else (242, 54, 69)
    mid_i = last_i + max(5, int(n_bars * 0.07))
    tip_i = last_i + max(10, int(n_bars * 0.15))
    pull = last_c + (abs(target - last_c) * (-0.15 if going_up else 0.15))

    path = [
        (xx(last_i), yx(last_c)),
        (xx(last_i + 2), yx(pull)),
        (xx(mid_i), yx((pull + target) / 2)),
        (xx(tip_i), yx(target)),
    ]
    path = [
        (
            min(max(x, pad_l), W - pad_r),
            min(max(y, pad_t + 2), pad_t + plot_h - 2),
        )
        for x, y in path
    ]
    draw.line(path, fill=color, width=3 * scale)
    ax, ay = path[-1]
    if going_up:
        draw.polygon(
            [(ax, ay), (ax - 9 * scale, ay + 6 * scale), (ax + 9 * scale, ay + 6 * scale)],
            fill=color,
        )
    else:
        draw.polygon(
            [(ax, ay), (ax - 9 * scale, ay - 6 * scale), (ax + 9 * scale, ay - 6 * scale)],
            fill=color,
        )


def render_candle_png(
    symbol: str,
    *,
    exchange_id: str = "bybit",
    levels: dict[str, Any] | None = None,
    bars: int | None = None,
    timeframe: str | None = None,
    bias: str = "long",
) -> bytes | None:
    tf = timeframe or RENDER_TF
    n_bars = max(60, min(200, int(bars if bars is not None else RENDER_BARS)))
    raw = None
    for try_tf in (tf, "4h", "1h"):
        raw = fetch_ohlcv_raw(symbol, try_tf, limit=max(n_bars + 30, 100), exchange_id=exchange_id)
        if raw and len(raw) >= 40:
            tf = try_tf
            break
    if not raw or len(raw) < 40:
        return None

    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = build_features(pd.DataFrame(raw, columns=cols)).tail(n_bars).reset_index(drop=True)
    if len(df) < 25:
        return None

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
    lv = levels or {}

    y_min, y_max = float(lows.min()), float(highs.max())
    for k in ("support", "resistance", "invalidation", "target_1", "target_2"):
        try:
            if lv.get(k) is not None:
                v = float(lv[k])
                # ?? ????????? ????? ????????? ????????
                if abs(v - closes.iloc[-1]) / closes.iloc[-1] < 0.15:
                    y_min = min(y_min, v)
                    y_max = max(y_max, v)
        except (TypeError, ValueError):
            pass
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
        draw.text(
            (W - pad_r + 8 * scale, yy - 7 * scale),
            _fmt(y_max - (y_max - y_min) * frac),
            font=font_xs,
            fill=text_muted,
        )

    ts_col = df["timestamp"]
    step = max(1, len(df) // 6)
    for i in range(0, len(df), step):
        x = xx(i)
        draw.line([(x, pad_t), (x, pad_t + plot_h)], fill=grid, width=scale)
        try:
            ts = int(ts_col.iloc[i])
            if ts > 10_000_000_000:
                ts //= 1000
            lbl = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d %b")
        except Exception:
            lbl = ""
        if lbl:
            draw.text((x - 14 * scale, H - 22 * scale), lbl, font=font_xs, fill=text_muted)

    vmax = float(vols.max()) or 1.0
    candle_w = max(2 * scale, int((plot_w / max(1, len(df))) * 0.68))
    for i, row in df.iterrows():
        o, c = float(row["open"]), float(row["close"])
        x = xx(int(i))
        vh = int((float(row["volume"]) / vmax) * (vol_h - 4 * scale))
        vol_color = (8, 90, 80) if c >= o else (120, 40, 50)
        draw.rectangle(
            [x - candle_w // 2, vol_top + vol_h - vh, x + candle_w // 2, vol_top + vol_h],
            fill=vol_color,
        )

    for kind in ("high", "low"):
        tl = _macro_trendline(df, kind)
        if not tl:
            continue
        i1, y1, i2, y2 = tl
        x1, yy1 = xx(i1), yx(y1)
        x2, yy2 = xx(i2), yx(y2)
        if x2 == x1:
            continue
        slope_px = (yy2 - yy1) / (x2 - x1)
        x_left, x_right = pad_l, W - pad_r
        draw.line(
            [
                (x_left, yy1 + slope_px * (x_left - x1)),
                (x_right, yy2 + slope_px * (x_right - x2)),
            ],
            fill=line_blue,
            width=2 * scale,
        )

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
    last_i = len(df) - 1
    bias_norm = (bias or "long").strip().lower()
    try:
        if bias_norm == "short":
            target = float(lv.get("invalidation") or lv.get("support") or last_c * 0.985)
            if target >= last_c:
                target = last_c * 0.985
        else:
            target = float(lv.get("target_1") or lv.get("resistance") or last_c * 1.015)
            if target <= last_c:
                target = last_c * 1.015
    except (TypeError, ValueError):
        target = last_c * (1.015 if bias_norm != "short" else 0.985)

    _draw_direction_path(
        draw,
        xx=xx,
        yx=yx,
        pad_l=pad_l,
        pad_r=pad_r,
        pad_t=pad_t,
        plot_h=plot_h,
        W=W,
        scale=scale,
        last_i=last_i,
        last_c=last_c,
        target=target,
        bias=bias_norm,
        n_bars=len(df),
    )

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
    x0 = xx(last_i)
    while x0 < W - pad_r:
        draw.line([(x0, py), (min(x0 + 6 * scale, W - pad_r), py)], fill=badge_color, width=scale)
        x0 += 11 * scale

    o, h, l, c = float(last["open"]), float(last["high"]), float(last["low"]), float(last["close"])
    chg = c - o
    chg_pct = (chg / o * 100) if o else 0
    chg_color = green if chg >= 0 else red
    title = f"{_pretty_name(symbol)} � {tf} � {exchange_id.capitalize()}"
    draw.text((pad_l, 10 * scale), title, font=font_lg, fill=text_main)
    ohlc = f"O{_fmt(o)}  H{_fmt(h)}  L{_fmt(l)}  C{_fmt(c)}  "
    draw.text((pad_l, 30 * scale), ohlc, font=font_sm, fill=text_muted)
    chg_s = f"{chg:+.2f} ({chg_pct:+.2f}%)" if c >= 1 else f"{chg:+.6f} ({chg_pct:+.2f}%)"
    draw.text((pad_l + draw.textlength(ohlc, font=font_sm), 30 * scale), chg_s, font=font_sm, fill=chg_color)

    if WATERMARK:
        tw = draw.textlength(WATERMARK, font=font_wm)
        wx = int((W - tw) / 2)
        wy = int(pad_t + plot_h * 0.52)
        draw.text((wx + scale, wy + scale), WATERMARK, font=font_wm, fill=(28, 32, 44))
        draw.text((wx, wy), WATERMARK, font=font_wm, fill=(72, 80, 100))

    draw.text((pad_l, H - 18 * scale), "TV", font=font_xs, fill=(60, 68, 88))

    out = img.resize((W // scale, H // scale), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def chart_for_symbol(
    symbol: str,
    *,
    exchange_id: str = "bybit",
    levels: dict[str, Any] | None = None,
    bias: str = "long",
) -> tuple[bytes | None, str]:
    force_tv = (os.getenv("OUTLOOK_FORCE_TV", "0") or "0").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if force_tv:
        png = fetch_tradingview_png(symbol)
        if png:
            return png, "tradingview"
    png = render_candle_png(symbol, exchange_id=exchange_id, levels=levels, bias=bias)
    if png:
        return png, "bybit_render"
    png = fetch_tradingview_png(symbol)
    if png:
        return png, "tradingview"
    return None, ""
