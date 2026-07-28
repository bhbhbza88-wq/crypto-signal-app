"""
Market Outlook — свой контент для @nowicki_news.

Раз в N часов: Bybit OHLCV по CANDIDATES → индикаторы → скоринг →
shortlist 1–3 монеты → AI пишет разбор (структура / уровни / сценарий /
invalidation, score 1–10) → пост ботом в TELEGRAM_NEWS_TARGET_CHANNEL.

Не путать с news_relay (рерайт чужих каналов) и с ТВХ-сигналами.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

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
INTERVAL_SEC = int(os.getenv("MARKET_OUTLOOK_INTERVAL_SEC", "300") or "300")  # 5m continuous scan
# Цель 5–6 постов/день; MAX чуть выше цели, чтобы догнать при отставании.
TARGET_PER_DAY = int(os.getenv("MARKET_OUTLOOK_TARGET_PER_DAY", "6") or "6")
MAX_PER_DAY = int(os.getenv("MARKET_OUTLOOK_MAX_PER_DAY", "6") or "6")
MAX_PER_RUN = int(os.getenv("MARKET_OUTLOOK_MAX_PER_RUN", "1") or "1")
# Базовый порог качества; при отставании от квоты смягчается до SOFT_MIN.
MIN_INTERNAL_SCORE = float(os.getenv("MARKET_OUTLOOK_MIN_SCORE", "65") or "65")
SOFT_MIN_SCORE = float(os.getenv("MARKET_OUTLOOK_SOFT_MIN_SCORE", "48") or "48")
# Базовый gap; фактический считается адаптивно под оставшуюся квоту/окно.
MIN_GAP_H = float(os.getenv("MARKET_OUTLOOK_MIN_GAP_H", "2.0") or "2.0")
SYMBOL_COOLDOWN_H = float(os.getenv("MARKET_OUTLOOK_SYMBOL_COOLDOWN_H", "18") or "18")
WORKERS = int(os.getenv("MARKET_OUTLOOK_WORKERS", "8") or "8")
EXCHANGE_ID = (os.getenv("MARKET_OUTLOOK_EXCHANGE", "bybit") or "bybit").strip().lower()
# Основной ТФ графика/разбора — как в заголовке чарта (4h).
CHART_TF = (os.getenv("OUTLOOK_CHART_TF", "4h") or "4h").strip().lower()

# Human-like posting window (local wall clock). Default: Europe/Kyiv 09:00–23:30.
ACTIVE_TZ = (os.getenv("MARKET_OUTLOOK_TZ") or "Europe/Kyiv").strip() or "Europe/Kyiv"


def _parse_hhmm(raw: str, default_h: int, default_m: int = 0) -> int:
    """Return minutes since midnight."""
    try:
        parts = (raw or "").strip().split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return max(0, min(24 * 60, h * 60 + m))
    except (TypeError, ValueError, IndexError):
        return default_h * 60 + default_m


ACTIVE_FROM_MIN = _parse_hhmm(os.getenv("MARKET_OUTLOOK_ACTIVE_FROM", "09:00"), 9, 0)
ACTIVE_UNTIL_MIN = _parse_hhmm(os.getenv("MARKET_OUTLOOK_ACTIVE_UNTIL", "23:30"), 23, 30)

_last_gap_skip_log_ts = 0.0
_last_quiet_log_ts = 0.0

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
Ты пишешь короткий разбор для Telegram-канала трейдера. Стиль «Торговый Букваръ».

ЖЁСТКИЕ ПРАВИЛА:
1. Первое предложение ВСЕГДА «По $TICKER…» (без #). Голос трейдера первого лица.
2. Price action язык — НЕ индикаторы:
   - НИКОГДА не пиши ema21/ema50/индикаторы/RSI/ADX в тексте.
   - ИСПОЛЬЗУЙ: ликвидность (сняли/собрали), зона спроса, зона предложения, заброс,
     смягчили диапазон, закрепление, подтверждение, цепочка предложения, реакция от зоны,
     точка №1/№2, проторговка.
   - Можно «поддержка/сопротивление», но лучше «зона спроса/предложения».
3. Голос: «смотрю», «жду», «работаю от шорта», «интересно после», «пока не рассматриваю»,
   «сначала нужно». НЕ пиши «цена торгуется», «это говорит о», «данный актив».
4. Сценарий с условием (не сразу цель):
   - Структура: что произошло → условие → потом вход/цель.
   - «Сначала нужно закрепиться выше X, после этого можно смотреть лонг с целью Y.»
   - «Пока рано», «без подтверждения не беру», «жду реакции от зоны».
5. Минимум цифр — НЕ каша:
   - ОДНА главная цена (куда жду) + ОДНО условие (если есть).
   - НЕ пиши список: «поддержка X, сопротивление Y, ключевой Z, цель W».
   - Ключевой уровень = условие входа (закрепление/подтверждение), не отдельная строка.
6. Длина: 170–300 символов (медиана Букваря 248). Короче чем раньше.
7. Таймфреймы: «на дневке», «на 4ч», «на младшем», «на часовике». НЕ «дневной график».
8. НЕ жаргон: «давление продавцов», «зона консолидации», «импульс», «тренд бычий».
   Пиши: «рынок падает», «цена стоит», «движение вверх», «получили реакцию».

Структура body (1–2 абзаца):
1) По $TICKER + где сейчас/что произошло за последние часы.
2) Что жду: условие (если нужно) → цель. «смотрю / жду / интересно».

Примеры (НЕ копируй дословно):
• «По BTC пришли в зону предложения. Локально жду заброс ниже 64 800, оттуда смотрю
  шорт с целью 63 400. Ключевое условие — закрепление ниже 64 800.»
• «По SOL сняли ликвидность сверху и получили реакцию. Интересно смотреть продолжение
  падения к 74.5. Если закрепимся ниже, дальше 72.»
• «По ETH движение боковое, ликвидность внизу не трогали. Сначала жду выход к 1820,
  после реакции от зоны спроса можно рассматривать лонг.»

Верни JSON:
{
  "ticker": "BTC",
  "body": "170–300 символов",
  "score_1_10": 7,
  "bias": "long",
  "post_subtype": "analysis"
}
post_subtype: "analysis" (полный разбор) или "chart_only" (если сценарий слабый/неясный —
текст не обязателен, график сам скажет).
""".strip()

OUTLOOK_SYSTEM_UPDATE = """
Короткий апдейт к прошлому разбору (стиль Букваръ).

Начни «По $TICKER…». Голос: «сценарий отрабатывает», «сходили и получили реакцию»,
«теперь жду», «смотрю дальше».

Что случилось с прошлого поста → что дальше (1 цель или условие).
НЕ список уровней. Price action язык (ликвидность, зона, закрепление), не ema.
1 абзац, 100–210 символов.

Пример (не копируй):
«По SOL сценарий отработал: сняли ликвидность в точке №1, получили реакцию от зоны
спроса. Смотрю продолжение вверх к 78. Ключевое условие — закрепление выше 75.»

Верни JSON:
{
  "ticker": "SOL",
  "body": "100–210 символов",
  "score_1_10": 7,
  "bias": "long",
  "post_subtype": "update"
}
""".strip()

# backward-compatible alias
OUTLOOK_SYSTEM = OUTLOOK_SYSTEM_ANALYSIS

# Bukvar-style variation hints: trader voice + sequential narrative + SMC terms.
_VARIATION_HINTS_ANALYSIS = [
    "Начни «По $TICKER» + где сейчас. Потом «жду» + условие → цель. Price action язык.",
    "«По $TICKER» + что произошло. «Сначала нужно» + условие, «после этого смотрю» + цель.",
    "Начни «По $TICKER» + ликвидность/зона. «Интересно смотреть» + сценарий + условие.",
    "«По $TICKER» + реакция/движение. «Пока рано» или «жду» + условие → цель. Один уровень.",
    "Начни «По $TICKER сняли/смягчили/пришли». Потом «смотрю/работаю» + сценарий.",
]
_VARIATION_HINTS_UPDATE = [
    "«По $TICKER сценарий отработал/отрабатывает» + факт. «Теперь жду/смотрю» + цель.",
    "«По $TICKER» + что случилось с прошлого разбора. «Дальше смотрю» + куда.",
    "Начни «По $TICKER сходили/дошли/получили реакцию». Условие → цель.",
]

_PRICE_NUM_RE = re.compile(r"\d[\d\s]*\.\d+")


def _price_numbers_in_text(text: str) -> list[float]:
    out: list[float] = []
    for m in _PRICE_NUM_RE.findall(text):
        try:
            out.append(float(m.replace(" ", "")))
        except ValueError:
            pass
    return out


def _facts_price_pool(row: dict, key_level: float) -> list[float]:
    """All prices the AI is allowed to cite — used to catch hallucinated numbers."""
    keys = (
        "close", "support", "resistance", "invalidation",
        "target_1", "target_2", "fail_zone", "ema21", "ema50",
    )
    pool: list[float] = []
    try:
        pool.append(float(key_level))
    except (TypeError, ValueError):
        pass
    for k in keys:
        v = row.get(k)
        try:
            if v is not None:
                pool.append(float(v))
        except (TypeError, ValueError):
            pass
    return pool


def _body_prices_sane(body: str, pool: list[float], *, tol: float = 0.015) -> bool:
    """Reject text that cites a price-looking number not backed by any fact."""
    nums = _price_numbers_in_text(body)
    if not nums:
        return True
    for n in nums:
        if n <= 0:
            continue
        if not any(p > 0 and abs(n - p) / p <= tol for p in pool):
            return False
    return True


_LEVEL_WORD_RE = re.compile(r"(поддержк\w*|сопротивлен\w*)", re.IGNORECASE)


def _levels_have_numbers(body: str, *, window: int = 22) -> bool:
    """Catches vague mentions like "к уровню поддержки" with no actual price."""
    for m in _LEVEL_WORD_RE.finditer(body):
        tail = body[m.end():m.end() + window]
        head = body[max(0, m.start() - window):m.start()]
        if not re.search(r"\d", tail) and not re.search(r"\d", head):
            return False
    return True


def _too_similar(new_body: str, prev_body: str | None, *, ratio_hi: float = 0.82) -> bool:
    """Catches near-duplicate consecutive posts (same wording, barely reworded)."""
    if not prev_body:
        return False
    a = " ".join(new_body.lower().split())
    b = " ".join(prev_body.lower().split())
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= ratio_hi


def _normalize_outlook_body(body: str) -> str:
    """
    Push wording toward Bukvar SMC style:
    - Remove EMA mentions, formal timeframe talk.
    - Map support/resistance → supply/demand zones when appropriate.
    - Add SMC vocabulary flavor.
    """
    text = body
    # Remove EMA mentions entirely from body (they're indicator talk, not price action).
    text = re.sub(r"\bторгуется\s+(ниже|выше|около|между)\s+ema\d+", r"цена \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(ниже|выше|около)\s+ema\d+\s+(и\s+ema\d+)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bema\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"EMA\s*\d+", "", text, flags=re.IGNORECASE)
    
    # Timeframe normalization
    replacements = (
        (r"дневным графиком", "дневкой"),
        (r"дневной график", "дневка"),
        (r"на дневном графике", "на дневке"),
        (r"на дневном таймфрейме", "на дневке"),
        (r"дневного таймфрейма", "дневки"),
        (r"дневном таймфрейме", "дневке"),
        (r"четырёхчасовом таймфрейме", "4ч"),
        (r"четырехчасовом таймфрейме", "4ч"),
        (r"на четырёхчасовом графике", "на 4ч"),
        (r"на четырехчасовом графике", "на 4ч"),
        (r"на часовом таймфрейме", "на часовике"),
        (r"на часовом графике", "на часовике"),
        # Formal → conversational
        (r"совпадает с\s+дневк\w*", "держится на дневке", ),
        (r"также\s+совпадает", "и на дневке"),
        # Passive → active trader voice
        (r"\bЦена торгуется", "Торгуемся"),
        (r"цена торгуется", "цена"),
        (r"Это говорит о", ""),
        (r"данный актив", "актив"),
        (r"зона консолидации", "боковое движение"),
        (r"давление продавцов", "продавцы давят"),
        (r"импульс\s+(вверх|вниз)", r"движение \1"),
        # SMC vocabulary nudges: поддержка → зона спроса (when clear)
        (r"к поддержке\b", "к зоне спроса"),
        (r"от поддержки\b", "от зоны спроса"),
        (r"к сопротивлению\b", "к зоне предложения"),
        (r"от сопротивления\b", "от зоны предложения"),
    )
    for pat, repl in replacements:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    
    # Clean up extra spaces from EMA removal
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\.\s+\.", ".", text)
    return text.strip()


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


def reset_posts_today() -> str:
    """Force today's counter to 0. Returns the new setting value."""
    val = f"{_day_key()}:0"
    db.set_setting(_SETTING_DAY, val)
    return val


def _maybe_reset_day_cap_from_env() -> None:
    """
    One-shot reset when MARKET_OUTLOOK_RESET_DAY is set to a non-empty
    truthy token (e.g. "1", "2", "now"). Changing the token re-triggers
    a reset even on the same UTC day.
    Also clears recent-post timestamps so the global gap opens immediately.
    """
    flag = (os.getenv("MARKET_OUTLOOK_RESET_DAY") or "").strip()
    if not flag or flag.lower() in ("0", "false", "no", "off"):
        return
    day = _day_key()
    consumed_key = "outlook_day_reset_consumed"
    token = f"{day}:{flag}"
    if (db.get_setting(consumed_key, "") or "") == token:
        return
    before = db.get_setting(_SETTING_DAY, "") or ""
    reset_posts_today()
    # Open the global posting gap right away (manual "let posts through again").
    db.set_setting(_SETTING_RECENT, "{}")
    db.set_setting(consumed_key, token)
    print(
        f"[market_outlook] day cap + gap reset via MARKET_OUTLOOK_RESET_DAY={flag!r} "
        f"(before={before!r} after={day}:0)",
        flush=True,
    )


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
    """{ symbol: {ts, bias, key_level, close, post_type, body} } — tolerates legacy float map."""
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
                    "body": None,
                }
            elif isinstance(v, dict) and "ts" in v:
                out[str(k)] = {
                    "ts": float(v["ts"]),
                    "bias": (v.get("bias") or "long"),
                    "key_level": v.get("key_level"),
                    "close": v.get("close"),
                    "post_type": v.get("post_type") or "analysis",
                    "body": v.get("body"),
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
    body: str | None = None,
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
        "body": (body or "")[:600],
    }
    db.set_setting(_SETTING_RECENT, json.dumps(m))


def _on_cooldown(symbol: str) -> bool:
    prev = _recent_posts().get(symbol)
    if not prev:
        return False
    return (time.time() - float(prev["ts"])) < SYMBOL_COOLDOWN_H * 3600


def _hours_since_any_post() -> float | None:
    """Age of the most recent outlook post across all symbols (hours)."""
    recent = _recent_posts()
    if not recent:
        return None
    latest = max(float(v.get("ts") or 0) for v in recent.values())
    if latest <= 0:
        return None
    return (time.time() - latest) / 3600.0


def _global_gap_ok() -> bool:
    """Enough time since the last post of any coin (spaces toward daily target)."""
    age = _hours_since_any_post()
    if age is None:
        return True
    return age >= _required_gap_h()


def _tzinfo():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(ACTIVE_TZ)
    except Exception:
        # Fallback UTC+2 if tzdata / zone name unavailable.
        return timezone(timedelta(hours=2))


def _local_now() -> datetime:
    return datetime.now(_tzinfo())


def _local_minutes(now: datetime | None = None) -> int:
    n = now or _local_now()
    return n.hour * 60 + n.minute


def _in_active_window(now: datetime | None = None) -> bool:
    """True only during the human posting window (e.g. 09:00–23:30 local)."""
    mins = _local_minutes(now)
    start, end = ACTIVE_FROM_MIN, ACTIVE_UNTIL_MIN
    if start == end:
        return True
    if start < end:
        return start <= mins < end
    # Overnight window (e.g. 22:00–06:00) — not our default, but supported.
    return mins >= start or mins < end


def _active_hours_left(now: datetime | None = None) -> float:
    """Hours remaining in today's active window (0 if quiet)."""
    n = now or _local_now()
    if not _in_active_window(n):
        return 0.0
    mins = _local_minutes(n)
    end = ACTIVE_UNTIL_MIN
    start = ACTIVE_FROM_MIN
    if start < end:
        return max(0.0, (end - mins) / 60.0)
    # Overnight: remaining until end after midnight wrap.
    if mins >= start:
        return ((24 * 60 - mins) + end) / 60.0
    return max(0.0, (end - mins) / 60.0)


def _posts_needed_today() -> int:
    """How many more posts we still want today (toward TARGET, capped by MAX)."""
    left_cap = max(0, MAX_PER_DAY - _posts_today())
    left_target = max(0, TARGET_PER_DAY - _posts_today())
    return min(left_cap, left_target) if left_target else left_cap


def _behind_quota(now: datetime | None = None) -> bool:
    """True if pacing is behind: too few posts for elapsed fraction of the window."""
    n = now or _local_now()
    if not _in_active_window(n):
        return False
    posts = _posts_today()
    if posts >= TARGET_PER_DAY:
        return False
    start, end = ACTIVE_FROM_MIN, ACTIVE_UNTIL_MIN
    if start >= end:
        window = (24 * 60 - start) + end
    else:
        window = end - start
    if window <= 0:
        return False
    elapsed = _local_minutes(n) - start
    if start >= end and _local_minutes(n) < start:
        elapsed = (24 * 60 - start) + _local_minutes(n)
    elapsed = max(0, min(window, elapsed))
    expected = TARGET_PER_DAY * (elapsed / window)
    # Slight buffer so we don't soft-score too early in the morning.
    return posts + 0.35 < expected


def _effective_min_score() -> float:
    """Soften quality bar when behind daily target so 5–6 posts still land."""
    base = MIN_INTERNAL_SCORE
    soft = min(base, SOFT_MIN_SCORE)
    posts = _posts_today()
    needed = max(0, TARGET_PER_DAY - posts)
    if needed <= 0:
        return base
    hours_left = _active_hours_left()
    if hours_left <= 0:
        return base
    # Behind schedule or running out of window → lower bar.
    if _behind_quota() or (needed >= 2 and hours_left / needed < 2.2):
        # Late day / far behind: go down to soft floor.
        if hours_left / max(needed, 1) < 1.4 or posts == 0 and hours_left < 8:
            return soft
        return max(soft, base - 12)
    return base


def _required_gap_h() -> float:
    """
    Adaptive gap: keep human spacing early, compress when behind quota
    so we can still hit TARGET_PER_DAY before the window closes.
    """
    if MIN_GAP_H <= 0:
        return 0.0
    posts = _posts_today()
    needed = max(0, min(MAX_PER_DAY, TARGET_PER_DAY) - posts)
    hours_left = _active_hours_left()
    jitter_min = ((hash(f"{_day_key()}:{posts}") % 51) - 25) / 60.0

    if needed <= 0:
        # Already hit target — space remaining optional posts wider.
        return max(2.0, MIN_GAP_H + jitter_min)

    # Ideal even spacing across leftover window (keep ~15% slack).
    if hours_left > 0:
        paced = (hours_left * 0.85) / needed
    else:
        paced = MIN_GAP_H

    gap = min(MIN_GAP_H, paced) if _behind_quota() else min(MIN_GAP_H + 0.4, max(MIN_GAP_H * 0.85, paced))
    # Hard floor so we don't spam; softer floor when desperately behind.
    floor = 0.6 if (_behind_quota() and hours_left / needed < 1.5) else 1.0
    return max(floor, gap + jitter_min * 0.5)


def _seconds_until_active() -> int:
    """Seconds until the next ACTIVE_FROM in local TZ (0 if already active)."""
    now = _local_now()
    if _in_active_window(now):
        return 0
    start_h, start_m = divmod(ACTIVE_FROM_MIN, 60)
    target = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(60, int((target - now).total_seconds()))


def _fmt_window() -> str:
    def _hm(m: int) -> str:
        return f"{m // 60:02d}:{m % 60:02d}"

    return f"{_hm(ACTIVE_FROM_MIN)}–{_hm(ACTIVE_UNTIL_MIN)} {ACTIVE_TZ}"


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

    # levels — keep meaningful air from price (not hairline 24h extremes)
    ema21 = float(last["ema21"]) if not pd.isna(last["ema21"]) else close
    ema50 = float(last["ema50"]) if not pd.isna(last["ema50"]) else close
    atr = float(last["atr"])
    window48 = df.iloc[-48:] if len(df) >= 48 else df
    hi_48 = float(window48["high"].max())
    lo_48 = float(window48["low"].min())
    # Prefer ~1.3 ATR / ~1.2% of room so text/chart levels don't sit on price.
    min_air = max(atr * 1.3, close * 0.012)

    struct_below = sorted(
        (float(p) for p in (lo_24, lo_48, ema21, ema50) if p < close - min_air * 0.95),
        reverse=True,
    )
    if struct_below:
        support = struct_below[0]
    else:
        support = close - max(min_air, atr * 1.6)

    struct_above = sorted(
        float(p) for p in (hi_24, hi_48) if p > close + min_air * 0.95
    )
    if struct_above:
        resistance = struct_above[0]
    else:
        resistance = close + max(min_air, atr * 1.6)

    invalidation = min(ema50, support) * 0.995
    if close - invalidation < min_air:
        invalidation = close - min_air
    target_1 = max(resistance, close + atr * 1.5)
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
    min_score = _effective_min_score()
    relax_regime = _behind_quota() and _active_hours_left() < 6

    def _ok_regime(r: dict) -> bool:
        if relax_regime:
            return True
        phase = (r.get("btc_phase") or "").upper()
        if phase == "DOWNTREND":
            return r["regime"] in ("DOWNTREND", "CHOP") or bool(r.get("breakout"))
        return not (r["regime"] == "DOWNTREND" and not r.get("breakout"))

    updates: list[dict] = []
    fresh: list[dict] = []
    for r in rows:
        if r["score"] < min_score:
            continue
        if not _ok_regime(r):
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
    # Last resort near end of day: any scored coin off cooldown.
    if not picked and relax_regime and rows:
        for r in rows:
            if r["score"] < SOFT_MIN_SCORE:
                continue
            if _on_cooldown(r["symbol"]):
                continue
            picked.append(r)
            if len(picked) >= limit:
                break
    return picked


def _tf_speak(tf: str) -> str:
    """Human slang for the chart TF used in AI facts."""
    t = (tf or "4h").lower().strip()
    if t in ("1d", "d", "day", "1D"):
        return "на дневке"
    if t in ("4h", "240", "4H"):
        return "на 4ч"
    if t in ("1h", "60", "1H"):
        return "на часовике"
    return f"на {t}"


def _facts_block(
    row: dict,
    *,
    key_level: float,
    bias: str,
    post_type: str,
    prev: dict | None = None,
    mtf_confirmed: bool = False,
) -> str:
    """
    Facts for AI (Bukvar style).
    Simplified: close, key_level, ONE target, invalidation.
    NO redundant support/resistance/ema listing — price action focus.
    """
    ex = (row.get("exchange") or EXCHANGE_ID or "bybit").strip()
    close = float(row["close"])
    # Pick ONE target based on bias (not 2–3 levels)
    if bias == "short":
        target = float(row.get("support") or row.get("invalidation") or close * 0.97)
        inv = float(row.get("resistance") or close * 1.03)
    else:
        target = float(row.get("resistance") or row.get("target_1") or close * 1.03)
        inv = float(row.get("support") or row.get("invalidation") or close * 0.97)
    
    base = (
        f"symbol: {row['symbol']}\n"
        f"ticker: ${row['symbol'].replace('/USDT', '')}\n"
        f"post_type: {post_type}\n"
        f"bias_hint: {bias}\n"
        f"KEY_LEVEL: {key_level} (условие входа: закрепление выше/ниже)\n"
        f"human_key_level: {_fmt_price(key_level)}\n"
        f"exchange: {ex} Futures ({row.get('listings')})\n"
        f"chart_tf: {CHART_TF} (пиши {_tf_speak(CHART_TF)})\n"
        f"price_now: {_fmt_price(close)}\n"
        f"chg_24h_pct: {row['chg_24h']}\n"
        f"target: {_fmt_price(target)} (ОДНА главная цена — куда жду)\n"
        f"invalidation: {_fmt_price(inv)} (стоп/отмена сценария)\n"
        f"internal_score_0_100: {row['score']}\n"
        f"btc_phase: {row.get('btc_phase')}\n"
        f"mtf_confluence_1d: {'yes (можно упомянуть «и на дневке»)' if mtf_confirmed else 'no'}\n"
        "СТИЛЬ: Price action (ликвидность, зона, заброс, смягчение), НЕ ema/индикаторы.\n"
        "Начни «По $TICKER…». Голос: смотрю/жду/работаю. Условие → цель (не сразу).\n"
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
    mtf_confirmed: bool = False,
    extra_hint: str | None = None,
) -> dict | None:
    bias_n = (bias or _infer_bias(row)).strip().lower()
    if bias_n not in ("long", "short"):
        bias_n = "long"
    kl = float(key_level) if key_level is not None else _pick_key_level(row, bias_n)
    system = OUTLOOK_SYSTEM_UPDATE if post_type == "update" else OUTLOOK_SYSTEM_ANALYSIS
    mtf_note = (
        " Уровень также держится на дневке — если уместно, одной фразой «и на дневке» (не пиши «график/таймфрейм»)."
        if mtf_confirmed
        else ""
    )
    hint_suffix = f"\n\n{extra_hint}" if extra_hint else ""
    if post_type == "update":
        variation = random.choice(_VARIATION_HINTS_UPDATE)
        user = (
            "Короткий апдейт. "
            f"{variation} "
            "ONE цена — куда жду. Price action язык (ликвидность/зона/закрепление), НЕ ema."
            f"{mtf_note}{hint_suffix}\n\n"
            + _facts_block(row, key_level=kl, bias=bias_n, post_type=post_type, prev=prev, mtf_confirmed=mtf_confirmed)
        )
        max_tokens = 250
        temperature = 0.7
    else:
        variation = random.choice(_VARIATION_HINTS_ANALYSIS)
        user = (
            "Понятный пост, price action. "
            f"{variation} "
            "ОДНА главная цена + условие (если нужно). НЕ список уровней. НЕ индикаторы в тексте."
            f"{mtf_note}{hint_suffix}\n\n"
            + _facts_block(row, key_level=kl, bias=bias_n, post_type=post_type, prev=prev, mtf_confirmed=mtf_confirmed)
        )
        max_tokens = 380
        temperature = 0.76
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
    # Guard against the AI literally echoing the field name instead of its value
    # (e.g. "уровень human_key_level" or "KEY_LEVEL зафиксирован").
    for placeholder in ("human_key_level", "HUMAN_KEY_LEVEL", "KEY_LEVEL"):
        body = body.replace(placeholder, human_kl)
    body = _normalize_outlook_body(body)
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
        "post_subtype": (verdict.get("post_subtype") or "analysis").strip().lower(),
    }


def _pick_emoji_for_bias(bias: str) -> str:
    """Bukvar-style emoji for ticker line."""
    b = (bias or "long").lower()
    if b == "short":
        return random.choice(["🔻", "⚪️"])
    if b == "long":
        return random.choice(["🪙", "🧬", "💎"])
    return "⚪️"


def _format_post(row: dict, ai: dict, chart_tag: str = "", *, post_subtype: str | None = None) -> str:
    """
    Bukvar format:
    - analysis/update: #TICKER\\n\\nbody
    - chart_only: emoji #TICKER (no body, chart speaks)
    - greet/promo: text only (no ticker, handled separately)
    """
    del chart_tag
    coin = row["symbol"].replace("/USDT", "")
    ticker = (ai.get("ticker") or coin).strip().lstrip("#$").upper() or coin
    body = (ai.get("body") or "").strip()
    subtype = post_subtype or ai.get("post_subtype") or "analysis"
    
    # Clean formal phrases
    for bad in ("На основании анализа", "Следует отметить", "В заключение", "Данный актив"):
        body = body.replace(bad, "")
    
    # Chart-only: just emoji + ticker (body empty or very short)
    if subtype == "chart_only" or (len(body) < 50 and subtype == "analysis"):
        emoji = _pick_emoji_for_bias(ai.get("bias") or "long")
        return f"{emoji} #{ticker}"
    
    # Full analysis/update
    if not body:
        return f"#{ticker}"
    text = f"#{ticker}\n\n{body}"
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

    atr_abs = float(row.get("close") or 0) * float(row.get("atr_pct") or 0) / 100.0
    mtf_confirmed = False
    try:
        mtf_confirmed = await asyncio.to_thread(
            tv_chart.key_level_mtf_confirmed,
            row["symbol"],
            key_level,
            atr=atr_abs,
            exchange_id=row.get("exchange") or "bybit",
        )
    except Exception as e:
        print(f"[market_outlook] mtf check fail {row['symbol']}: {e}", flush=True)

    ai = await _ai_write_post(
        row,
        post_type=post_type,
        bias=bias_hint,
        key_level=key_level,
        prev=prev,
        mtf_confirmed=mtf_confirmed,
    )
    if not ai:
        return False

    prev_body = (prev or {}).get("body")
    pool = _facts_price_pool(row, float(ai.get("key_level") or key_level))
    needs_retry = (
        not _body_prices_sane(ai["body"], pool)
        or not _levels_have_numbers(ai["body"])
        or _too_similar(ai["body"], prev_body)
    )
    if needs_retry:
        print(
            f"[market_outlook] retrying AI text for {row['symbol']} "
            "(sanity/duplicate check failed)",
            flush=True,
        )
        retry = await _ai_write_post(
            row,
            post_type=post_type,
            bias=bias_hint,
            key_level=key_level,
            prev=prev,
            mtf_confirmed=mtf_confirmed,
            extra_hint=(
                "Важно: используй только числа из фактов ниже, ни одной новой цифры. "
                "Каждое упоминание поддержки/сопротивления — сразу с числом. "
                "Сформулируй иначе, не повторяй прошлый текст."
            ),
        )
        retry_pool = _facts_price_pool(row, float((retry or {}).get("key_level") or key_level)) if retry else []
        if (
            retry
            and _body_prices_sane(retry["body"], retry_pool)
            and _levels_have_numbers(retry["body"])
            and not _too_similar(retry["body"], prev_body)
        ):
            ai = retry
        else:
            print(
                f"[market_outlook] dropping post for {row['symbol']}: "
                "failed sanity/duplicate check twice",
                flush=True,
            )
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
        "mtf_confirmed": mtf_confirmed,
    }
    png, chart_tag = await asyncio.to_thread(
        tv_chart.chart_for_symbol,
        row["symbol"],
        exchange_id=row.get("exchange") or "bybit",
        levels=levels,
        bias=bias,
    )
    if not png:
        print(f"[market_outlook] WARNING: no chart rendered for {row['symbol']}", flush=True)
        try:
            await telegram_bot._notify_admins(
                f"[outlook] no chart rendered for {row['symbol']} "
                f"({row.get('exchange') or 'bybit'}) — posting text only."
            )
        except Exception as e:
            print(f"[market_outlook] admin alert fail: {e}", flush=True)
    text = _format_post(row, ai, chart_tag=chart_tag, post_subtype=ai.get("post_subtype"))
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
        body=ai.get("body"),
    )
    if count_toward_cap:
        _bump_posts_today(1)
    subtype_tag = ai.get("post_subtype") or "analysis"
    print(
        f"[market_outlook] published {row['symbol']} type={post_type} subtype={subtype_tag} "
        f"key={_fmt_price(key_level)} score={row['score']} "
        f"ai={ai['score_1_10']}/10 chart={chart_tag or 'none'}",
        flush=True,
    )
    return True


async def run_once() -> int:
    """Один проход: scan → shortlist → AI → publish. Возвращает число постов."""
    global _last_quiet_log_ts, _last_gap_skip_log_ts
    _maybe_reset_day_cap_from_env()

    if not _in_active_window():
        now = time.time()
        if now - _last_quiet_log_ts >= 1800:
            loc = _local_now().strftime("%H:%M")
            print(
                f"[market_outlook] quiet hours (now {loc} local, window {_fmt_window()})",
                flush=True,
            )
            _last_quiet_log_ts = now
        return 0

    left_day = MAX_PER_DAY - _posts_today()
    if left_day <= 0:
        print(f"[market_outlook] day cap ({MAX_PER_DAY}) reached", flush=True)
        return 0

    if not _global_gap_ok():
        age = _hours_since_any_post()
        now = time.time()
        if now - _last_gap_skip_log_ts >= 1800:
            print(
                f"[market_outlook] skip: gap {age:.1f}h < {_required_gap_h():.1f}h "
                f"(posts_today={_posts_today()}/{MAX_PER_DAY} "
                f"target={TARGET_PER_DAY} behind={_behind_quota()})",
                flush=True,
            )
            _last_gap_skip_log_ts = now
        return 0

    limit = min(MAX_PER_RUN, left_day)
    eff_score = _effective_min_score()
    print(
        f"[market_outlook] scan… candidates={len(CANDIDATES)} limit={limit} "
        f"posts={_posts_today()}/{TARGET_PER_DAY} (cap {MAX_PER_DAY}) "
        f"min_score={eff_score:.0f} gap≥{_required_gap_h():.1f}h "
        f"hours_left={_active_hours_left():.1f}",
        flush=True,
    )
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
        print(
            f"[market_outlook] no setup ≥{eff_score:.0f} "
            f"(best={top[0]['symbol']}={top[0]['score']})",
            flush=True,
        )
        return 0

    # Human-like: don't fire exactly on the 5-minute tick.
    delay = random.randint(40, 240)
    print(f"[market_outlook] human delay {delay}s before publish…", flush=True)
    await asyncio.sleep(delay)
    # Re-check window after delay (near 23:30 edge).
    if not _in_active_window():
        print("[market_outlook] skipped: left active window during delay", flush=True)
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
        f"target/day={TARGET_PER_DAY} max/day={MAX_PER_DAY} max/run={MAX_PER_RUN} "
        f"min_score={MIN_INTERNAL_SCORE} (soft={SOFT_MIN_SCORE}) "
        f"base_gap={MIN_GAP_H}h window={_fmt_window()}",
        flush=True,
    )
    # небольшой стартовый джиттер, чтобы не биться с ingest при рестарте
    await asyncio.sleep(45)
    while True:
        try:
            if not _in_active_window():
                wait = _seconds_until_active()
                # Wake periodically so config/redeploys aren't stuck all night.
                sleep_for = min(wait, 1800)
                loc = _local_now().strftime("%H:%M")
                print(
                    f"[market_outlook] quiet ({loc} local) — sleep {sleep_for}s "
                    f"until {_fmt_window()}",
                    flush=True,
                )
                await asyncio.sleep(sleep_for)
                continue
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[market_outlook] Упал: {e}", flush=True)
        await asyncio.sleep(max(60, INTERVAL_SEC))
