"""
График для outlook-постов — стиль «Торговый Букварь»:
тёмный фон, синие/белые свечи, серые зоны, оранжевые уровни, зелёный путь.
OHLC/объём/даты = Bybit; зоны/путь = авто по уровням сканера.
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
CHART_INTERVAL = (os.getenv("OUTLOOK_CHART_INTERVAL", "60") or "60").strip()
CHART_WIDTH = int(os.getenv("OUTLOOK_CHART_WIDTH", "1200") or "1200")
CHART_HEIGHT = int(os.getenv("OUTLOOK_CHART_HEIGHT", "675") or "675")
EXCHANGE_TV = (os.getenv("OUTLOOK_TV_EXCHANGE", "BYBIT") or "BYBIT").strip().upper()
WATERMARK = (os.getenv("OUTLOOK_CHART_WATERMARK") or "Telegram: nowicki_news").strip()
# 1h плотнее, как у «Букваря»; можно OUTLOOK_CHART_TF=4h
RENDER_TF = (os.getenv("OUTLOOK_CHART_TF", "1h") or "1h").strip()
RENDER_BARS = int(os.getenv("OUTLOOK_CHART_BARS", "100") or "100")


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


def _blend(base: tuple, overlay: tuple, alpha: float) -> tuple[int, int, int]:
    a = max(0.0, min(1.0, alpha))
    return tuple(int(base[i] * (1 - a) + overlay[i] * a) for i in range(3))


def _zone_band(df: pd.DataFrame, kind: str) -> tuple[float, float, int, int] | None:
    """Серая зона вокруг swing low/high в правой трети графика."""
    n = len(df)
    if n < 30:
        return None
    right = df.iloc[n // 2 :]
    if kind == "low":
        i = int(right["low"].astype(float).idxmin())
        p = float(df.loc[i, "low"])
        atr = float(df["atr"].iloc[-1]) if "atr" in df.columns and not pd.isna(df["atr"].iloc[-1]) else p * 0.008
        return p - atr * 0.15, p + atr * 0.55, max(0, i - 8), min(n - 1, i + 18)
    i = int(right["high"].astype(float).idxmax())
    p = float(df.loc[i, "high"])
    atr = float(df["atr"].iloc[-1]) if "atr" in df.columns and not pd.isna(df["atr"].iloc[-1]) else p * 0.008
    return p - atr * 0.55, p + atr * 0.15, max(0, i - 8), min(n - 1, i + 18)


def render_candle_png(
    symbol: str,
    *,
    exchange_id: str = "bybit",
    levels: dict[str, Any] | None = None,
    bars: int | None = None,
    timeframe: str | None = None,
) -> bytes | None:
    tf = timeframe or RENDER_TF
    n_bars = max(60, min(200, int(bars if bars is not None else RENDER_BARS)))
    raw = None
    for try_tf in (tf, "1h", "4h"):
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
    pad_l, pad_r, pad_t, pad_b = 14 * scale, 88 * scale, 44 * scale, 28 * scale
    vol_h = int(H * 0.11)
    plot_h = H - pad_t - pad_b - vol_h - 6 * scale
    plot_w = W - pad_l - pad_r
    vol_top = pad_t + plot_h + 4 * scale

    highs = df["high"].astype(float)
    lows = df["low"].astype(float)
    closes = df["close"].astype(float)
    vols = df["volume"].astype(float)

    lv = levels or {}
    y_min = float(lows.min())
    y_max = float(highs.max())
    for k in ("support", "resistance", "invalidation", "target_1", "target_2"):
        try:
            if lv.get(k) is not None:
                y_min = min(y_min, float(lv[k]))
                y_max = max(y_max, float(lv[k]))
        except (TypeError, ValueError):
            pass
    pad_y = (y_max - y_min) * 0.07 or y_max * 0.01
    y_min -= pad_y
    y_max += pad_y
    if y_max <= y_min:
        y_max = y_min * 1.01 + 1e-9

    def yx(price: float) -> int:
        return int(pad_t + (1.0 - (price - y_min) / (y_max - y_min)) * plot_h)

    def xx(i: float) -> int:
        n = max(1, len(df) - 1)
        return int(pad_l + (float(i) / n) * plot_w)

    # TB palette
    bg = (0, 0, 0)
    grid = (28, 28, 32)
    text_muted = (140, 140, 150)
    text_main = (220, 220, 225)
    bull = (90, 160, 255)       # blue up
    bear = (230, 230, 235)      # white down
    zone_c = (70, 70, 78)
    orange = (255, 152, 0)
    path_g = (46, 204, 113)
    badge_now = (230, 230, 235)

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    font_xs = _font(12 * scale)
    font_sm = _font(13 * scale)
    font_lg = _font(15 * scale, bold=True)
    font_price = _font(12 * scale, bold=True)
    font_wm = _font(20 * scale)

    # grid
    for g in range(6):
        frac = g / 5
        yy = pad_t + int(plot_h * frac)
        draw.line([(pad_l, yy), (W - pad_r, yy)], fill=grid, width=scale)
        draw.text((W - pad_r + 8 * scale, yy - 7 * scale), _fmt(y_max - (y_max - y_min) * frac), font=font_xs, fill=text_muted)

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
            draw.text((x - 12 * scale, H - 20 * scale), lbl, font=font_xs, fill=text_muted)

    # grey zones (liquidity / demand-supply)
    def paint_zone(lo: float, hi: float, i0: int, i1: int, alpha: float = 0.35):
        x0, x1 = xx(i0), xx(i1)
        y0, y1 = yx(hi), yx(lo)
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        # simulate alpha by blending onto black
        fill = _blend(bg, zone_c, alpha)
        draw.rectangle([x0, y0, max(x0 + 2, x1), max(y0 + 2, y1)], fill=fill)

    z_low = _zone_band(df, "low")
    z_high = _zone_band(df, "high")
    if z_low:
        paint_zone(*z_low, alpha=0.45)
    if z_high:
        paint_zone(*z_high, alpha=0.35)
    # zone from scanner support/resistance around last third
    try:
        if lv.get("support") is not None:
            s = float(lv["support"])
            atr = float(df["atr"].iloc[-1]) if not pd.isna(df["atr"].iloc[-1]) else s * 0.01
            paint_zone(s - atr * 0.2, s + atr * 0.5, int(len(df) * 0.55), len(df) - 1, 0.4)
        if lv.get("target_1") is not None:
            t = float(lv["target_1"])
            atr = float(df["atr"].iloc[-1]) if not pd.isna(df["atr"].iloc[-1]) else t * 0.01
            paint_zone(t - atr * 0.45, t + atr * 0.2, int(len(df) * 0.7), len(df) - 1 + 5, 0.3)
    except (TypeError, ValueError):
        pass

    # volume (subtle)
    vmax = float(vols.max()) or 1.0
    candle_w = max(2 * scale, int((plot_w / max(1, len(df))) * 0.65))
    for i, row in df.iterrows():
        o, c = float(row["open"]), float(row["close"])
        x = xx(int(i))
        vh = int((float(row["volume"]) / vmax) * (vol_h - 3 * scale))
        vc = (40, 70, 110) if c >= o else (90, 90, 95)
        draw.rectangle([x - candle_w // 2, vol_top + vol_h - vh, x + candle_w // 2, vol_top + vol_h], fill=vc)

    # candles blue / white
    for i, row in df.iterrows():
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        x = xx(int(i))
        color = bull if c >= o else bear
        draw.line([(x, yx(h)), (x, yx(l))], fill=color, width=scale)
        y1, y2 = yx(max(o, c)), yx(min(o, c))
        if y2 <= y1:
            y2 = y1 + scale
        draw.rectangle([x - candle_w // 2, y1, x + candle_w // 2, y2], fill=color)

    # green projected path → target (только если цель рядом, иначе криво)
    last_i = len(df) - 1
    last_c = float(closes.iloc[-1])
    try:
        t1 = float(lv["target_1"]) if lv.get("target_1") is not None else last_c * 1.015
    except (TypeError, ValueError):
        t1 = last_c * 1.015
    if last_c > 0 and abs(t1 - last_c) / last_c < 0.12:
        mid_i = last_i + max(4, len(df) * 0.06)
        tip_i = last_i + max(8, len(df) * 0.14)
        dip = last_c - abs(t1 - last_c) * 0.12
        path = [
            (xx(last_i), yx(last_c)),
            (xx(last_i + 2), yx(dip)),
            (xx(mid_i), yx((dip + t1) / 2)),
            (xx(tip_i), yx(t1)),
        ]
        path = [(min(max(p[0], pad_l), W - pad_r), min(max(p[1], pad_t), pad_t + plot_h)) for p in path]
        draw.line(path, fill=path_g, width=3 * scale)
        ax, ay = path[-1]
        draw.polygon(
            [(ax, ay), (ax - 8 * scale, ay + 5 * scale), (ax - 8 * scale, ay - 5 * scale)],
            fill=path_g,
        )

    def price_badge(price: float, color: tuple, text_color=(0, 0, 0)):
        y = yx(price)
        label = _fmt(price)
        bw = int(draw.textlength(label, font=font_price)) + 12 * scale
        bh = 20 * scale
        draw.rounded_rectangle(
            [W - pad_r + 4 * scale, y - bh // 2, W - pad_r + 4 * scale + bw, y + bh // 2],
            radius=3 * scale,
            fill=color,
        )
        draw.text((W - pad_r + 10 * scale, y - 7 * scale), label, font=font_price, fill=text_color)
        # hairline
        x0 = xx(last_i)
        while x0 < W - pad_r:
            draw.line([(x0, y), (min(x0 + 5 * scale, W - pad_r), y)], fill=color, width=scale)
            x0 += 10 * scale

    # orange key levels + current
    try:
        if lv.get("support") is not None:
            price_badge(float(lv["support"]), orange, (0, 0, 0))
        if lv.get("invalidation") is not None and lv.get("support") is not None:
            if abs(float(lv["invalidation"]) - float(lv["support"])) / last_c > 0.003:
                price_badge(float(lv["invalidation"]), orange, (0, 0, 0))
        if lv.get("target_1") is not None:
            price_badge(float(lv["target_1"]), orange, (0, 0, 0))
    except (TypeError, ValueError):
        pass
    price_badge(last_c, badge_now, (20, 20, 20))

    # header
    last = df.iloc[-1]
    o, h, l, c = float(last["open"]), float(last["high"]), float(last["low"]), float(last["close"])
    chg = c - o
    chg_pct = (chg / o * 100) if o else 0
    title = f"{_pretty_name(symbol)} · {tf} · {exchange_id.capitalize()}"
    draw.text((pad_l, 8 * scale), title, font=font_lg, fill=text_main)
    ohlc = f"O{_fmt(o)}  H{_fmt(h)}  L{_fmt(l)}  C{_fmt(c)}  "
    draw.text((pad_l, 28 * scale), ohlc, font=font_sm, fill=text_muted)
    chg_col = bull if chg >= 0 else (200, 80, 90)
    draw.text(
        (pad_l + draw.textlength(ohlc, font=font_sm), 28 * scale),
        f"{chg:+.2f} ({chg_pct:+.2f}%)" if c >= 1 else f"{chg_pct:+.2f}%",
        font=font_sm,
        fill=chg_col,
    )

    if WATERMARK:
        tw = draw.textlength(WATERMARK, font=font_wm)
        wx = int((W - tw) / 2)
        wy = int(pad_t + plot_h * 0.48)
        draw.text((wx + scale, wy + scale), WATERMARK, font=font_wm, fill=(18, 18, 22))
        draw.text((wx, wy), WATERMARK, font=font_wm, fill=(55, 55, 65))

    draw.text((pad_l, H - 16 * scale), "TV", font=font_xs, fill=(50, 50, 55))

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
