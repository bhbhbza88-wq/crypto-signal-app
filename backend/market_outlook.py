"""
Market Outlook — свой контент для @nowicki_news.

Раз в N часов: Bybit OHLCV по CANDIDATES → индикаторы → скоринг →
shortlist 1–3 монеты → AI пишет разбор (структура / уровни / сценарий /
invalidation, score 1–10) → пост ботом в TELEGRAM_NEWS_TARGET_CHANNEL.

Не путать с news_relay (рерайт чужих каналов) и с ТВХ-сигналами.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd

import ai_client
import database as db
from data_layer import (
    CANDIDATES,
    build_features,
    detect_regime,
    fetch_ohlcv_raw,
    listings_label,
)

# ── Config ────────────────────────────────────────────────────────────
ENABLED = (os.getenv("MARKET_OUTLOOK_ENABLED", "1") or "1").strip().lower() in (
    "1", "true", "yes", "on",
)
INTERVAL_SEC = int(os.getenv("MARKET_OUTLOOK_INTERVAL_SEC", "10800") or "10800")  # 3h
MAX_PER_DAY = int(os.getenv("MARKET_OUTLOOK_MAX_PER_DAY", "4") or "4")
MAX_PER_RUN = int(os.getenv("MARKET_OUTLOOK_MAX_PER_RUN", "2") or "2")
MIN_INTERNAL_SCORE = float(os.getenv("MARKET_OUTLOOK_MIN_SCORE", "55") or "55")
SYMBOL_COOLDOWN_H = float(os.getenv("MARKET_OUTLOOK_SYMBOL_COOLDOWN_H", "18") or "18")
WORKERS = int(os.getenv("MARKET_OUTLOOK_WORKERS", "8") or "8")
EXCHANGE_ID = (os.getenv("MARKET_OUTLOOK_EXCHANGE", "bybit") or "bybit").strip().lower()

TARGET = (
    os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL")
    or os.getenv("MARKET_OUTLOOK_CHANNEL")
    or "nowicki_news"
).strip().lstrip("@")

_SETTING_DAY = "outlook_posts_day"       # "YYYY-MM-DD:count"
_SETTING_RECENT = "outlook_recent_posts"  # JSON { "BTC/USDT": {ts,bias,key_level,close,post_type}, ... }

UPDATE_MIN_AGE_H = float(os.getenv("MARKET_OUTLOOK_UPDATE_MIN_AGE_H", "6") or "6")
UPDATE_MAX_AGE_H = float(os.getenv("MARKET_OUTLOOK_UPDATE_MAX_AGE_H", "48") or "48")

OUTLOOK_SYSTEM_ANALYSIS = """
Ты пишешь короткий разбор для Telegram-канала NOWICKI в стиле «Торговый Букварь».

Язык: русский. Тон: живой трейдер, коротко и по делу.
Пиши: ликвидность, зона спроса/предложения, реакция, закрепление, цель.
Обязательно один раз естественно вставь KEY_LEVEL из фактов (тот же уровень, что на графике).
Часто уместно: «заходить без подтверждения рано», «жду закрепление ниже/выше».
Без канцелярита, без «покупай сейчас», без эмодзи.

Формат body: 2 коротких абзаца через \\n\\n.
Цены только из фактов, KEY_LEVEL пиши так же, как в фактах (human_key_level).

Верни JSON:
{
  "ticker": "SOL",
  "body": "...",
  "score_1_10": 7,
  "bias": "long"
}
body 260–480 символов.
""".strip()

OUTLOOK_SYSTEM_UPDATE = """
Ты пишешь короткий апдейт к уже вышедшему разбору (стиль «Торговый Букварь»).

Формат: 1 короткий абзац. Примеры тона:
- «По SOL сходили ровно по нашему сценарию: … Ключевой уровень — X.»
- «Дошли до зоны, получили реакцию. Дальше жду …»

Обязательно упомяни KEY_LEVEL (human_key_level из фактов).
Без эмодзи, без «покупай», без воды.

Верни JSON:
{
  "ticker": "SOL",
  "body": "один абзац 120–280 символов",
  "score_1_10": 7,
  "bias": "long"
}
""".strip()

# backward-compatible alias
OUTLOOK_SYSTEM = OUTLOOK_SYSTEM_ANALYSIS



def is_configured() -> bool:
    if not ENABLED:
        return False
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    return bool(token and TARGET and ai_client.fast_configured())


def _day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _posts_today() -> int:
    raw = db.get_setting(_SETTING_DAY, "") or ""
    if ":" not in raw:
        return 0
    day, _, cnt = raw.partition(":")
    if day != _day_key():
        return 0
    try:
        return int(cnt)
    except ValueError:
        return 0


def _bump_posts_today(n: int = 1) -> None:
    cur = _posts_today()
    db.set_setting(_SETTING_DAY, f"{_day_key()}:{cur + n}")


def _fmt_price(v: float) -> str:
    n = float(v)
    if n >= 1000:
        s = f"{n:,.2f}".replace(",", " ")
        if s.endswith(".00"):
            s = s[:-3]
        return s
    if n >= 1:
        return f"{n:.4f}".rstrip("0").rstrip(".")
    if n >= 0.01:
        return f"{n:.5f}".rstrip("0").rstrip(".")
    return f"{n:.8f}".rstrip("0").rstrip(".")


def _recent_posts() -> dict[str, dict]:
    """{ symbol: {ts, bias, key_level, close, post_type} } — tolerates legacy float map."""
    try:
        data = json.loads(db.get_setting(_SETTING_RECENT, "{}") or "{}")
        if not isinstance(data, dict):
            return {}
        out: dict[str, dict] = {}
        for k, v in data.items():
            if isinstance(v, (int, float)):
                out[str(k)] = {
                    "ts": float(v),
                    "bias": "long",
                    "key_level": None,
                    "close": None,
                    "post_type": "analysis",
                }
            elif isinstance(v, dict) and "ts" in v:
                out[str(k)] = {
                    "ts": float(v["ts"]),
                    "bias": (v.get("bias") or "long"),
                    "key_level": v.get("key_level"),
                    "close": v.get("close"),
                    "post_type": v.get("post_type") or "analysis",
                }
        return out
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _remember_post(
    symbol: str,
    *,
    bias: str,
    key_level: float | None,
    close: float,
    post_type: str,
) -> None:
    m = _recent_posts()
    now = time.time()
    cutoff = now - max(SYMBOL_COOLDOWN_H, UPDATE_MAX_AGE_H) * 3600 * 2
    m = {k: v for k, v in m.items() if float(v.get("ts") or 0) >= cutoff}
    m[symbol] = {
        "ts": now,
        "bias": bias,
        "key_level": key_level,
        "close": close,
        "post_type": post_type,
    }
    db.set_setting(_SETTING_RECENT, json.dumps(m))


def _on_cooldown(symbol: str) -> bool:
    prev = _recent_posts().get(symbol)
    if not prev:
        return False
    return (time.time() - float(prev["ts"])) < SYMBOL_COOLDOWN_H * 3600


def _infer_bias(row: dict) -> str:
    regime = (row.get("regime") or "").upper()
    phase = (row.get("btc_phase") or "").upper()
    if regime == "DOWNTREND" or (phase == "DOWNTREND" and regime != "UPTREND"):
        return "short"
    return "long"


def _pick_key_level(row: dict, bias: str) -> float:
    close = float(row["close"])
    if bias == "short":
        for k in ("resistance", "target_1"):
            try:
                v = float(row.get(k))
                if v > close:
                    return v
            except (TypeError, ValueError):
                pass
        return close * 1.012
    for k in ("support", "invalidation"):
        try:
            v = float(row.get(k))
            if v < close:
                return v
        except (TypeError, ValueError):
            pass
    return close * 0.988


def _update_context(row: dict) -> dict | None:
    """Prior post exists and price moved enough -> short update."""
    prev = _recent_posts().get(row["symbol"])
    if not prev:
        return None
    age_h = (time.time() - float(prev["ts"])) / 3600.0
    if age_h < UPDATE_MIN_AGE_H or age_h > UPDATE_MAX_AGE_H:
        return None
    if (prev.get("post_type") or "") == "update" and age_h < UPDATE_MIN_AGE_H * 2:
        return None
    old_c = prev.get("close")
    try:
        old_c = float(old_c) if old_c is not None else None
    except (TypeError, ValueError):
        old_c = None
    now_c = float(row["close"])
    if old_c and old_c > 0:
        moved = (now_c - old_c) / old_c
        if abs(moved) < 0.003:
            return None
    return prev


def _scan_symbol(symbol: str) -> dict | None:
    """Синхронный скан одной монеты на Bybit."""
    ex_id = EXCHANGE_ID or "bybit"
    raw = fetch_ohlcv_raw(symbol, "1h", limit=120, exchange_id=ex_id)
    if not raw or len(raw) < 60:
        return None

    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = build_features(pd.DataFrame(raw, columns=cols))
    if len(df) < 50 or pd.isna(df.iloc[-1].get("atr")):
        return None

    last = df.iloc[-1]
    prev24 = df.iloc[-25] if len(df) >= 25 else df.iloc[0]
    close = float(last["close"])
    if close <= 0:
        return None

    chg_24h = (close / float(prev24["close"]) - 1.0) * 100.0
    vol_trend = float(last["vol_trend"]) if not pd.isna(last["vol_trend"]) else 1.0
    rsi = float(last["rsi"]) if not pd.isna(last["rsi"]) else 50.0
    atr = float(last["atr"])
    atr_pct = atr / close * 100.0
    regime, adx = detect_regime(df)
    adx = float(adx)

    # breakout: close near 24h high + volume expansion
    window = df.iloc[-24:]
    hi_24 = float(window["high"].max())
    lo_24 = float(window["low"].min())
    near_high = (hi_24 - close) / close < 0.008 if hi_24 > 0 else False
    breakout = bool(near_high and vol_trend >= 1.35 and chg_24h > 1.5)

    # levels
    ema21 = float(last["ema21"]) if not pd.isna(last["ema21"]) else close
    ema50 = float(last["ema50"]) if not pd.isna(last["ema50"]) else close
    support = min(lo_24, ema21)
    resistance = hi_24
    invalidation = min(ema50, support) * 0.995
    # Fed-style levels to watch
    atr = float(last["atr"])
    target_1 = max(resistance, close + atr)
    target_2 = target_1 + atr * 1.2
    fail_zone = invalidation - atr * 0.5

    # ── internal score 0–100 ──
    score = 40.0
    if regime == "UPTREND":
        score += 18
    elif regime == "DOWNTREND":
        score -= 12
    elif regime == "CHOP":
        score += 2

    if breakout:
        score += 14
    if vol_trend >= 1.5:
        score += 10
    elif vol_trend >= 1.2:
        score += 5

    # sweet-spot momentum (не уже перегретый памп)
    if 2.0 <= chg_24h <= 12.0:
        score += 12
    elif 0.5 <= chg_24h < 2.0:
        score += 6
    elif chg_24h > 18:
        score -= 10  # слишком растянуто
    elif chg_24h < -5:
        score -= 8

    if 45 <= rsi <= 68:
        score += 8
    elif rsi > 78:
        score -= 10
    elif rsi < 35:
        score += 3  # возможен отскок, но осторожно

    if adx >= 22:
        score += 6
    elif adx < 14:
        score -= 4

    if 0.6 <= atr_pct <= 4.0:
        score += 4

    score = max(0.0, min(100.0, score))

    listed = [ex_id]
    return {
        "symbol": symbol,
        "exchange": ex_id,
        "listed_on": listed,
        "listings": listings_label(listed),
        "close": close,
        "chg_24h": round(chg_24h, 2),
        "vol_trend": round(vol_trend, 2),
        "rsi": round(rsi, 1),
        "atr_pct": round(atr_pct, 2),
        "adx": round(adx, 1),
        "regime": regime,
        "breakout": breakout,
        "ema21": ema21,
        "ema50": ema50,
        "support": support,
        "resistance": resistance,
        "invalidation": invalidation,
        "target_1": target_1,
        "target_2": target_2,
        "fail_zone": fail_zone,
        "score": round(score, 1),
    }


def _apply_btc_phase(rows: list[dict], phase: dict | None) -> list[dict]:
    if not phase:
        return rows
    p = (phase.get("phase") or "").upper()
    out = []
    for r in rows:
        s = float(r["score"])
        if p == "UPTREND" and r["regime"] == "UPTREND":
            s += 8
        elif p == "DOWNTREND" and r["regime"] == "UPTREND":
            s -= 10  # long-bias в медвежьем BTC — штраф
        elif p == "DOWNTREND" and r["regime"] == "DOWNTREND":
            s += 4  # можно short-bias разбор
        elif p == "SIDEWAYS":
            s += 0
        r = dict(r)
        r["score"] = round(max(0.0, min(100.0, s)), 1)
        r["btc_phase"] = p
        r["btc_meta"] = {
            "momentum_60d_pct": phase.get("momentum_60d_pct"),
            "breadth_pct": phase.get("breadth_pct"),
            "btc_close": phase.get("btc_close"),
        }
        out.append(r)
    return out


def scan_candidates() -> list[dict]:
    """Скан CANDIDATES → отсортированный список по score."""
    rows: list[dict] = []
    symbols = list(CANDIDATES)
    workers = max(2, min(WORKERS, 12))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_scan_symbol, sym): sym for sym in symbols}
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except Exception as e:
                print(f"[market_outlook] scan {futs[fut]}: {e}", flush=True)
                row = None
            if row:
                rows.append(row)

    phase = None
    try:
        import trend_strategy
        phase = trend_strategy.get_market_phase()
    except Exception as e:
        print(f"[market_outlook] market phase: {e}", flush=True)

    rows = _apply_btc_phase(rows, phase)
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def _pick_shortlist(rows: list[dict], limit: int) -> list[dict]:
    """Prefer scenario updates first, then fresh analysis (respecting cooldown)."""
    updates: list[dict] = []
    fresh: list[dict] = []
    for r in rows:
        if r["score"] < MIN_INTERNAL_SCORE:
            continue
        phase = (r.get("btc_phase") or "").upper()
        if phase == "DOWNTREND":
            if r["regime"] not in ("DOWNTREND", "CHOP") and not r.get("breakout"):
                continue
        else:
            if r["regime"] == "DOWNTREND" and not r.get("breakout"):
                continue
        prev = _update_context(r)
        if prev:
            rr = dict(r)
            rr["_force_post_type"] = "update"
            updates.append(rr)
            continue
        if _on_cooldown(r["symbol"]):
            continue
        fresh.append(r)

    picked = (updates + fresh)[:limit]
    return picked


def _facts_block(row: dict, *, key_level: float, bias: str, post_type: str, prev: dict | None = None) -> str:
    base = (
        f"symbol: {row['symbol']}\n"
        f"ticker: ${row['symbol'].replace('/USDT', '')}\n"
        f"post_type: {post_type}\n"
        f"bias_hint: {bias}\n"
        f"KEY_LEVEL: {key_level}\n"
        f"human_key_level: {_fmt_price(key_level)}\n"
        f"exchange: {row.get('exchange')} ({row.get('listings')})\n"
        f"price: {_fmt_price(row['close'])}\n"
        f"chg_24h_pct: {row['chg_24h']}\n"
        f"regime: {row['regime']} adx={row['adx']} rsi={row['rsi']}\n"
        f"vol_trend: {row['vol_trend']} atr_pct={row['atr_pct']}\n"
        f"breakout_flag: {row['breakout']}\n"
        f"ema21: {_fmt_price(row['ema21'])} ema50: {_fmt_price(row['ema50'])}\n"
        f"support: {_fmt_price(row['support'])}\n"
        f"resistance: {_fmt_price(row['resistance'])}\n"
        f"target_1: {_fmt_price(row.get('target_1') or row['resistance'])}\n"
        f"target_2: {_fmt_price(row.get('target_2') or row['resistance'])}\n"
        f"invalidation: {_fmt_price(row['invalidation'])}\n"
        f"fail_zone: {_fmt_price(row.get('fail_zone') or row['invalidation'])}\n"
        f"internal_score_0_100: {row['score']}\n"
        f"btc_phase: {row.get('btc_phase')}\n"
    )
    if prev:
        base += (
            f"prev_bias: {prev.get('bias')}\n"
            f"prev_key_level: {prev.get('key_level')}\n"
            f"prev_close: {prev.get('close')}\n"
            f"prev_post_type: {prev.get('post_type')}\n"
        )
    return base


async def _ai_write_post(
    row: dict,
    *,
    post_type: str = "analysis",
    bias: str | None = None,
    key_level: float | None = None,
    prev: dict | None = None,
) -> dict | None:
    bias_n = (bias or _infer_bias(row)).strip().lower()
    if bias_n not in ("long", "short"):
        bias_n = "long"
    kl = float(key_level) if key_level is not None else _pick_key_level(row, bias_n)
    system = OUTLOOK_SYSTEM_UPDATE if post_type == "update" else OUTLOOK_SYSTEM_ANALYSIS
    if post_type == "update":
        user = (
            "Короткий апдейт по уже вышедшему сценарию. "
            "Обязательно упомяни human_key_level. Цены не выдумывай.\n\n"
            + _facts_block(row, key_level=kl, bias=bias_n, post_type=post_type, prev=prev)
        )
        max_tokens = 280
        temperature = 0.7
    else:
        user = (
            "Короткий пост в стиле Торгового Букваря по фактам. "
            "Обязательно один раз вставь human_key_level как ключевой уровень. "
            "Цены не выдумывай. Без отчёта бота.\n\n"
            + _facts_block(row, key_level=kl, bias=bias_n, post_type=post_type, prev=prev)
        )
        max_tokens = 420
        temperature = 0.78
    try:
        verdict = await ai_client.fast_json_completion(
            system=system,
            user_text=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        print(f"[market_outlook] AI fail {row['symbol']}: {e}", flush=True)
        return None
    if not isinstance(verdict, dict):
        return None
    body = (verdict.get("body") or verdict.get("narrative") or "").strip()
    if not body:
        return None
    # Ensure key level appears in analysis/update text.
    human_kl = _fmt_price(kl)
    if human_kl not in body and human_kl.replace(" ", "") not in body.replace(" ", ""):
        if post_type == "update":
            body = f"{body.rstrip()} Ключевой уровень — {human_kl}."
        else:
            body = f"{body.rstrip()}\n\nКлючевой уровень — {human_kl}."
    coin = row["symbol"].replace("/USDT", "")
    ticker = (verdict.get("ticker") or coin).strip().lstrip("#$").upper() or coin
    try:
        s10 = int(verdict.get("score_1_10") or round(row["score"] / 10))
    except (TypeError, ValueError):
        s10 = max(1, min(10, round(row["score"] / 10)))
    bias_out = (verdict.get("bias") or bias_n).strip().lower()
    if bias_out not in ("long", "short", "neutral"):
        bias_out = bias_n
    if bias_out == "neutral":
        bias_out = bias_n
    return {
        "ticker": ticker,
        "body": body,
        "score_1_10": max(1, min(10, s10)),
        "bias": bias_out,
        "key_level": kl,
        "post_type": post_type,
    }


def _format_post(row: dict, ai: dict, chart_tag: str = "") -> str:
    """Bukvar: #TICKER + body (full or short update)."""
    del chart_tag
    coin = row["symbol"].replace("/USDT", "")
    ticker = (ai.get("ticker") or coin).strip().lstrip("#$").upper() or coin
    body = (ai.get("body") or "").strip()
    for bad in ("На основании анализа", "Следует отметить", "В заключение", "Данный актив"):
        body = body.replace(bad, "")
    if ai.get("post_type") == "update" and not body:
        return f"#{ticker}"
    text = f"#{ticker}\n\n{body}" if body else f"#{ticker}"
    return text[:1020]


async def _publish_row(
    row: dict,
    *,
    count_toward_cap: bool = True,
    force_post_type: str | None = None,
) -> bool:
    import telegram_bot
    import tv_chart

    prev = _update_context(row)
    post_type = force_post_type or ("update" if prev else "analysis")
    bias_hint = (prev.get("bias") if prev else None) or _infer_bias(row)
    key_level = None
    if prev and prev.get("key_level") is not None:
        try:
            key_level = float(prev["key_level"])
        except (TypeError, ValueError):
            key_level = None
    if key_level is None:
        key_level = _pick_key_level(row, bias_hint)

    ai = await _ai_write_post(
        row,
        post_type=post_type,
        bias=bias_hint,
        key_level=key_level,
        prev=prev,
    )
    if not ai:
        return False
    bias = ai.get("bias") or bias_hint
    key_level = float(ai.get("key_level") or key_level)
    levels = {
        "support": row.get("support"),
        "resistance": row.get("resistance"),
        "invalidation": row.get("invalidation"),
        "ema21": row.get("ema21"),
        "ema50": row.get("ema50"),
        "target_1": row.get("target_1"),
        "target_2": row.get("target_2"),
        "fail_zone": row.get("fail_zone"),
        "key_level": key_level,
    }
    png, chart_tag = await asyncio.to_thread(
        tv_chart.chart_for_symbol,
        row["symbol"],
        exchange_id=row.get("exchange") or "bybit",
        levels=levels,
        bias=bias,
    )
    text = _format_post(row, ai, chart_tag=chart_tag)
    try:
        await telegram_bot.publish_news(text, photo_png=png)
    except Exception as e:
        print(f"[market_outlook] publish fail {row['symbol']}: {e}", flush=True)
        return False
    _remember_post(
        row["symbol"],
        bias=bias,
        key_level=key_level,
        close=float(row["close"]),
        post_type=post_type,
    )
    if count_toward_cap:
        _bump_posts_today(1)
    print(
        f"[market_outlook] published {row['symbol']} type={post_type} "
        f"key={_fmt_price(key_level)} score={row['score']} "
        f"ai={ai['score_1_10']}/10 chart={chart_tag or 'none'}",
        flush=True,
    )
    return True


async def run_once() -> int:
    """Один проход: scan → shortlist → AI → publish. Возвращает число постов."""
    left_day = MAX_PER_DAY - _posts_today()
    if left_day <= 0:
        print(f"[market_outlook] day cap ({MAX_PER_DAY}) reached", flush=True)
        return 0

    limit = min(MAX_PER_RUN, left_day)
    print(f"[market_outlook] scan… candidates={len(CANDIDATES)} limit={limit}", flush=True)
    rows = await asyncio.to_thread(scan_candidates)
    if not rows:
        print("[market_outlook] empty scan", flush=True)
        return 0

    top = rows[:5]
    print(
        "[market_outlook] top: "
        + ", ".join(f"{r['symbol']}={r['score']}" for r in top),
        flush=True,
    )
    shortlist = _pick_shortlist(rows, limit)
    if not shortlist:
        print("[market_outlook] nothing passed filters", flush=True)
        return 0

    published = 0
    for row in shortlist:
        force = row.pop("_force_post_type", None)
        if await _publish_row(row, force_post_type=force):
            published += 1
            await asyncio.sleep(1.2)
    return published


async def publish_test(symbol: str | None = None, post_type: str | None = None) -> bool:
    """Тестовый пост в канал (без day-cap / cooldown). Для итераций по стилю."""
    rows = await asyncio.to_thread(scan_candidates)
    if not rows:
        print("[market_outlook] test: empty scan", flush=True)
        return False
    row = None
    if symbol:
        raw = symbol.upper().replace("-", "/").strip()
        if raw.endswith("USDT") and "/" not in raw:
            want = raw[:-4] + "/USDT"
        elif "/USDT" in raw:
            want = raw.split("/USDT")[0] + "/USDT"
        else:
            want = f"{raw}/USDT"
        for r in rows:
            if r["symbol"] == want:
                row = r
                break
        if row is None:
            one = await asyncio.to_thread(_scan_symbol, want)
            if one:
                try:
                    import trend_strategy
                    phase = await asyncio.to_thread(trend_strategy.get_market_phase)
                except Exception:
                    phase = None
                row = _apply_btc_phase([one], phase)[0]
    if row is None:
        picked = _pick_shortlist(rows, 1) or rows[:1]
        row = picked[0]
    close = float(row["close"])
    res = float(row["resistance"])
    row.setdefault("target_1", res if res > close else close * 1.03)
    row.setdefault("target_2", float(row["target_1"]) * 1.06)
    row.setdefault("fail_zone", float(row["invalidation"]) * 0.97)
    force = (post_type or "").strip().lower() or None
    if force not in ("analysis", "update", None):
        force = "analysis"
    print(
        f"[market_outlook] TEST post → {row['symbol']} score={row['score']} type={force or 'auto'}",
        flush=True,
    )
    return await _publish_row(row, count_toward_cap=False, force_post_type=force)


async def run() -> None:
    if not is_configured():
        print(
            "[market_outlook] не сконфигурирован "
            "(MARKET_OUTLOOK_ENABLED / BOT_TOKEN / AI / channel) — пропуск",
            flush=True,
        )
        return

    print(
        f"[market_outlook] start → @{TARGET} every {INTERVAL_SEC}s "
        f"max/day={MAX_PER_DAY} max/run={MAX_PER_RUN} min_score={MIN_INTERNAL_SCORE}",
        flush=True,
    )
    # небольшой стартовый джиттер, чтобы не биться с ingest при рестарте
    await asyncio.sleep(45)
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[market_outlook] Упал: {e}", flush=True)
        await asyncio.sleep(max(600, INTERVAL_SEC))
