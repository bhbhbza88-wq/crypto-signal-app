"""
Chart for outlook: TradingView-like dark (green/red candles + blue trendlines)
+ right-side future padding for direction path (like TB / Bukvar charts).
OHLC/levels from Bybit; drawing is local.
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from data_layer import build_features, fetch_ohlcv_raw

CHART_IMG_API_KEY = (os.getenv("CHART_IMG_API_KEY") or "").strip()
CHART_INTERVAL = (os.getenv("OUTLOOK_CHART_INTERVAL", "240") or "240").strip()
CHART_WIDTH = int(os.getenv("OUTLOOK_CHART_WIDTH", "1200") or "1200")
CHART_HEIGHT = int(os.getenv("OUTLOOK_CHART_HEIGHT", "675") or "675")
EXCHANGE_TV = (os.getenv("OUTLOOK_TV_EXCHANGE", "BYBIT") or "BYBIT").strip().upper()
WATERMARK = (os.getenv("OUTLOOK_CHART_WATERMARK") or "nowicki").strip()
RENDER_TF = (os.getenv("OUTLOOK_CHART_TF", "4h") or "4h").strip()
RENDER_BARS = int(os.getenv("OUTLOOK_CHART_BARS", "100") or "100")
# Share of plot width reserved as empty "future" for the direction arrow.
FUTURE_RATIO = float(os.getenv("OUTLOOK_CHART_FUTURE_RATIO", "0.22") or "0.22")
FUTURE_RATIO = min(0.35, max(0.16, FUTURE_RATIO))

_ICON_DIR = os.path.join(os.getenv("DATA_DIR", "."), "coin_icons")
_ICON_BYTES_CACHE: dict[str, bytes | None] = {}
_ICON_CDN = (
    "https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/{sym}.png"
)


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


def _fetch_coin_icon_bytes(base: str) -> bytes | None:
    """PNG bytes for a coin logo ? disk cache under DATA_DIR, then CDN, memoized."""
    base = base.lower().strip()
    if base in _ICON_BYTES_CACHE:
        return _ICON_BYTES_CACHE[base]
    path = os.path.join(_ICON_DIR, f"{base}.png")
    data: bytes | None = None
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
    except OSError:
        data = None
    if not data:
        try:
            with httpx.Client(timeout=6) as client:
                r = client.get(_ICON_CDN.format(sym=base))
                if r.status_code == 200 and r.content and len(r.content) > 200:
                    data = r.content
                    try:
                        os.makedirs(_ICON_DIR, exist_ok=True)
                        with open(path, "wb") as f:
                            f.write(data)
                    except OSError:
                        pass
        except Exception:
            data = None
    _ICON_BYTES_CACHE[base] = data
    return data


def _draw_coin_icon(img: Image.Image, symbol: str, *, x: int, y: int, size: int) -> None:
    """Paste the coin logo at (x, y); fall back to an initials badge if unavailable."""
    base = symbol.replace("/USDT", "").upper().strip()
    data = _fetch_coin_icon_bytes(base)
    if data:
        try:
            icon = Image.open(io.BytesIO(data)).convert("RGBA").resize(
                (size, size), Image.Resampling.LANCZOS
            )
            img.paste(icon, (x, y), icon)
            return
        except Exception:
            pass
    fallback = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fallback)
    palette = [
        (60, 120, 220), (220, 120, 60), (120, 80, 220),
        (50, 180, 140), (220, 70, 120), (200, 170, 40),
    ]
    col = palette[sum(ord(c) for c in base) % len(palette)]
    fd.ellipse([0, 0, size, size], fill=(*col, 255))
    letter = base[:1] or "?"
    lf = _font(int(size * 0.55), bold=True)
    tw = fd.textlength(letter, font=lf)
    fd.text(((size - tw) / 2, size * 0.16), letter, font=lf, fill=(255, 255, 255, 255))
    img.paste(fallback, (x, y), fallback)


def _draw_dashed_hline(
    draw: ImageDraw.ImageDraw,
    x0: int,
    x1: int,
    y: int,
    color: tuple[int, int, int, int],
    *,
    dash: int,
    gap: int,
    width: int,
) -> None:
    x = x0
    while x < x1:
        xe = min(x + dash, x1)
        draw.line([(x, y), (xe, y)], fill=color, width=width)
        x += dash + gap


def _swing_pivots(
    df: pd.DataFrame,
    kind: str,
    order: int = 3,
) -> list[tuple[int, float]]:
    """Local swing highs/lows (pivot left=right=order)."""
    col = "high" if kind == "high" else "low"
    vals = df[col].astype(float).to_numpy()
    n = len(vals)
    order = max(2, min(order, max(2, n // 20)))
    out: list[tuple[int, float]] = []
    for i in range(order, n - order):
        window = vals[i - order : i + order + 1]
        v = vals[i]
        if kind == "high":
            if v >= float(window.max()) - 1e-12 and v == float(window.max()):
                out.append((i, float(v)))
        else:
            if v <= float(window.min()) + 1e-12 and v == float(window.min()):
                out.append((i, float(v)))
    return out


def _line_price(i1: int, y1: float, i2: int, y2: float, i: float) -> float:
    if i2 == i1:
        return y1
    return y1 + (y2 - y1) * ((i - i1) / (i2 - i1))


def _cluster_levels(
    pivots: list[tuple[int, float]],
    *,
    atr: float,
    last_c: float,
    kind: str,
    max_levels: int = 1,
) -> list[float]:
    """Merge nearby swing prices into the main horizontal S/R (not mid clutter)."""
    if not pivots:
        return []
    atr = max(atr, last_c * 0.004)
    tol = atr * 0.45
    ordered = sorted(pivots, key=lambda p: p[0], reverse=True)
    clusters: list[list[float]] = []
    for _, price in ordered:
        placed = False
        for cluster in clusters:
            if abs(sum(cluster) / len(cluster) - price) <= tol:
                cluster.append(price)
                placed = True
                break
        if not placed:
            clusters.append([price])

    scored: list[tuple[float, float]] = []
    for cluster in clusters:
        lvl = sum(cluster) / len(cluster)
        if abs(lvl - last_c) / last_c > 0.10:
            continue
        # Only true opposite-side levels (R above / S below), with air from price.
        if kind == "high":
            if lvl < last_c + atr * 0.25:
                continue
        else:
            if lvl > last_c - atr * 0.25:
                continue
        # Prefer multi-touch bases; single random mid-swing is weak.
        if len(cluster) < 2 and abs(lvl - last_c) < atr * 1.1:
            continue
        strength = len(cluster) * 3.0 - abs(lvl - last_c) / atr
        scored.append((strength, lvl))
    scored.sort(reverse=True)
    return [lvl for _, lvl in scored[:max_levels]]


def _best_trendline(
    pivots: list[tuple[int, float]],
    *,
    kind: str,
    n_bars: int,
    atr: float,
    last_c: float,
    range_low: float | None = None,
    range_high: float | None = None,
) -> tuple[int, float, int, float] | None:
    """
    Pick the most valid structure line:
    - connects 2 swing pivots
    - other pivots touch it
    - price mostly respects it (below resistance / above support)
    - still relevant near the right edge
    - support stays in lower band, resistance in upper band
    """
    if len(pivots) < 2:
        return None
    atr = max(atr, last_c * 0.004)
    touch_tol = atr * 0.28
    min_gap = max(6, n_bars // 14)
    r_lo = range_low if range_low is not None else last_c * 0.9
    r_hi = range_high if range_high is not None else last_c * 1.1
    r_mid = (r_lo + r_hi) / 2.0
    best: tuple[int, float, int, float] | None = None
    best_score = -1e18

    for a in range(len(pivots)):
        for b in range(a + 1, len(pivots)):
            i1, y1 = pivots[a]
            i2, y2 = pivots[b]
            if i2 - i1 < min_gap:
                continue

            touches = 0
            for ip, yp in pivots:
                if ip in (i1, i2):
                    continue
                ly = _line_price(i1, y1, i2, y2, ip)
                if abs(yp - ly) <= touch_tol:
                    touches += 1

            end_y = _line_price(i1, y1, i2, y2, n_bars - 1)
            violations = 0
            for ip, yp in pivots:
                ly = _line_price(i1, y1, i2, y2, ip)
                if kind == "high" and yp > ly + touch_tol:
                    violations += 1
                if kind == "low" and yp < ly - touch_tol:
                    violations += 1

            dist = abs(end_y - last_c) / atr
            if dist > 6.5:
                continue
            side_ok = 1.0
            if kind == "high" and end_y < last_c - atr * 0.15:
                side_ok = 0.35
            if kind == "low" and end_y > last_c + atr * 0.15:
                side_ok = 0.35

            # Keep support near bottoms / resistance near tops (not mid-chart).
            avg_y = (y1 + y2 + end_y) / 3.0
            band_pen = 0.0
            if kind == "low" and avg_y > r_mid:
                band_pen = 3.5 + (avg_y - r_mid) / atr
            if kind == "high" and avg_y < r_mid:
                band_pen = 3.5 + (r_mid - avg_y) / atr

            length = (i2 - i1) / max(1, n_bars)
            recency = i2 / max(1, n_bars - 1)
            score = (
                touches * 3.2
                + length * 4.0
                + recency * 3.5
                - violations * 2.4
                - dist * 0.55
                - band_pen
            ) * side_ok

            if kind == "high" and y2 <= y1:
                score += 0.8
            if kind == "low" and y2 >= y1:
                score += 0.8

            if score > best_score:
                best_score = score
                best = (i1, y1, i2, y2)

    return best


def _zone_from_candle(
    df: pd.DataFrame,
    idx: int,
    *,
    kind: str,
    atr: float,
) -> tuple[float, float, float]:
    """Order-block style box from the swing candle (+ small pad)."""
    i = int(max(0, min(len(df) - 1, idx)))
    row = df.iloc[i]
    o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    pad = atr * 0.08
    if kind == "supply":
        # Body top ? wick high (resistance base).
        body_lo = min(o, c)
        top = h + pad
        bot = min(body_lo, h - atr * 0.35)
        # Keep a readable band.
        if top - bot < atr * 0.35:
            bot = top - atr * 0.45
        if top - bot > atr * 1.35:
            bot = top - atr * 1.35
        mid = (top + bot) / 2.0
        return float(top), float(bot), float(mid)
    body_hi = max(o, c)
    bot = l - pad
    top = max(body_hi, l + atr * 0.35)
    if top - bot < atr * 0.35:
        top = bot + atr * 0.45
    if top - bot > atr * 1.35:
        top = bot + atr * 1.35
    mid = (top + bot) / 2.0
    return float(top), float(bot), float(mid)


def _build_zones(
    df: pd.DataFrame,
    highs: list[tuple[int, float]],
    lows: list[tuple[int, float]],
    *,
    atr: float,
    last_c: float,
) -> list[dict[str, Any]]:
    """Always try for 1 grey supply (above) + 1 grey demand (below), Bukvar-style."""
    atr = max(atr, last_c * 0.004)
    n = len(df)
    zones: list[dict[str, Any]] = []

    def _score(kind: str, i: int, pivot: float) -> float | None:
        dist = (pivot - last_c) / atr if kind == "supply" else (last_c - pivot) / atr
        # Allow zones on price (testing) and up to ~7 ATR / ~8% away.
        if dist < -0.15:
            return None
        max_dist = max(7.0, (last_c * 0.08) / atr)
        if dist > max_dist:
            return None
        # Prefer a clear band (~1.3-4 ATR), not a hairline under last price.
        sweet = -abs(dist - 2.3) * 0.9
        if 1.2 <= dist <= 4.0:
            sweet += 1.8
        if dist < 0.8:
            sweet -= 1.4  # too glued to price unless it's the only option
        recency = i / max(1, n - 1)
        return sweet + recency * 1.2

    def _pick(kind: str, pivots: list[tuple[int, float]]) -> dict[str, Any] | None:
        scored: list[tuple[float, dict[str, Any]]] = []
        for i, p in pivots:
            sc = _score(kind, i, p)
            if sc is None:
                continue
            top, bot, mid = _zone_from_candle(df, i, kind=kind, atr=atr)
            if kind == "supply" and bot <= last_c + atr * 0.05:
                # Shift box so it overhangs when price is pressing / broke the pivot.
                lift = max(0.0, last_c + atr * 0.08 - bot)
                top += lift
                bot += lift
                mid = (top + bot) / 2.0
                if bot < last_c - atr * 0.25:
                    continue
            if kind == "demand" and top >= last_c - atr * 0.05:
                drop = max(0.0, top - (last_c - atr * 0.08))
                top -= drop
                bot -= drop
                mid = (top + bot) / 2.0
                if top > last_c + atr * 0.25:
                    continue
            scored.append(
                (
                    sc,
                    {
                        "kind": kind,
                        "top": float(top),
                        "bot": float(bot),
                        "start_i": int(max(0, i - 3)),
                        "mid": float(mid),
                        "score": float(sc),
                        "fallback": False,
                    },
                )
            )
        if not scored:
            return None
        scored.sort(reverse=True)
        return scored[0][1]

    supply = _pick("supply", highs[-14:])
    demand = _pick("demand", lows[-14:])

    # Fallbacks from strongest recent swing / visible extreme so both sides exist.
    if supply is None and highs:
        i, p = max(highs[-8:], key=lambda t: t[1])
        top, bot, mid = _zone_from_candle(df, i, kind="supply", atr=atr)
        if mid < last_c:
            shift = (last_c + atr * 0.25) - mid
            top += shift
            bot += shift
            mid += shift
        supply = {
            "kind": "supply",
            "top": float(top),
            "bot": float(bot),
            "start_i": int(max(0, i - 3)),
            "mid": float(mid),
            "score": -99.0,
            "fallback": True,
        }
    if demand is None and lows:
        i, p = min(lows[-8:], key=lambda t: t[1])
        top, bot, mid = _zone_from_candle(df, i, kind="demand", atr=atr)
        if mid > last_c:
            shift = mid - (last_c - atr * 0.25)
            top -= shift
            bot -= shift
            mid -= shift
        demand = {
            "kind": "demand",
            "top": float(top),
            "bot": float(bot),
            "start_i": int(max(0, i - 3)),
            "mid": float(mid),
            "score": -99.0,
            "fallback": True,
        }

    if supply:
        zones.append(supply)
    if demand:
        zones.append(demand)
    return zones


def _structure_from_df(
    df: pd.DataFrame,
    *,
    atr: float,
    last_c: float,
    bias: str = "long",
    key_level: float | None = None,
) -> dict[str, Any]:
    """Zones (1 supply + 1 demand) + single orange key level. No trendline clutter."""
    n = len(df)
    default_order = 3 if n < 90 else 4

    # Try a few pivot resolutions and keep the one that yields real (non-fallback)
    # zones with the strongest score ? avoids a single fixed `order` missing the
    # cleanest swing on a given symbol/regime.
    best: tuple[list[tuple[int, float]], list[tuple[int, float]], list[dict[str, Any]]] | None = None
    best_rank: tuple[int, float, int] | None = None
    for order in sorted({max(2, default_order - 1), default_order, default_order + 1, default_order + 2}):
        h = _swing_pivots(df, "high", order=order)[-14:]
        l = _swing_pivots(df, "low", order=order)[-14:]
        if not h or not l:
            continue
        z = _build_zones(df, h, l, atr=atr, last_c=last_c)
        fallback_n = sum(1 for x in z if x.get("fallback"))
        total_score = sum(float(x.get("score") or 0.0) for x in z)
        rank = (-fallback_n, total_score, len(h) + len(l))
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best = (h, l, z)

    if best is not None:
        highs, lows, zones = best
    else:
        highs = _swing_pivots(df, "high", order=default_order)[-14:]
        lows = _swing_pivots(df, "low", order=default_order)[-14:]
        zones = _build_zones(df, highs, lows, atr=atr, last_c=last_c)

    range_low = float(df["low"].astype(float).min())
    range_high = float(df["high"].astype(float).max())

    h_res = _cluster_levels(highs, atr=atr, last_c=last_c, kind="high", max_levels=1)
    h_sup = _cluster_levels(lows, atr=atr, last_c=last_c, kind="low", max_levels=1)

    swing_high = max((p for _, p in highs), default=range_high)
    swing_low = min((p for _, p in lows), default=range_low)
    # Resistance: nearest meaningful high at/above price (incl. local high being tested).
    above = [p for _, p in highs if p >= last_c - atr * 0.15]
    below = [p for _, p in lows if p <= last_c + atr * 0.15]
    resistance = min(above, default=swing_high) if above else (
        min([p for p in h_res if p >= last_c], default=swing_high)
    )
    support = max(below, default=swing_low) if below else (
        max([p for p in h_sup if p <= last_c], default=swing_low)
    )

    demand_mid = next((float(z["mid"]) for z in zones if z["kind"] == "demand"), support)
    supply_mid = next((float(z["mid"]) for z in zones if z["kind"] == "supply"), resistance)

    # One orange key: explicit override, else bias-aware watch level.
    kl = _fnum(key_level)
    if kl is None:
        if (bias or "long").lower() == "short":
            kl = supply_mid if supply_mid >= last_c - atr * 0.2 else resistance
        else:
            kl = demand_mid if demand_mid <= last_c + atr * 0.2 else support
    orange_levels = [float(kl)] if kl else []

    return {
        "res_tl": None,
        "sup_tl": None,
        "h_res": h_res,
        "h_sup": h_sup,
        "zones": zones,
        "orange_levels": orange_levels,
        "key_level": float(kl) if kl else None,
        "swing_high": float(swing_high),
        "swing_low": float(swing_low),
        "resistance": float(resistance),
        "support": float(support),
        "demand_mid": float(demand_mid),
        "supply_mid": float(supply_mid),
    }


def key_level_mtf_confirmed(
    symbol: str,
    key_level: float,
    *,
    atr: float | None = None,
    exchange_id: str = "bybit",
) -> bool:
    """True if the 4h key level also lines up with a swing high/low on the daily chart."""
    try:
        raw = fetch_ohlcv_raw(symbol, "1d", limit=120, exchange_id=exchange_id)
        if not raw or len(raw) < 30:
            return False
        cols = ["timestamp", "open", "high", "low", "close", "volume"]
        df = build_features(pd.DataFrame(raw, columns=cols)).reset_index(drop=True)
        if len(df) < 20:
            return False
        last_c = float(df["close"].iloc[-1])
        atr_d = _fnum(df.iloc[-1].get("atr")) if "atr" in df.columns else None
        if atr_d is None:
            atr_d = float((df["high"].astype(float) - df["low"].astype(float)).tail(14).mean())
        tol = max(atr_d, _fnum(atr) or 0.0, last_c * 0.006)
        highs = _swing_pivots(df, "high", order=3)
        lows = _swing_pivots(df, "low", order=3)
        levels = [p for _, p in highs] + [p for _, p in lows]
        return any(abs(p - key_level) <= tol for p in levels)
    except Exception:
        return False


def _tf_delta(tf: str) -> timedelta:
    t = (tf or "4h").lower().strip()
    if t.endswith("m"):
        return timedelta(minutes=int(t[:-1] or 15))
    if t.endswith("h"):
        return timedelta(hours=int(t[:-1] or 4))
    if t.endswith("d"):
        return timedelta(days=int(t[:-1] or 1))
    return timedelta(hours=4)


def _fnum(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None:
            return default
        n = float(v)
        if n != n:  # NaN
            return default
        return n
    except (TypeError, ValueError):
        return default


def _forecast_price_path(
    last_c: float,
    bias: str,
    *,
    atr: float | None = None,
    support: float | None = None,
    resistance: float | None = None,
    target: float | None = None,
    target_2: float | None = None,
    invalidation: float | None = None,
    swing_low: float | None = None,
    swing_high: float | None = None,
    visible_span: float | None = None,
    timeframe: str | None = None,
) -> list[float]:
    """Build angular path from structure; amplify bends on higher TFs (4h)."""
    if last_c <= 0:
        return [last_c]

    atr_v = _fnum(atr) or (last_c * 0.012)
    atr_v = max(atr_v, last_c * 0.004)
    span = _fnum(visible_span) or (atr_v * 8.0)
    span = max(span, atr_v * 3.0)

    tf = (timeframe or "").lower().strip()
    # On 4h the chart range is wide ? force bends to eat a real chunk of height.
    if tf in ("4h", "240", "1d", "1D", "d"):
        dump_min = max(atr_v * 1.0, span * 0.13)
        dump_max = max(atr_v * 2.1, span * 0.22)
        drive_min = max(atr_v * 1.9, span * 0.22)
        drive_max = max(atr_v * 3.6, span * 0.34)
    else:
        dump_min = atr_v * 0.35
        dump_max = atr_v * 1.4
        drive_min = atr_v * 1.05
        drive_max = atr_v * 2.8

    going_up = bias != "short"

    if going_up:
        below = [
            p
            for p in (_fnum(support), _fnum(swing_low), last_c - dump_min)
            if p is not None and p < last_c * 0.999
        ]
        grab = max(below) if below else (last_c - dump_min)
        grab = min(grab, last_c - dump_min)
        grab = max(grab, last_c - dump_max, last_c * 0.955)

        tip = _fnum(target)
        t2 = _fnum(target_2)
        if tip is None or tip <= last_c + drive_min * 0.45:
            tip = t2 if (t2 and t2 > last_c) else _fnum(resistance)
        if tip is None or tip <= last_c:
            tip = last_c + drive_min
        tip = max(tip, last_c + drive_min)
        tip = min(tip, last_c + drive_max)

        mid = last_c - (last_c - grab) * 0.55
        return [last_c, mid, grab, tip]

    above = [
        p
        for p in (_fnum(resistance), _fnum(swing_high), last_c + dump_min)
        if p is not None and p > last_c * 1.001
    ]
    grab = min(above) if above else (last_c + dump_min)
    grab = max(grab, last_c + dump_min)
    grab = min(grab, last_c + dump_max, last_c * 1.045)

    tip = _fnum(target)
    if tip is None or tip >= last_c - drive_min * 0.45:
        tip = _fnum(invalidation) or _fnum(support)
    if tip is None or tip >= last_c:
        tip = last_c - drive_min
    tip = min(tip, last_c - drive_min)
    tip = max(tip, last_c - drive_max)

    mid = last_c + (grab - last_c) * 0.55
    return [last_c, mid, grab, tip]


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    tip: tuple[int, int],
    prev: tuple[int, int],
    color: tuple[int, int, int],
    scale: int,
) -> None:
    import math

    dx = float(tip[0] - prev[0])
    dy = float(tip[1] - prev[1])
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    length_h = 15 * scale
    half_w = 8 * scale
    bx = tip[0] - ux * length_h
    by = tip[1] - uy * length_h
    left = (int(bx + px * half_w), int(by + py * half_w))
    right = (int(bx - px * half_w), int(by - py * half_w))
    draw.polygon([tip, left, right], fill=color)


def _draw_direction_path(
    draw: ImageDraw.ImageDraw,
    *,
    yx: Callable[[float], int],
    pad_l: int,
    pad_r: int,
    pad_t: int,
    plot_h: int,
    hist_right: int,
    plot_right: int,
    W: int,
    scale: int,
    last_c: float,
    target: float,
    bias: str,
    candle_w: int,
    green: tuple[int, int, int],
    red: tuple[int, int, int],
    atr: float | None = None,
    support: float | None = None,
    resistance: float | None = None,
    invalidation: float | None = None,
    swing_low: float | None = None,
    swing_high: float | None = None,
    target_2: float | None = None,
    visible_span: float | None = None,
    timeframe: str | None = None,
):
    """Angular polyline from structure levels; segment color by direction."""
    del pad_l, pad_r, W, candle_w
    if last_c <= 0:
        return

    prices = _forecast_price_path(
        last_c,
        bias,
        atr=atr,
        support=support,
        resistance=resistance,
        target=target,
        target_2=target_2,
        invalidation=invalidation,
        swing_low=swing_low,
        swing_high=swing_high,
        visible_span=visible_span,
        timeframe=timeframe,
    )
    n = len(prices)
    if n < 2:
        return

    span = max(40 * scale, plot_right - hist_right)
    # Compact liquidity leg, longer impulse leg.
    if n == 4:
        fracs = [0.0, 0.20, 0.36, 0.94]
    else:
        fracs = [i / (n - 1) * 0.94 for i in range(n)]
    xs = [hist_right + int(span * fracs[i]) for i in range(n)]

    path: list[tuple[int, int]] = []
    for i in range(n):
        y = int(min(max(yx(prices[i]), pad_t + 2), pad_t + plot_h - 2))
        x = min(xs[i], plot_right - 2 * scale)
        path.append((x, y))

    last_color = green if bias != "short" else red
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        seg_up = prices[i + 1] >= prices[i]
        col = green if seg_up else red
        last_color = col
        draw.line([a, b], fill=col, width=4 * scale)

    x0, y0 = path[0]
    r = 3 * scale
    start_col = green if prices[1] >= prices[0] else red
    draw.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=start_col)
    _draw_arrowhead(draw, path[-1], path[-2], last_color, scale)


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
    pad_l, pad_r, pad_t, pad_b = 18 * scale, 92 * scale, 52 * scale, 36 * scale
    # Bukvar charts are clean ? no volume strip (more room for zones + path).
    vol_h = 0
    plot_h = H - pad_t - pad_b - vol_h - 8 * scale
    plot_w = W - pad_l - pad_r
    hist_w = int(plot_w * (1.0 - FUTURE_RATIO))
    future_w = plot_w - hist_w
    hist_right = pad_l + hist_w
    plot_right = pad_l + plot_w
    vol_top = pad_t + plot_h + 6 * scale

    highs = df["high"].astype(float)
    lows = df["low"].astype(float)
    closes = df["close"].astype(float)
    vols = df["volume"].astype(float)
    lv = levels or {}
    last_c0 = float(closes.iloc[-1])
    bias_norm = (bias or "long").strip().lower()
    if bias_norm not in ("long", "short"):
        bias_norm = "long"

    atr_v = _fnum(df.iloc[-1]["atr"]) if "atr" in df.columns else None
    if atr_v is None:
        atr_v = float((highs - lows).tail(14).mean()) if len(df) >= 14 else last_c0 * 0.012

    structure = _structure_from_df(
        df,
        atr=float(atr_v),
        last_c=last_c0,
        bias=bias_norm,
        key_level=_fnum(lv.get("key_level")),
    )
    swing_low = float(structure["swing_low"])
    swing_high = float(structure["swing_high"])

    # Prefer chart structure; fall back to outlook scan levels.
    support_v = structure["support"]
    resistance_v = structure["resistance"]
    scan_sup = _fnum(lv.get("support"))
    scan_res = _fnum(lv.get("resistance"))
    if scan_sup is not None and abs(scan_sup - last_c0) / last_c0 < 0.08:
        # Blend: nearest real support wins if within ATR of scan.
        if abs(support_v - scan_sup) > atr_v * 0.8:
            support_v = scan_sup if abs(scan_sup - last_c0) < abs(support_v - last_c0) else support_v
    if scan_res is not None and abs(scan_res - last_c0) / last_c0 < 0.08:
        if abs(resistance_v - scan_res) > atr_v * 0.8:
            resistance_v = scan_res if abs(scan_res - last_c0) < abs(resistance_v - last_c0) else resistance_v

    invalidation_v = _fnum(lv.get("invalidation")) or min(support_v, swing_low) * 0.995
    target_2_v = _fnum(lv.get("target_2"))
    target_1_scan = _fnum(lv.get("target_1"))
    # Target: structural resistance / scan target, whichever is the next real upside.
    if bias_norm == "short":
        target = _fnum(lv.get("fail_zone")) or invalidation_v or support_v
        if target is None or target >= last_c0:
            target = last_c0 - atr_v * 1.2
    else:
        cands = [p for p in (resistance_v, target_1_scan, target_2_v) if p and p > last_c0]
        target = min(cands) if cands else (last_c0 + atr_v * 1.4)
        if target <= last_c0:
            target = target_2_v if (target_2_v and target_2_v > last_c0) else (last_c0 + atr_v * 1.4)

    # Candle span first ? used to size 4h bends so they read on a wide chart.
    visible_span = float(highs.max() - lows.min()) or (atr_v * 8.0)

    path_preview = _forecast_price_path(
        last_c0,
        bias_norm,
        atr=atr_v,
        support=support_v,
        resistance=resistance_v,
        target=target,
        target_2=target_2_v,
        invalidation=invalidation_v,
        swing_low=swing_low,
        swing_high=swing_high,
        visible_span=visible_span,
        timeframe=tf,
    )

    y_min, y_max = float(lows.min()), float(highs.max())
    for k in ("support", "resistance", "target_1", "target_2"):
        try:
            if lv.get(k) is not None:
                v = float(lv[k])
                if abs(v - last_c0) / last_c0 < 0.18:
                    y_min = min(y_min, v)
                    y_max = max(y_max, v)
        except (TypeError, ValueError):
            pass
    for p in (support_v, resistance_v, swing_low, swing_high):
        if p is not None:
            y_min = min(y_min, float(p))
            y_max = max(y_max, float(p))
    for p in (structure.get("h_res") or []) + (structure.get("h_sup") or []):
        y_min = min(y_min, float(p))
        y_max = max(y_max, float(p))
    for z in structure.get("zones") or []:
        y_min = min(y_min, float(z["bot"]))
        y_max = max(y_max, float(z["top"]))
    for p in path_preview:
        y_min = min(y_min, p)
        y_max = max(y_max, p)

    pad_y = (y_max - y_min) * 0.06 or y_max * 0.01
    y_min -= pad_y
    y_max += pad_y
    if y_max <= y_min:
        y_max = y_min * 1.01 + 1e-9

    def yx(price: float) -> int:
        return int(pad_t + (1.0 - (price - y_min) / (y_max - y_min)) * plot_h)

    def xx(i: float) -> int:
        """Map bar index onto historical (left) strip only."""
        n = max(1, len(df) - 1)
        return int(pad_l + (float(i) / n) * hist_w)

    bg = (8, 10, 14)
    grid = (28, 32, 40)
    text_muted = (120, 130, 150)
    text_main = (220, 224, 230)
    # Path + candle colors (classic green/red).
    green = (8, 153, 129)
    red = (242, 54, 69)
    candle_up = green
    candle_dn = red
    orange = (230, 140, 50)
    zone_fill = (90, 95, 105)

    img = Image.new("RGBA", (W, H), (*bg, 255))
    draw = ImageDraw.Draw(img)
    # ????????? ??????? ??? ????????????? timeframe/???/???????
    font_xs = _font(14 * scale)
    font_sm = _font(15 * scale)
    font_lg = _font(18 * scale, bold=True)
    font_price = _font(15 * scale, bold=True)
    font_wm = _font(28 * scale)

    n_grid = 7
    for g in range(n_grid):
        frac = g / (n_grid - 1)
        yy = pad_t + int(plot_h * frac)
        _draw_dashed_hline(
            draw, pad_l, plot_right, yy, (*grid, 160), dash=6 * scale, gap=5 * scale, width=scale
        )
        draw.text(
            (plot_right + 8 * scale, yy - 7 * scale),
            _fmt(y_max - (y_max - y_min) * frac),
            font=font_xs,
            fill=text_muted,
        )

    # Soft vertical divider at end of history (subtle).
    draw.line(
        [(hist_right, pad_t), (hist_right, pad_t + plot_h)],
        fill=(32, 36, 44, 255),
        width=scale,
    )

    ts_col = df["timestamp"]
    step = max(1, len(df) // 5)
    for i in range(0, len(df), step):
        x = xx(i)
        for yy0 in range(pad_t, pad_t + plot_h, 9 * scale):
            draw.line(
                [(x, yy0), (x, min(yy0 + 5 * scale, pad_t + plot_h))],
                fill=(*grid, 130),
                width=scale,
            )
        try:
            ts = int(ts_col.iloc[i])
            if ts > 10_000_000_000:
                ts //= 1000
            lbl = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d %b")
        except Exception:
            lbl = ""
        if lbl:
            draw.text((x - 14 * scale, H - 22 * scale), lbl, font=font_xs, fill=text_muted)

    # Future date ticks in the empty right margin (Bukvar-style).
    try:
        last_ts = int(ts_col.iloc[-1])
        if last_ts > 10_000_000_000:
            last_ts //= 1000
        last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        delta = _tf_delta(tf)
        for fi in (1, 2, 3):
            fx = hist_right + int(future_w * (fi / 3.5))
            if fx >= plot_right - 4 * scale:
                continue
            draw.line([(fx, pad_t), (fx, pad_t + plot_h)], fill=(26, 28, 34, 255), width=scale)
            ahead = max(1, int(len(df) * FUTURE_RATIO * (fi / 3)))
            fdt = last_dt + delta * ahead
            draw.text(
                (fx - 14 * scale, H - 22 * scale),
                fdt.strftime("%d %b"),
                font=font_xs,
                fill=text_muted,
            )
    except Exception:
        pass

    candle_w = max(2 * scale, int((hist_w / max(1, len(df))) * 0.68))

    # Supply/demand zones (semi-transparent), full width into future like Bukvar.
    zone_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    zd = ImageDraw.Draw(zone_layer)
    for z in structure.get("zones") or []:
        y_top = yx(float(z["top"]))
        y_bot = yx(float(z["bot"]))
        if y_bot < y_top:
            y_top, y_bot = y_bot, y_top
        x0 = xx(float(z.get("start_i") or 0))
        zd.rectangle(
            [x0, y_top, plot_right, y_bot],
            fill=(*zone_fill, 55),
        )
    img = Image.alpha_composite(img, zone_layer)
    draw = ImageDraw.Draw(img)

    # Cyrillic labels via unicode escapes on purpose ? keeps them safe from
    # encoding mangling regardless of how this file gets saved.
    lbl_supply = "\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435"  # "Predlozhenie"
    lbl_demand = "\u0421\u043f\u0440\u043e\u0441"  # "Spros"
    zone_label_ru = {"supply": lbl_supply, "demand": lbl_demand}
    zone_label_col = {"supply": (235, 150, 150), "demand": (150, 210, 190)}

    # Single orange key level (the one referenced in the post text).
    mtf_confirmed = bool(lv.get("mtf_confirmed"))
    for p in structure.get("orange_levels") or []:
        yy = yx(float(p))
        if yy < pad_t or yy > pad_t + plot_h:
            continue
        draw.line([(pad_l, yy), (hist_right, yy)], fill=(*orange, 255), width=2 * scale)
        draw.line(
            [(hist_right, yy), (hist_right + int(future_w * 0.25), yy)],
            fill=(*orange, 180),
            width=2 * scale,
        )
        badge = _fmt(float(p)) + (" 1D" if mtf_confirmed else "")
        bw = int(draw.textlength(badge, font=font_xs)) + 8 * scale
        draw.rectangle(
            [plot_right + 4 * scale, yy - 8 * scale, plot_right + 4 * scale + bw, yy + 8 * scale],
            fill=(*orange, 255),
        )
        draw.text((plot_right + 8 * scale, yy - 7 * scale), badge, font=font_xs, fill=(20, 20, 20))

    # Candles: green up / red down.
    for i, row in df.iterrows():
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        x = xx(int(i))
        color = candle_up if c >= o else candle_dn
        draw.line([(x, yx(h)), (x, yx(l))], fill=(*color, 255), width=scale)
        y1, y2 = yx(max(o, c)), yx(min(o, c))
        if y2 <= y1:
            y2 = y1 + scale
        draw.rectangle([x - candle_w // 2, y1, x + candle_w // 2, y2], fill=(*color, 255))

    last = df.iloc[-1]
    last_c = last_c0

    _draw_direction_path(
        draw,
        yx=yx,
        pad_l=pad_l,
        pad_r=pad_r,
        pad_t=pad_t,
        plot_h=plot_h,
        hist_right=hist_right,
        plot_right=plot_right,
        W=W,
        scale=scale,
        last_c=last_c,
        target=float(target),
        bias=bias_norm,
        candle_w=candle_w,
        green=green,
        red=red,
        atr=atr_v,
        support=support_v,
        resistance=resistance_v,
        invalidation=invalidation_v,
        swing_low=swing_low,
        swing_high=swing_high,
        target_2=target_2_v,
        visible_span=visible_span,
        timeframe=tf,
    )

    # Zone labels drawn last (on top of candles/lines) so they stay legible
    # even when a key/guide line crosses a thin zone.
    for z in structure.get("zones") or []:
        kind = z.get("kind")
        ru = zone_label_ru.get(kind)
        if not ru:
            continue
        y_top = yx(float(z["top"]))
        y_bot = yx(float(z["bot"]))
        if y_bot < y_top:
            y_top, y_bot = y_bot, y_top
        x0 = xx(float(z.get("start_i") or 0))
        label = f"{ru}  {_fmt(float(z['bot']))}-{_fmt(float(z['top']))}"
        tw = int(draw.textlength(label, font=font_xs))
        lx = min(x0 + 6 * scale, plot_right - tw - 6 * scale)
        lx = max(lx, pad_l + 4 * scale)
        text_h = 16 * scale
        if (y_bot - y_top) >= text_h + 6 * scale:
            ly = y_top + 3 * scale
        else:
            ly = max(pad_t, y_top - text_h - 2 * scale)
        draw.rectangle(
            [lx - 3 * scale, ly - 2 * scale, lx + tw + 3 * scale, ly + 13 * scale],
            fill=(10, 12, 16, 165),
        )
        draw.text((lx, ly), label, font=font_xs, fill=zone_label_col.get(kind, text_muted))

    last_o = float(last["open"])
    py = yx(last_c)
    badge = _fmt(last_c)
    bw = int(draw.textlength(badge, font=font_price)) + 14 * scale
    bh = 22 * scale
    badge_color = green if last_c >= last_o else red
    text_on_badge = (255, 255, 255)
    draw.rounded_rectangle(
        [plot_right + 4 * scale, py - bh // 2, plot_right + 4 * scale + bw, py + bh // 2],
        radius=3 * scale,
        fill=(*badge_color, 255),
    )
    draw.text((plot_right + 11 * scale, py - 8 * scale), badge, font=font_price, fill=text_on_badge)
    x0 = hist_right
    dash_end = hist_right + int((plot_right - hist_right) * 0.18)
    while x0 < dash_end:
        draw.line([(x0, py), (min(x0 + 6 * scale, dash_end), py)], fill=(*badge_color, 255), width=scale)
        x0 += 11 * scale

    o, h, l, c = float(last["open"]), float(last["high"]), float(last["low"]), float(last["close"])
    chg = c - o
    chg_pct = (chg / o * 100) if o else 0
    chg_color = green if chg >= 0 else red

    icon_size = 20 * scale
    icon_x, icon_y = pad_l, 8 * scale
    _draw_coin_icon(img, symbol, x=icon_x, y=icon_y, size=icon_size)
    draw = ImageDraw.Draw(img)
    title_x = icon_x + icon_size + 8 * scale

    title = f"{_pretty_name(symbol)} | {str(tf).upper()} | {exchange_id.capitalize()}"
    draw.text((title_x, 10 * scale), title, font=font_lg, fill=text_main)
    ohlc = f"O{_fmt(o)}  H{_fmt(h)}  L{_fmt(l)}  C{_fmt(c)}  "
    draw.text((title_x, 30 * scale), ohlc, font=font_sm, fill=text_muted)
    chg_s = f"{chg:+.2f} ({chg_pct:+.2f}%)" if c >= 1 else f"{chg:+.6f} ({chg_pct:+.2f}%)"
    draw.text((title_x + draw.textlength(ohlc, font=font_sm), 30 * scale), chg_s, font=font_sm, fill=chg_color)

    if WATERMARK:
        tw = draw.textlength(WATERMARK, font=font_wm)
        wx = int((W - tw) / 2)
        wy = int(pad_t + plot_h * 0.52)
        draw.text((wx + scale, wy + scale), WATERMARK, font=font_wm, fill=(24, 26, 32, 255))
        draw.text((wx, wy), WATERMARK, font=font_wm, fill=(70, 76, 90, 255))

    out = img.convert("RGB").resize((W // scale, H // scale), Image.Resampling.LANCZOS)
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
