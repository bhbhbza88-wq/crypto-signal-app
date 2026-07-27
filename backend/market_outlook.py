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
_SETTING_RECENT = "outlook_recent_syms"  # JSON { "BTC/USDT": unix_ts, ... }

OUTLOOK_SYSTEM = (
    "Ты аналитик NOWICKI. Пишешь короткий разбор монеты для Telegram-канала.\n"
    "Стиль: спокойный, конкретный, без хайпа и без обещаний прибыли.\n"
    "ЗАПРЕЩЕНО: «вероятность роста XX%», «гарантированно», «100x», эмодзи-спам, "
    "призывы срочно купить, реферальные коды.\n"
    "Можно: структура (тренд/флэт), ключевые уровни, сценарий вверх, "
    "что ломает идею (invalidation), score 1–10 как уверенность в сетапе "
    "(не вероятность прибыли).\n"
    "Язык: русский. HTML: только <b> и <i>, без других тегов.\n"
    "Верни JSON:\n"
    '{"headline": string, "body": string, "score_1_10": int, "bias": "long"|"neutral"|"short"}\n'
    "headline: коротко, с тикером ($SOL — …). body: 4–7 коротких абзацев/строк, "
    "до ~900 символов. Уровни бери ТОЛЬКО из входных данных, не выдумывай."
)


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


def _recent_map() -> dict[str, float]:
    try:
        data = json.loads(db.get_setting(_SETTING_RECENT, "{}") or "{}")
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return {}


def _remember_symbol(symbol: str) -> None:
    m = _recent_map()
    now = time.time()
    cutoff = now - SYMBOL_COOLDOWN_H * 3600 * 2
    m = {k: v for k, v in m.items() if v >= cutoff}
    m[symbol] = now
    db.set_setting(_SETTING_RECENT, json.dumps(m))


def _on_cooldown(symbol: str) -> bool:
    ts = _recent_map().get(symbol)
    if not ts:
        return False
    return (time.time() - ts) < SYMBOL_COOLDOWN_H * 3600


def _fmt_price(v: float) -> str:
    n = float(v)
    if n >= 1000:
        return f"{n:.2f}"
    if n >= 1:
        return f"{n:.4f}".rstrip("0").rstrip(".")
    if n >= 0.01:
        return f"{n:.5f}".rstrip("0").rstrip(".")
    return f"{n:.8f}".rstrip("0").rstrip(".")


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
    picked = []
    for r in rows:
        if r["score"] < MIN_INTERNAL_SCORE:
            continue
        if _on_cooldown(r["symbol"]):
            continue
        # в бычьем/боковике предпочитаем long-структуру; в дауне — можно downtренд
        phase = (r.get("btc_phase") or "").upper()
        if phase == "DOWNTREND":
            if r["regime"] not in ("DOWNTREND", "CHOP") and not r.get("breakout"):
                continue
        else:
            if r["regime"] == "DOWNTREND" and not r.get("breakout"):
                continue
        picked.append(r)
        if len(picked) >= limit:
            break
    return picked


def _facts_block(row: dict) -> str:
    return (
        f"symbol: {row['symbol']}\n"
        f"exchange: {row.get('exchange')} ({row.get('listings')})\n"
        f"price: {_fmt_price(row['close'])}\n"
        f"chg_24h_pct: {row['chg_24h']}\n"
        f"regime: {row['regime']} adx={row['adx']} rsi={row['rsi']}\n"
        f"vol_trend: {row['vol_trend']} atr_pct={row['atr_pct']}\n"
        f"breakout_flag: {row['breakout']}\n"
        f"ema21: {_fmt_price(row['ema21'])} ema50: {_fmt_price(row['ema50'])}\n"
        f"support: {_fmt_price(row['support'])}\n"
        f"resistance: {_fmt_price(row['resistance'])}\n"
        f"invalidation: {_fmt_price(row['invalidation'])}\n"
        f"internal_score_0_100: {row['score']}\n"
        f"btc_phase: {row.get('btc_phase')}\n"
        f"btc_meta: {json.dumps(row.get('btc_meta') or {}, ensure_ascii=False)}\n"
    )


async def _ai_write_post(row: dict) -> dict | None:
    user = (
        "Сделай разбор по фактам ниже. Уровни и цифры не меняй.\n\n"
        + _facts_block(row)
    )
    try:
        verdict = await ai_client.fast_json_completion(
            system=OUTLOOK_SYSTEM,
            user_text=user,
            max_tokens=520,
        )
    except Exception as e:
        print(f"[market_outlook] AI fail {row['symbol']}: {e}", flush=True)
        return None
    if not isinstance(verdict, dict):
        return None
    body = (verdict.get("body") or "").strip()
    headline = (verdict.get("headline") or "").strip()
    if not body:
        return None
    try:
        s10 = int(verdict.get("score_1_10") or round(row["score"] / 10))
    except (TypeError, ValueError):
        s10 = max(1, min(10, round(row["score"] / 10)))
    s10 = max(1, min(10, s10))
    bias = (verdict.get("bias") or "neutral").strip().lower()
    if bias not in ("long", "short", "neutral"):
        bias = "neutral"
    return {"headline": headline, "body": body, "score_1_10": s10, "bias": bias}


def _format_post(row: dict, ai: dict) -> str:
    coin = row["symbol"].replace("/USDT", "")
    headline = ai["headline"] or f"${coin} — outlook"
    if not headline.startswith("$"):
        headline = f"${coin} — {headline}"
    score = ai["score_1_10"]
    bias = ai["bias"]
    bias_ru = {"long": "бычий", "short": "медвежий", "neutral": "нейтральный"}.get(bias, bias)
    phase = row.get("btc_phase") or "—"
    footer = (
        f"\n\n<i>Score сетапа: {score}/10 · bias: {bias_ru}</i>"
        f"\n<i>BTC phase: {phase} · data: {row.get('exchange', 'bybit')} 1h</i>"
        f"\n<i>Не сигнал входа. Своё решение и риск — на тебе.</i>"
    )
    body = ai["body"].strip()
    text = f"<b>{headline}</b>\n\n{body}{footer}"
    return text[:3900]


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

    import telegram_bot

    published = 0
    for row in shortlist:
        ai = await _ai_write_post(row)
        if not ai:
            continue
        text = _format_post(row, ai)
        try:
            await telegram_bot.publish_news(text)
        except Exception as e:
            print(f"[market_outlook] publish fail {row['symbol']}: {e}", flush=True)
            continue
        _remember_symbol(row["symbol"])
        _bump_posts_today(1)
        published += 1
        print(
            f"[market_outlook] published {row['symbol']} "
            f"score={row['score']} ai={ai['score_1_10']}/10",
            flush=True,
        )
        await asyncio.sleep(1.2)
    return published


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
