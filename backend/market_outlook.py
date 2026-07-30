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
Ты пишешь короткий разбор для Telegram-канала трейдера (SMC / Price Action).
Звучит как живой профи в ленте, не как шаблонный бот.

ЖЁСТКИЕ ПРАВИЛА:
1. Голос первого лица: «смотрю», «жду», «работаю», «фиксирую». Без канцелярита и AI-штампов
   («важно отметить», «следует», «таким образом», «на основании анализа»,
   «не повод для паники», «не теряю оптимизма», «Биток просел», «всё чётко», 
   «выглядит интересно», «интересная картина», «неплохой расклад»).
2. Только price action / SMC. НИКОГДА: ema, rsi, adx, индикаторы, штамп «ключевое условие»,
   шаблон «Цена находится между…».
   Можно: зона спроса/предложения (OB), ликвидность (сняли/собрали/свип), заброс, реакция,
   слом структуры (BOS/CHoCH), POI, пул ликвидности, инвалидация.
3. Цены — мягкими диапазонами, не одной точкой: «в зоне 64100–64400».
4. ЛОГИКА ЦЕН (обязательно сверяй с price_now из фактов):
   - long: цель ВЫШЕ текущей цены; инвалидация НИЖЕ.
   - short: цель НИЖЕ текущей; инвалидация ВЫШЕ.
   - Цель и инвалидация — РАЗНЫЕ уровни (не одна и та же цифра).
   - В body ОБЯЗАТЕЛЬНО одна явная отмена + ПОСЛЕДСТВИЕ: «инвалидация X — закрываю позу / отменяю сценарий / выхожу».
     НЕ просто «инвалидация X», а что КОНКРЕТНО делаешь при сломе.
   - Не пиши «пробой выше X → открываю шорт» (для шорта пробой вверх = отмена).
   - Не пиши «жду закрепление выше/ниже X», если price_now УЖЕ там — тогда говори
     «держимся / уже выше(ниже) / смотрю продолжение к …».
5. Старт фразы — ВАРЬИРУЙ (не копируй один каркас):
   ~60% «По $TICKER …»; остальные: с сессии («Под Европу по $TICKER…»),
   с действия («Сняли ликвидность по $TICKER…»), с зоны («$TICKER в зоне предложения…»).
6. Структура 1–2 абзаца, 160–280 символов. Не заканчивай висящим «, и на дневке.» —
   встраивай дневку внутрь фразы естественно или не упоминай.
7. В ~половине постов мягко упомяни менеджмент: частичный фикс / остаток в Б/У.
8. НЕ добавляй отдельной строкой «Ключевой уровень — …». Уровень уже в тексте сценария.

Примеры тона (НЕ копируй):
• «По BTC на Азии зашли в предложение около 64.1–64.4k. Жду реакцию; если удержит —
  первая цель пул 63.2–63.5k, часть сниму на импульсе. Ниже 61.8k — закрываю, сценарий слом.»
• «Под Европу по SOL свипнули снизу — реакция есть. Смотрю выход к 74.5–75.0;
  ниже вчерашнего минимума закрываю идею.»
• «AAVE уже ниже 220, ждать пробой смысла нет. Работаю продолжение шорта к 209–211,
  стоп выше локального хая — там отменяю.»

Верни JSON:
{
  "ticker": "BTC",
  "body": "160–280 символов",
  "score_1_10": 7,
  "bias": "long",
  "target": 63200,
  "invalidation": 61800,
  "post_subtype": "analysis"
}
""".strip()

OUTLOOK_SYSTEM_UPDATE = """
Короткий апдейт-reply к прошлому разбору. Честно и по-человечески.

Правила:
1. Варьируй старт: чаще «По $TICKER…», иногда сразу факт («Дошли…», «Сломали…»).
2. Сценарий отработал (даже небольшое движение в нашу сторону):
   факт + фиксация («забрал часть / остаток в Б/У») + что дальше смотрю.
3. Слом сценария: не приукрашивай. «Структуру сломали, отменяю, на заборе.»
4. Price action язык. 90–200 символов. Без «Ключевой уровень — …» отдельной строкой.
5. Цены согласуй с price_now из фактов.

Пример:
«По SOL дошли до верхней границы зоны — реакцию забрали. Часть зафиксировал, остаток в Б/У. Дальше смотрю, удержит ли уровень.»

Верни JSON:
{
  "ticker": "SOL",
  "body": "90–200 символов",
  "score_1_10": 7,
  "bias": "long",
  "target": 75.0,
  "post_subtype": "update"
}
""".strip()

# backward-compatible alias
OUTLOOK_SYSTEM = OUTLOOK_SYSTEM_ANALYSIS

# Variation hints: avoid identical "По $TICKER + Ключевое условие" skeleton.
_VARIATION_HINTS_ANALYSIS = [
    "Начни с «По $TICKER» + где цена сейчас. Дальше сценарий без штампа «ключевое условие».",
    "Начни с сессии («Под Европу / На Азии / Перед Америкой») + $TICKER. Потом зона → цель.",
    "Начни с действия: сняли/свипнули/зашли в зону по $TICKER. Потом что смотришь.",
    "Начни с зоны: «$TICKER в предложении/спросе…». Условие формулируй живо, не шаблоном.",
    "Коротко и по делу: где мы → куда жду → где отмена. Без канцелярита.",
    "Если price_now уже за key_level — не пиши «жду закрепление», пиши продолжение/удержание.",
]
_VARIATION_HINTS_UPDATE = [
    "Факт отработки (даже небольшой) + фиксация части/Б/У + что дальше.",
    "Дошли до зоны / реакция — без пафоса. Один следующий ориентир мягко.",
    "Если слом — честно отмени. Без попытки «всё равно был прав».",
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


def _too_similar_any_recent(
    new_body: str,
    *,
    skip_symbol: str | None = None,
    ratio_hi: float = 0.82,
) -> bool:
    """Near-duplicate vs any recent outlook body (cross-symbol anti-dupe)."""
    a = " ".join((new_body or "").lower().split())
    if not a:
        return False
    for sym, meta in _recent_posts().items():
        if skip_symbol and str(sym) == str(skip_symbol):
            # same-symbol prev already checked via _too_similar(prev_body)
            continue
        if not isinstance(meta, dict):
            continue
        prev = meta.get("body")
        if not prev:
            continue
        b = " ".join(str(prev).lower().split())
        if not b:
            continue
        if difflib.SequenceMatcher(None, a, b).ratio() >= ratio_hi:
            return True
    return False


_AI_SMELL_PHRASES = (
    "не повод для паники",
    "не теряю оптимизма",
    "биток просел",
    "цена находится между",
    "это говорит о",
    "на основании анализа",
    "следует отметить",
    "таким образом",
    "важно отметить",
    "всё чётко",
    "все четко",
    "выглядит интересно",
    "интересная картина",
    "неплохой расклад",
    "интересный расклад",
)


def _target_side_ok(
    bias: str,
    close: float,
    target: float | None,
    *,
    eps: float = 0.001,
) -> bool:
    """long → target > close; short → target < close."""
    if target is None:
        return True
    try:
        c = float(close)
        t = float(target)
    except (TypeError, ValueError):
        return True
    if c <= 0 or t <= 0:
        return True
    b = (bias or "long").lower()
    if b == "long":
        return t > c * (1.0 + eps)
    if b == "short":
        return t < c * (1.0 - eps)
    return True


def _invalidation_side_ok(
    bias: str,
    close: float,
    invalidation: float | None,
    target: float | None = None,
    *,
    eps: float = 0.001,
) -> bool:
    """long → inv < close; short → inv > close; inv != target."""
    if invalidation is None:
        return True
    try:
        c = float(close)
        inv = float(invalidation)
    except (TypeError, ValueError):
        return True
    if c <= 0 or inv <= 0:
        return True
    b = (bias or "long").lower()
    if b == "long" and inv >= c * (1.0 - eps):
        return False
    if b == "short" and inv <= c * (1.0 + eps):
        return False
    if target is not None:
        try:
            t = float(target)
            if t > 0 and abs(inv - t) / max(c, t, inv) < 0.002:
                return False
        except (TypeError, ValueError):
            pass
    return True


def _body_logic_ok(body: str, *, close: float, bias: str) -> bool:
    """Reject known bad patterns from post_review (BCH upside-break→short, AI pep-talk)."""
    text = (body or "").lower()
    if not text:
        return False
    for phrase in _AI_SMELL_PHRASES:
        if phrase in text:
            return False

    try:
        c = float(close)
    except (TypeError, ValueError):
        return True
    if c <= 0:
        return True

    b = (bias or "long").lower()
    # «если пробьёт/пробьем X … открываю/работаю шорт» where X > close → upside break opens short
    if b == "short":
        for m in re.finditer(
            r"(пробь[её]т|пробьём|пробьем|пробой)\s+(?:выше\s+)?([\d\s]+(?:\.\d+)?).{0,40}?"
            r"(открываю\s+шорт|работаю\s+шорт|шорт\s+с\s+цель)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            try:
                lvl = float(m.group(2).replace(" ", ""))
            except ValueError:
                continue
            if lvl > c * 1.001:
                return False
    return True


def _post_passes_gates(
    ai: dict,
    *,
    row: dict,
    prev_body: str | None,
    pool: list[float],
) -> bool:
    """All pre-publish sanity checks for an AI outlook body."""
    body = ai.get("body") or ""
    close_now = float(row.get("close") or 0)
    bias_chk = (ai.get("bias") or "long").lower()
    target = ai.get("target")
    inv = ai.get("invalidation")
    sym = row.get("symbol")
    if not _body_prices_sane(body, pool):
        return False
    if not _levels_have_numbers(body):
        return False
    if _too_similar(body, prev_body):
        return False
    if _too_similar_any_recent(body, skip_symbol=str(sym) if sym else None):
        return False
    if not _scenario_levels_sane(body, close=close_now, bias=bias_chk):
        return False
    if not _target_side_ok(bias_chk, close_now, target if isinstance(target, (int, float)) else None):
        return False
    if not _invalidation_side_ok(
        bias_chk,
        close_now,
        inv if isinstance(inv, (int, float)) else None,
        target if isinstance(target, (int, float)) else None,
    ):
        return False
    if not _body_logic_ok(body, close=close_now, bias=bias_chk):
        return False
    # Кросс-проверка VIP/News противоречий: если за последние 24ч по той же монете
    # есть пост с противоположным bias — вероятно конфликт идей.
    if not _check_vip_news_conflict(sym, bias_chk):
        print(
            f"[market_outlook] WARNING: {sym} {bias_chk} conflicts with recent opposite bias post",
            flush=True,
        )
        # Не блокируем жёстко (может быть разворот), но предупреждаем.
    return True


def _check_vip_news_conflict(symbol: str | None, bias: str) -> bool:
    """
    Проверка: если за последние 24ч по той же монете был пост с противоположным bias
    → возможно конфликт между VIP LONG и news SHORT (или наоборот).
    Возвращает False если конфликт есть (противоположный bias свежий).
    """
    if not symbol:
        return True
    recent = _recent_posts()
    prev = recent.get(str(symbol))
    if not prev:
        return True
    age_h = (time.time() - float(prev.get("ts") or 0)) / 3600.0
    if age_h > 24.0:
        return True
    prev_bias = (prev.get("bias") or "long").strip().lower()
    curr_bias = (bias or "long").strip().lower()
    # Противоположные bias: long vs short или наоборот
    if (prev_bias == "long" and curr_bias == "short") or (prev_bias == "short" and curr_bias == "long"):
        return False
    return True


def _normalize_outlook_body(body: str) -> str:
    """
    Push wording toward Bukvar SMC style:
    - Remove EMA mentions, formal timeframe talk.
    - Map support/resistance → supply/demand zones when appropriate.
    - Clean glue artifacts from replacements.
    """
    text = body or ""
    # Remove EMA mentions entirely from body (they're indicator talk, not price action).
    text = re.sub(r"\bторгуется\s+(ниже|выше|около|между)\s+ema\d+", r"цена \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(ниже|выше|около)\s+ema\d+\s+(и\s+ema\d+)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bema\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"EMA\s*\d+", "", text, flags=re.IGNORECASE)

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
        # Formal → conversational (careful: avoid hanging ", и на дневке.")
        (r",?\s*также\s+совпадает\s+с\s+дневк\w*", " и это видно на дневке"),
        (r"совпадает с\s+дневк\w*", "держится и на дневке"),
        (r",\s*и на дневке\.?\s*$", "."),
        (r"\s+и на дневке\.?\s*$", "."),
        (r"\bЦена торгуется", "Торгуемся"),
        (r"цена торгуется", "цена"),
        (r"Это говорит о", ""),
        (r"данный актив", "актив"),
        (r"зона консолидации", "боковое движение"),
        (r"давление продавцов", "продавцы давят"),
        (r"импульс\s+(вверх|вниз)", r"движение \1"),
        (r"Ключевое условие[:\s—–-]*", ""),
        (r"ключевое условие[:\s—–-]*", ""),
        (r"к поддержке\b", "к зоне спроса"),
        (r"от поддержки\b", "от зоны спроса"),
        (r"к сопротивлению\b", "к зоне предложения"),
        (r"от сопротивления\b", "от зоны предложения"),
        (r"не\s+повод\s+для\s+паники[!.,]?", ""),
        (r"не\s+теряю\s+оптимизма[:\s—–,-]*", ""),
        (r"Биток\s+просел[,!]?", "BTC просел"),
        (r"Цена\s+находится\s+между", "Цена между"),
        (r"это\s+зона\s+консолидации", "боковик"),
    )
    for pat, repl in replacements:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)

    # Drop forced trailing key-level lines (we weave levels into body instead).
    text = re.sub(
        r"\n*\s*Ключевой уровень\s*[—–:-]\s*[\d\s.,]+\.?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\.\s+\.", ".", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r",\s*,", ",", text)
    return text.strip()


def _key_level_relation(close: float, key_level: float, bias: str) -> str:
    """How price sits vs key level — drives AI wording so we don't wait for already-true breaks."""
    try:
        c, k = float(close), float(key_level)
    except (TypeError, ValueError):
        return "unknown"
    if k <= 0:
        return "unknown"
    pct = (c - k) / k * 100.0
    b = (bias or "long").lower()
    if abs(pct) < 0.15:
        return "at_level"
    if b == "short":
        if c < k:
            return "already_below"  # don't wait for break below
        return "still_above"
    # long / default
    if c > k:
        return "already_above"  # don't wait for break above
    return "still_below"


def _scenario_levels_sane(body: str, *, close: float, bias: str) -> bool:
    """
    Reject obviously stale scenarios:
    - long with all cited targets below close
    - short with all cited targets above close
    - 'жду закрепление выше X' when already above X (and vice versa)
    """
    text = (body or "").lower()
    nums = _price_numbers_in_text(body)
    b = (bias or "long").lower()
    try:
        c = float(close)
    except (TypeError, ValueError):
        return True
    if c <= 0:
        return True

    # Stale "wait for break" phrasing
    for m in re.finditer(
        r"(жду|ждём|ждем|если)\s+.{0,24}?(закреп\w*|проб\w*|удерж\w*)\s+(выше|ниже)\s+([\d\s]+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    ):
        side = m.group(2).lower()
        try:
            lvl = float(m.group(3).replace(" ", ""))
        except ValueError:
            continue
        if lvl <= 0:
            continue
        if side == "выше" and c > lvl * 1.001:
            return False
        if side == "ниже" and c < lvl * 0.999:
            return False

    # Target side check: use numbers that look like targets (not the close itself)
    candidates = [n for n in nums if n > 0 and abs(n - c) / c > 0.002]
    if len(candidates) >= 1:
        if b == "long" and all(n < c for n in candidates):
            # allow one support/inval below if there's also something above — already filtered
            return False
        if b == "short" and all(n > c for n in candidates):
            return False
    return True


def _extract_target_from_verdict(verdict: dict, row: dict, bias: str) -> float | None:
    """Prefer AI target field, else row target_1 / resistance/support by bias."""
    for key in ("target", "target_1"):
        v = verdict.get(key) if key == "target" else row.get(key)
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except (TypeError, ValueError):
            pass
    b = (bias or "long").lower()
    fallback = row.get("resistance") if b != "short" else row.get("support")
    try:
        if fallback is not None and float(fallback) > 0:
            return float(fallback)
    except (TypeError, ValueError):
        pass
    # last resort: first price in body away from close
    try:
        close = float(row.get("close") or 0)
    except (TypeError, ValueError):
        close = 0.0
    body = str(verdict.get("body") or "")
    for n in _price_numbers_in_text(body):
        if close > 0 and abs(n - close) / close > 0.003:
            if b == "short" and n < close:
                return n
            if b != "short" and n > close:
                return n
    return None


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
    """{ symbol: {ts, bias, key_level, close, post_type, body, message_id, root_message_id} }."""
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
                    "message_id": None,
                    "root_message_id": None,
                    "target": None,
                    "invalidation": None,
                }
            elif isinstance(v, dict) and "ts" in v:
                out[str(k)] = {
                    "ts": float(v["ts"]),
                    "bias": (v.get("bias") or "long"),
                    "key_level": v.get("key_level"),
                    "close": v.get("close"),
                    "post_type": v.get("post_type") or "analysis",
                    "body": v.get("body"),
                    "message_id": v.get("message_id"),
                    "root_message_id": v.get("root_message_id") or v.get("message_id"),
                    "target": v.get("target"),
                    "invalidation": v.get("invalidation"),
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
    message_id: int | None = None,
    root_message_id: int | None = None,
    target: float | None = None,
    invalidation: float | None = None,
) -> None:
    m = _recent_posts()
    now = time.time()
    cutoff = now - max(SYMBOL_COOLDOWN_H, UPDATE_MAX_AGE_H) * 3600 * 2
    m = {k: v for k, v in m.items() if float(v.get("ts") or 0) >= cutoff}
    prev = m.get(symbol) or {}
    if post_type == "analysis" and message_id:
        root_id = int(message_id)
    else:
        root_id = root_message_id or prev.get("root_message_id") or prev.get("message_id")
        if root_id is not None:
            root_id = int(root_id)
    m[symbol] = {
        "ts": now,
        "bias": bias,
        "key_level": key_level,
        "close": close,
        "post_type": post_type,
        "body": (body or "")[:600],
        "message_id": int(message_id) if message_id else prev.get("message_id"),
        "root_message_id": root_id,
        "target": target if target is not None else prev.get("target"),
        "invalidation": invalidation if invalidation is not None else prev.get("invalidation"),
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


def _soft_scenario_move(row: dict, prev: dict) -> bool:
    """Букварь-стиль: хватает лёгкого движения в сторону сценария / к зоне."""
    bias = (prev.get("bias") or "long").strip().lower()
    try:
        old_c = float(prev["close"]) if prev.get("close") is not None else None
    except (TypeError, ValueError):
        old_c = None
    now_c = float(row["close"])
    if not old_c or old_c <= 0:
        return True
    moved = (now_c - old_c) / old_c
    # ~0.15% в сторону сценария — уже «дошли / реакция»
    if bias == "short" and moved <= -0.0015:
        return True
    if bias != "short" and moved >= 0.0015:
        return True
    for key in ("key_level", "target"):
        try:
            lvl = float(prev[key]) if prev.get(key) is not None else None
        except (TypeError, ValueError):
            lvl = None
        if lvl is None or lvl <= 0:
            continue
        if abs(now_c - lvl) / lvl <= 0.004:
            return True
        if bias == "short" and now_c <= lvl * 1.002:
            return True
        if bias != "short" and now_c >= lvl * 0.998:
            return True
    return abs(moved) >= 0.0025


def _update_context(row: dict) -> dict | None:
    """Prior post + soft move → reply-update (приукрашенный, как Букварь)."""
    prev = _recent_posts().get(row["symbol"])
    if not prev:
        return None
    age_h = (time.time() - float(prev["ts"])) / 3600.0
    if age_h < UPDATE_MIN_AGE_H or age_h > UPDATE_MAX_AGE_H:
        return None
    if (prev.get("post_type") or "") == "update" and age_h < UPDATE_MIN_AGE_H * 1.5:
        return None
    if not _soft_scenario_move(row, prev):
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

    relation = _key_level_relation(close, key_level, bias)
    relation_hint = {
        "already_above": "price_now УЖЕ ВЫШЕ key_level — НЕ пиши «жду закрепление выше». Пиши удержание/продолжение к target.",
        "already_below": "price_now УЖЕ НИЖЕ key_level — НЕ пиши «жду закрепление ниже». Пиши продолжение шорта к target.",
        "still_above": "price_now ещё выше key_level — для шорта можно ждать заход/закрепление ниже.",
        "still_below": "price_now ещё ниже key_level — для лонга можно ждать заход/закрепление выше.",
        "at_level": "price_now около key_level — говори про реакцию/удержание зоны.",
        "unknown": "",
    }.get(relation, "")

    base = (
        f"symbol: {row['symbol']}\n"
        f"ticker: ${row['symbol'].replace('/USDT', '')}\n"
        f"post_type: {post_type}\n"
        f"bias_hint: {bias}\n"
        f"KEY_LEVEL: {key_level}\n"
        f"human_key_level: {_fmt_price(key_level)}\n"
        f"key_level_vs_price: {relation}\n"
        f"{relation_hint}\n"
        f"exchange: {ex} Futures ({row.get('listings')})\n"
        f"chart_tf: {CHART_TF} (пиши {_tf_speak(CHART_TF)} только если уместно, не висящим хвостом)\n"
        f"price_now: {_fmt_price(close)}\n"
        f"chg_24h_pct: {row['chg_24h']}\n"
        f"target: {_fmt_price(target)} (ОДНА главная цена — куда жду; должна быть по сторону bias)\n"
        f"invalidation: {_fmt_price(inv)} (стоп/отмена; ДРУГОЙ уровень, не равен target)\n"
        f"internal_score_0_100: {row['score']}\n"
        f"btc_phase: {row.get('btc_phase')}\n"
        f"mtf_confluence_1d: {'yes (можно естественно вплести «на дневке»)' if mtf_confirmed else 'no'}\n"
        "СТИЛЬ: Price action. Без ema/индикаторов. Без штампа «Ключевое условие».\n"
        "Варьируй старт. Не добавляй отдельную строку «Ключевой уровень — …».\n"
        "В JSON: target и invalidation — числа; в body явно напиши отмену.\n"
        "Запрещено: «не повод для паники», «не теряю оптимизма», «Цена находится между».\n"
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
            "Одна цель. Price action. Без «Ключевое условие» и без отдельной строки уровня."
            f"{mtf_note}{hint_suffix}\n\n"
            + _facts_block(row, key_level=kl, bias=bias_n, post_type=post_type, prev=prev, mtf_confirmed=mtf_confirmed)
        )
        max_tokens = 260
        temperature = 0.78
    else:
        variation = random.choice(_VARIATION_HINTS_ANALYSIS)
        user = (
            "Живой пост трейдера, price action. "
            f"{variation} "
            "ОДНА главная цель по сторону bias. Не шаблон. Не индикаторы. "
            "Верни target и invalidation числами в JSON. В body явно укажи отмену."
            f"{mtf_note}{hint_suffix}\n\n"
            + _facts_block(row, key_level=kl, bias=bias_n, post_type=post_type, prev=prev, mtf_confirmed=mtf_confirmed)
        )
        max_tokens = 400
        temperature = 0.88
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
    human_kl = _fmt_price(kl)
    for placeholder in ("human_key_level", "HUMAN_KEY_LEVEL", "KEY_LEVEL"):
        body = body.replace(placeholder, human_kl)
    body = _normalize_outlook_body(body)
    # If key level still missing, weave it into a natural clause — never a bolted footer.
    if human_kl not in body and human_kl.replace(" ", "") not in body.replace(" ", ""):
        if post_type == "update":
            body = f"{body.rstrip().rstrip('.')} — ориентир {_fmt_price(kl)}."
        else:
            body = f"{body.rstrip().rstrip('.')} Зона/ориентир около {_fmt_price(kl)}."
        body = _normalize_outlook_body(body)
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
    target_out = _extract_target_from_verdict(verdict, row, bias_out)
    inv_out = None
    for key in ("invalidation", "inval", "stop"):
        try:
            v = verdict.get(key)
            if v is not None and float(v) > 0:
                inv_out = float(v)
                break
        except (TypeError, ValueError):
            pass
    if inv_out is None:
        try:
            close = float(row.get("close") or 0)
            if bias_out == "short":
                inv_out = float(row.get("resistance") or close * 1.03)
            else:
                inv_out = float(row.get("support") or row.get("invalidation") or close * 0.97)
        except (TypeError, ValueError):
            inv_out = None
    return {
        "ticker": ticker,
        "body": body,
        "score_1_10": max(1, min(10, s10)),
        "bias": bias_out,
        "key_level": kl,
        "target": target_out,
        "invalidation": inv_out,
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


def _format_post(row: dict, ai: dict, chart_tag: str = "", *, post_subtype: str | None = None, prev_post: dict | None = None) -> str:
    """
    Bukvar format:
    - analysis/update: emoji #TICKER\\n\\nbody
    - chart_only: emoji #TICKER (no body, chart speaks)
    - greet/promo: text only (no ticker, handled separately)
    - update: добавляет "Обновление: " если повторный post_type=update
    """
    del chart_tag
    coin = row["symbol"].replace("/USDT", "")
    ticker = (ai.get("ticker") or coin).strip().lstrip("#$").upper() or coin
    body = (ai.get("body") or "").strip()
    subtype = post_subtype or ai.get("post_subtype") or "analysis"
    bias = (ai.get("bias") or "long").strip().lower()
    
    # Clean formal / AI-smell phrases
    for bad in (
        "На основании анализа",
        "Следует отметить",
        "В заключение",
        "Данный актив",
        "не повод для паники",
        "Не повод для паники",
        "не теряю оптимизма",
        "Не теряю оптимизма",
        "Цена находится между",
        "всё чётко",
        "все четко",
        "выглядит интересно",
        "интересная картина",
    ):
        body = body.replace(bad, "")
    
    # Emoji before ticker (Bukvar style): long → 🪙/🧬, short → 🔻, neutral → ⚪️
    emoji = _pick_emoji_for_bias(bias)
    
    # Chart-only: just emoji + ticker (body empty or very short)
    if subtype == "chart_only" or (len(body) < 50 and subtype == "analysis"):
        return f"{emoji} #{ticker}"
    
    # Full analysis/update: emoji #TICKER + body
    if not body:
        return f"{emoji} #{ticker}"
    
    # Если update и есть предыдущий пост (не первый analysis) — добавляем маркер обновления
    if subtype == "update" and prev_post and prev_post.get("post_type") != "update":
        # Первое обновление к analysis → пометка "Обновление:"
        body = f"Обновление: {body}"
    
    text = f"{emoji} #{ticker}\n\n{body}"
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
    needs_retry = not _post_passes_gates(ai, row=row, prev_body=prev_body, pool=pool)
    if needs_retry:
        print(
            f"[market_outlook] retrying AI text for {row['symbol']} "
            "(sanity/duplicate/scenario check failed)",
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
                "Цели строго по сторону bias относительно price_now. "
                "invalidation строго по другую сторону и ≠ target. "
                "Не пиши «жду закрепление», если key_level_vs_price = already_above/already_below. "
                "Запрещено: «не повод для паники», «не теряю оптимизма», «Цена находится между». "
                "Для short: пробой ВЫШЕ уровня = отмена, не вход в шорт. "
                "Сформулируй иначе, без штампа «Ключевое условие», не повторяй прошлый текст."
            ),
        )
        retry_pool = _facts_price_pool(row, float((retry or {}).get("key_level") or key_level)) if retry else []
        if retry and _post_passes_gates(retry, row=row, prev_body=prev_body, pool=retry_pool):
            ai = retry
        else:
            print(
                f"[market_outlook] dropping post for {row['symbol']}: "
                "failed sanity/duplicate/scenario check twice",
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
    text = _format_post(row, ai, chart_tag=chart_tag, post_subtype=ai.get("post_subtype"), prev_post=prev)
    reply_to = None
    if post_type == "update" and prev:
        reply_to = prev.get("root_message_id") or prev.get("message_id")
        try:
            reply_to = int(reply_to) if reply_to else None
        except (TypeError, ValueError):
            reply_to = None
    try:
        msg_id = await telegram_bot.publish_news(
            text,
            photo_png=png,
            reply_to_message_id=reply_to,
        )
    except Exception as e:
        print(f"[market_outlook] publish fail {row['symbol']}: {e}", flush=True)
        return False
    if not msg_id:
        print(f"[market_outlook] publish returned no msg_id for {row['symbol']}", flush=True)
        return False
    target_v = None
    try:
        if ai.get("target") is not None:
            target_v = float(ai.get("target")) or None
    except (TypeError, ValueError):
        target_v = None
    if target_v is None:
        try:
            target_v = float(row.get("target_1") or row.get("resistance") or 0) or None
        except (TypeError, ValueError):
            target_v = None
        if (bias or "").lower() == "short":
            try:
                target_v = float(row.get("support") or row.get("target_1") or 0) or target_v
            except (TypeError, ValueError):
                pass
    root_id = None
    if post_type == "analysis":
        root_id = int(msg_id)
    elif prev:
        root_id = prev.get("root_message_id") or prev.get("message_id")
    try:
        import post_review as _post_review

        _post_review.save_chart_png(row["symbol"], png)
    except Exception as e:
        print(f"[market_outlook] chart save skip: {e}", flush=True)
    inv_v = None
    try:
        if ai.get("invalidation") is not None:
            inv_v = float(ai["invalidation"]) or None
    except (TypeError, ValueError):
        inv_v = None
    _remember_post(
        row["symbol"],
        bias=bias,
        key_level=key_level,
        close=float(row["close"]),
        post_type=post_type,
        body=ai.get("body"),
        message_id=int(msg_id),
        root_message_id=int(root_id) if root_id else None,
        target=target_v,
        invalidation=inv_v,
    )
    if count_toward_cap:
        _bump_posts_today(1)
    subtype_tag = ai.get("post_subtype") or "analysis"
    print(
        f"[market_outlook] published {row['symbol']} type={post_type} subtype={subtype_tag} "
        f"key={_fmt_price(key_level)} score={row['score']} "
        f"ai={ai['score_1_10']}/10 chart={chart_tag or 'none'} "
        f"msg={msg_id} reply_to={reply_to} target={target_v}",
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


async def maybe_rewrite_once_on_boot() -> None:
    """Один раз после деплоя переписать подписи недавних постов (v1 style fix)."""
    flag = "outlook_style_rewrite_v3"
    if (db.get_setting(flag) or "").strip():
        print(f"[market_outlook] rewrite_once skip ({flag} done)", flush=True)
        return
    await asyncio.sleep(90)
    try:
        recent = _recent_posts()
        for sym, meta in list(recent.items())[:8]:
            print(
                f"[market_outlook] recent {sym}: msg={meta.get('message_id')} "
                f"body_len={len(str(meta.get('body') or ''))} "
                f"bias={meta.get('bias')} close={meta.get('close')}",
                flush=True,
            )
        result = await rewrite_and_edit_recent_posts(limit=12)
        db.set_setting(
            flag,
            json.dumps(
                {
                    "ts": time.time(),
                    **{k: result.get(k) for k in ("edited", "skipped", "failed")},
                }
            ),
        )
    except Exception as e:
        print(f"[market_outlook] rewrite_once fail: {e}", flush=True)


REWRITE_SYSTEM = """
Ты редактор крипто-канала. Перепиши ГОТОВЫЙ пост так, чтобы он звучал живо и профессионально (SMC / price action).
Сохрани: тикер, bias, уровни/цели/смысл сценария. Не меняй торговую идею на противоположную.

ОБЯЗАТЕЛЬНО поправь логику цен:
- long: цель ВЫШЕ close; инвалидация НИЖЕ.
- short: цель НИЖЕ close; инвалидация ВЫШЕ.
- Цель и инвалидация — разные уровни.
- Для short: пробой ВЫШЕ уровня = отмена, НЕ «открываю шорт».
- В body одна явная отмена («инвалидация / стоп / отмена — выше|ниже X»).

Убери: штамп «Ключевое условие», висящее «, и на дневке.», канцелярит, AI-штампы,
«не повод для паники», «не теряю оптимизма», «Цена находится между», EMA/индикаторы.
Если по close цена УЖЕ за уровнем — «уже ниже/выше… смотрю продолжение», не «жду закрепление».

Верни JSON: {"body": "...", "ticker": "BTC", "invalidation": 123.0}
""".strip()


async def _rewrite_one_body(meta: dict, symbol: str) -> str | None:
    body = (meta.get("body") or "").strip()
    if not body or len(body) < 40:
        return None
    coin = symbol.replace("/USDT", "")
    bias = meta.get("bias") or "long"
    close = meta.get("close")
    key_level = meta.get("key_level")
    target = meta.get("target")
    inv = meta.get("invalidation")
    relation = _key_level_relation(close or 0, key_level or 0, bias)
    user = (
        f"symbol: {symbol}\n"
        f"ticker: ${coin}\n"
        f"bias: {bias}\n"
        f"close_at_publish: {close}\n"
        f"key_level: {key_level}\n"
        f"target: {target}\n"
        f"invalidation: {inv}\n"
        f"key_level_vs_price: {relation}\n"
        f"original_body:\n{body}\n"
    )
    try:
        out = await ai_client.fast_json_completion(
            system=REWRITE_SYSTEM,
            user_text=user,
            max_tokens=360,
            temperature=0.55,
        )
    except Exception as e:
        print(f"[market_outlook] rewrite AI fail {symbol}: {e}", flush=True)
        return None
    if not isinstance(out, dict):
        return None
    new_body = _normalize_outlook_body((out.get("body") or "").strip())
    if len(new_body) < 60:
        return None
    # Soft reject obvious leftover AI smell / inverted short break
    try:
        c = float(close or 0)
    except (TypeError, ValueError):
        c = 0.0
    if c > 0 and not _body_logic_ok(new_body, close=c, bias=str(bias)):
        # one more pass via normalize already done — drop smell phrases hard
        for bad in _AI_SMELL_PHRASES:
            new_body = re.sub(re.escape(bad), "", new_body, flags=re.IGNORECASE)
        new_body = _normalize_outlook_body(new_body)
        if len(new_body) < 60 or not _body_logic_ok(new_body, close=c, bias=str(bias)):
            print(f"[market_outlook] rewrite logic reject {symbol}", flush=True)
            return None
    return new_body


async def rewrite_and_edit_recent_posts(*, limit: int = 12) -> dict:
    """
    Переписать текст недавних outlook-постов и отредактировать подписи в Telegram.
    Графики не трогаем (editMessageCaption).
    """
    import telegram_bot

    recent = _recent_posts()
    items = sorted(
        recent.items(),
        key=lambda kv: float((kv[1] or {}).get("ts") or 0),
        reverse=True,
    )[: max(1, limit)]

    edited = 0
    skipped = 0
    failed = 0
    details: list[dict] = []

    for symbol, meta in items:
        msg_id = meta.get("message_id")
        old_body = (meta.get("body") or "").strip()
        if not msg_id or not old_body:
            skipped += 1
            details.append({"symbol": symbol, "status": "skip_no_msg_or_body"})
            continue
        new_body = await _rewrite_one_body(meta, symbol)
        if not new_body:
            failed += 1
            details.append({"symbol": symbol, "status": "rewrite_fail"})
            continue
        ticker = symbol.replace("/USDT", "")
        emoji = _pick_emoji_for_bias(str(meta.get("bias") or "long"))
        caption = f"{emoji} #{ticker}\n\n{new_body}"[:1020]
        ok = await telegram_bot.edit_news_caption(int(msg_id), caption)
        if not ok:
            failed += 1
            details.append({"symbol": symbol, "status": "edit_fail", "msg_id": msg_id})
            continue
        # persist rewritten body
        _remember_post(
            symbol,
            bias=str(meta.get("bias") or "long"),
            key_level=meta.get("key_level"),
            close=float(meta.get("close") or 0),
            post_type=str(meta.get("post_type") or "analysis"),
            body=new_body,
            message_id=int(msg_id),
            root_message_id=meta.get("root_message_id") or msg_id,
            target=meta.get("target"),
        )
        edited += 1
        details.append(
            {
                "symbol": symbol,
                "status": "ok",
                "msg_id": msg_id,
                "old": old_body[:120],
                "new": new_body[:120],
            }
        )
        print(f"[market_outlook] rewritten+edited {symbol} msg={msg_id}", flush=True)
        await asyncio.sleep(1.2)

    summary = {"edited": edited, "skipped": skipped, "failed": failed, "details": details}
    print(f"[market_outlook] rewrite_and_edit done: {summary}", flush=True)
    try:
        await telegram_bot._notify_admins(
            f"✏️ Outlook rewrite: edited={edited} skipped={skipped} failed={failed}"
        )
    except Exception:
        pass
    return summary
