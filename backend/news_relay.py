"""
Ретрансляция market-analysis (график + разбор монеты) → @nowicki_news.

Эталон: Fed. Russian Insiders / Bitcoin Bullets —
chart + $TICKER ANALYSIS / #TICKER Market Analysis + уровни/сценарии.

Env:
  TELEGRAM_NEWS_SESSION / TELEGRAM_NEWS_SOURCE_CHANNELS / TELEGRAM_NEWS_TARGET_CHANNEL
  NEWS_RELAY_MAX_PER_HOUR     default 5
  NEWS_RELAY_MIN_SCORE        default 7
  NEWS_RELAY_MIN_GAP_SEC      default 600 (10 мин)
  NEWS_RELAY_STARTUP_LOOKBACK default 5
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime
from io import BytesIO

import ai_client
import database as db

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_NEWS_SESSION = os.getenv("TELEGRAM_NEWS_SESSION", "").strip()
TELEGRAM_NEWS_SOURCE_CHANNELS = os.getenv("TELEGRAM_NEWS_SOURCE_CHANNELS", "").strip()
TELEGRAM_NEWS_TARGET_CHANNEL = os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL", "").strip()

MAX_PER_HOUR = int(os.getenv("NEWS_RELAY_MAX_PER_HOUR", "5") or "5")
MIN_SCORE = int(os.getenv("NEWS_RELAY_MIN_SCORE", "7") or "7")
MIN_GAP_SEC = int(os.getenv("NEWS_RELAY_MIN_GAP_SEC", "600") or "600")
STARTUP_LOOKBACK = int(os.getenv("NEWS_RELAY_STARTUP_LOOKBACK", "5") or "5")

# Fed-style TA / coin outlook first. Override via TELEGRAM_NEWS_SOURCE_CHANNELS.
DEFAULT_NEWS_SOURCES = (
    "FedRussianInsiders,"
    "BitcoinBullets,"
    "CryptoCapoTG,"
    "tcgforyou,"
    "CryptoBusy,"
    "rektchat,"
    "lookonchainchannel,"
    "CryptoInnerCircle_Officiall,"
    "EveningTraderx,"
    "binancekillers_vips,"
    "WolfofTrading_Officiall,"
    "cryptoquant_official,"
    "glassnode,"
    "WatcherGuru,"
    "TreeNewsFeed"
)

_PROC_PREFIX = "news:"

_hour_bucket: str | None = None
_hour_count = 0
_last_publish_ts = 0.0
_recent_fingerprints: list[tuple[float, frozenset[str]]] = []

_VIP_RE = re.compile(
    r"(?im)(?:👉\s*)?(?:join\s+(?:our\s+)?vip|vip\s*(?:access\s*)?->|@\w*vip\w*|"
    r"t\.me/\w*vip\w*|vip registration).*$"
)
# Эталон Fed / Bullets
_STRONG_ANALYSIS = re.compile(
    r"(?is)("
    r"\$[A-Z0-9]{2,15}\s+ANALYSIS|"
    r"#[A-Z0-9]{2,15}\s+Market\s+Analysis|"
    r"TOTALCRYPTO\s+ANALYSIS|"
    r"(bull\s+case|bear\s+case).{0,40}(hold|lose|break|reclaim)"
    r")"
)
_ANALYSIS_HINT = re.compile(
    r"(?i)(\$[A-Z0-9]{2,15}\s+ANALYSIS|#[A-Z0-9]{2,15}\s+Market\s+Analysis|"
    r"trendline|higher\s+lows|support|resistance|price\s+discovery|"
    r"bull\s+trend|bear\s+trend|trading\s+at\s+\$?\d|"
    r"bull\s+case|bear\s+case|ascending\s+channel|descending\s+channel)"
)
_SIGNAL_PACK = re.compile(
    r"(?is)\b(leverage\s*[:=]?\s*\d|entry\s*[:=]|targets?\s*[:=].{0,40}\d|"
    r"sl\s*[:=]|stop[\s-]?loss\s*[:=]|signal\s*id\s*[:=])"
)


def is_configured() -> bool:
    sources = TELEGRAM_NEWS_SOURCE_CHANNELS or DEFAULT_NEWS_SOURCES
    # Telethon StringSession usually starts with "1"; reject placeholders.
    session_ok = bool(TELEGRAM_NEWS_SESSION) and len(TELEGRAM_NEWS_SESSION) > 50
    return bool(
        TELEGRAM_API_ID
        and TELEGRAM_API_HASH
        and session_ok
        and sources
        and TELEGRAM_NEWS_TARGET_CHANNEL
    )


def _parse_sources(raw: str) -> list[str]:
    out = []
    for part in (raw or DEFAULT_NEWS_SOURCES).split(","):
        u = part.strip().lstrip("@")
        if u:
            out.append(u)
    return out


def _target() -> str:
    t = TELEGRAM_NEWS_TARGET_CHANNEL.strip()
    if t.startswith("-") or t.lstrip("-").isdigit():
        return t
    return t if t.startswith("@") else f"@{t}"


def _allow_hour_slot() -> bool:
    global _hour_bucket, _hour_count
    bucket = datetime.utcnow().strftime("%Y%m%d%H")
    if _hour_bucket != bucket:
        _hour_bucket = bucket
        _hour_count = 0
    return _hour_count < MAX_PER_HOUR


def _bump_hour() -> None:
    global _hour_count, _last_publish_ts
    _hour_count += 1
    _last_publish_ts = time.time()


def _gap_ok() -> bool:
    if MIN_GAP_SEC <= 0:
        return True
    return (time.time() - _last_publish_ts) >= MIN_GAP_SEC


def _fingerprint(text: str) -> frozenset[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9$#]{3,}", (text or "").lower())
    stop = {
        "this", "that", "with", "from", "have", "will", "just", "about", "after",
        "analysis", "trading", "trend", "price", "market", "support", "resistance",
        "case", "bull", "bear", "hold", "lose", "break", "разбор", "анализ",
    }
    return frozenset(w for w in words if w not in stop)


def _is_near_duplicate(text: str) -> bool:
    global _recent_fingerprints
    now = time.time()
    _recent_fingerprints = [(ts, fp) for ts, fp in _recent_fingerprints if now - ts < 8 * 3600]
    fp = _fingerprint(text)
    tickers = {w for w in fp if w.startswith("$") or w.startswith("#")}
    for _, prev in _recent_fingerprints:
        prev_tickers = {w for w in prev if w.startswith("$") or w.startswith("#")}
        if tickers and prev_tickers and (tickers & prev_tickers):
            if len(fp & prev) >= 4:
                return True
        overlap = len(fp & prev)
        union = len(fp | prev) or 1
        if overlap / union >= 0.42 or overlap >= 6:
            return True
    return False


def _remember_fingerprint(text: str) -> None:
    _recent_fingerprints.append((time.time(), _fingerprint(text)))


def _plain_text(msg) -> str:
    return (getattr(msg, "message", None) or getattr(msg, "text", None) or "").strip()


def _strip_promo(text: str) -> str:
    text = _VIP_RE.sub("", text)
    text = re.sub(r"(?im)^.*(?:join\s+(?:our\s+)?vip|@\w*bot|vip\s*registration).*$", "", text)
    text = re.sub(r"(?im)^[➖\-_]{3,}.*$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _looks_like_noise(text: str) -> bool:
    text = _strip_promo(text)
    if len(text) < 60:
        return True
    low = text.lower()
    # Signal packs / VIP sales — не analysis
    if _SIGNAL_PACK.search(text) and not _STRONG_ANALYSIS.search(text):
        return True
    if re.search(r"(flash vip sale|offer valid|lifetime:|cornix|vip registration)", low):
        return True
    if re.search(
        r"(ref(erral)?\s*link|promo code|airdrop claim|claim bonus|first deposit|sponsored)",
        low,
    ):
        return True
    return False


def _is_analysis_shaped(text: str, has_media: bool) -> bool:
    if _STRONG_ANALYSIS.search(text) or _ANALYSIS_HINT.search(text):
        return True
    if has_media and re.search(r"(\$[A-Z]{2,10}|#[A-Z]{2,10})", text) and re.search(r"\d", text):
        return True
    return False


def _is_strong_analysis(text: str) -> bool:
    return bool(_STRONG_ANALYSIS.search(text))


async def _score_and_rewrite(text: str, source: str, *, has_chart: bool, strong: bool) -> dict | None:
    system = (
        "Ты редактор Nowicki News. Эталон — Fed. Russian Insiders / Bitcoin Bullets:\n"
        "график + $TICKER ANALYSIS / #TICKER Market Analysis + цена + тренд + "
        "Bull case / Bear case с уровнями.\n\n"
        "БЕРИ (score 7–10) если это разбор рынка/монеты с уровнями или сценариями.\n"
        "ОТКЛОНЯЙ: VIP-продажи, entry/leverage/TP-пакеты без анализа, мемы, рекламу, "
        "голые headlines без цифр.\n"
        f"График: {'да' if has_chart else 'нет'}. Сильный TA-формат: {'да' if strong else 'нет'}.\n"
        "Если берёшь — ПЕРЕВЕДИ на русский в том же стиле:\n"
        "headline «$TICKER — разбор», body 3–8 предложений "
        "(цена → структура → цели вверх → риски вниз → вывод).\n"
        "Без VIP/ботов/исходного канала, без «покупай сейчас».\n"
        "JSON: {\"keep\":bool,\"score\":1-10,\"headline\":str,\"body\":str,\"ticker\":str,\"reason\":str}"
    )
    try:
        return await ai_client.fast_json_completion(
            system=system,
            user_text=f"Источник: @{source}\n\n{_strip_promo(text)[:3500]}",
            max_tokens=520,
        )
    except Exception as e:
        print(f"[news_relay] AI fail: {e}", flush=True)
        return None


async def _download_chart(msg) -> bytes | None:
    try:
        if getattr(msg, "video", None):
            return None
        doc = getattr(msg, "document", None)
        if doc is not None:
            mime = getattr(doc, "mime_type", "") or ""
            if mime and not mime.startswith("image/"):
                return None
        if not getattr(msg, "photo", None) and doc is None and not getattr(msg, "media", None):
            return None
        data = await msg.download_media(file=bytes)
        if isinstance(data, (bytes, bytearray)) and len(data) > 1000:
            return bytes(data)
    except Exception as e:
        print(f"[news_relay] chart download: {e}", flush=True)
    return None


async def _handle_message(client, source: str, msg, *, target: str) -> None:
    msg_id = int(getattr(msg, "id", 0) or 0)
    if not msg_id:
        return
    key_ch = f"{_PROC_PREFIX}{source}"
    if db.is_message_processed(key_ch, msg_id):
        return

    text = _strip_promo(_plain_text(msg))
    has_media = bool(getattr(msg, "photo", None) or getattr(msg, "media", None))
    print(
        f"[news_relay] seen @{source}/{msg_id} chars={len(text)} media={has_media}",
        flush=True,
    )

    if not text or _looks_like_noise(text):
        db.mark_message_processed(key_ch, msg_id)
        print(f"[news_relay] noise skip @{source}/{msg_id}", flush=True)
        return

    analysis_shaped = _is_analysis_shaped(text, has_media)
    strong = _is_strong_analysis(text)

    # Не-analysis почти не берём (кроме очень сильных)
    if not analysis_shaped and not strong:
        db.mark_message_processed(key_ch, msg_id)
        print(f"[news_relay] not-analysis skip @{source}/{msg_id}", flush=True)
        return

    if not _allow_hour_slot():
        print(f"[news_relay] hour cap ({MAX_PER_HOUR}), skip @{source}/{msg_id}", flush=True)
        return
    if not _gap_ok():
        left = int(MIN_GAP_SEC - (time.time() - _last_publish_ts))
        print(f"[news_relay] gap {left}s left, skip @{source}/{msg_id}", flush=True)
        return
    if _is_near_duplicate(text):
        db.mark_message_processed(key_ch, msg_id)
        print(f"[news_relay] near-dup skip @{source}/{msg_id}", flush=True)
        return

    verdict = await _score_and_rewrite(
        text, source, has_chart=has_media and analysis_shaped, strong=strong
    )
    if not verdict or not isinstance(verdict, dict):
        return

    keep = bool(verdict.get("keep"))
    try:
        score = int(verdict.get("score") or 0)
    except (TypeError, ValueError):
        score = 0

    # Strong Fed/Bullets format: чуть мягче порог
    need = max(6, MIN_SCORE - 1) if strong else MIN_SCORE
    headline = (verdict.get("headline") or "").strip()
    body = (verdict.get("body") or "").strip()
    reason = (verdict.get("reason") or "").strip()
    ticker = (verdict.get("ticker") or "").strip().upper().lstrip("$#")

    # Для явного TA-формата не даём AI «зарезать» хороший пост слишком легко
    if strong and body and score >= 6:
        keep = True

    if not keep or score < need or not body:
        db.mark_message_processed(key_ch, msg_id)
        print(
            f"[news_relay] skip @{source}/{msg_id} score={score}/{need} "
            f"strong={strong} ({reason[:80]})",
            flush=True,
        )
        return

    if ticker and not headline.startswith("$"):
        headline = f"${ticker} — разбор"
    caption = f"<b>{headline}</b>\n\n{body}" if headline else body
    caption = _strip_promo(caption)[:1024]

    chart = await _download_chart(msg) if has_media else None
    try:
        if chart:
            bio = BytesIO(chart)
            bio.name = "chart.jpg"
            await client.send_file(
                target,
                file=bio,
                caption=caption,
                parse_mode="html",
                force_document=False,
            )
        else:
            long_post = (f"<b>{headline}</b>\n\n{body}" if headline else body)[:3900]
            await client.send_message(target, long_post, parse_mode="html", link_preview=False)
        _bump_hour()
        _remember_fingerprint(f"{headline}\n{body}\n{text[:500]}")
        db.mark_message_processed(key_ch, msg_id)
        print(
            f"[news_relay] published score={score} chart={bool(chart)} "
            f"from @{source}: {headline[:80]}",
            flush=True,
        )
    except Exception as e:
        print(f"[news_relay] publish fail @{source}/{msg_id}: {e}", flush=True)


async def _run_once() -> None:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    from telethon.tl.functions.channels import JoinChannelRequest

    sources = _parse_sources(TELEGRAM_NEWS_SOURCE_CHANNELS or DEFAULT_NEWS_SOURCES)
    target = _target()
    print(
        f"[news_relay] connect… sources={len(sources)} target={target} "
        f"mode=analysis min_score={MIN_SCORE} max/h={MAX_PER_HOUR} "
        f"gap={MIN_GAP_SEC}s lookback={STARTUP_LOOKBACK}",
        flush=True,
    )
    client = TelegramClient(
        StringSession(TELEGRAM_NEWS_SESSION),
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH,
    )
    source_by_id: dict[int, str] = {}

    @client.on(events.NewMessage(chats=sources))
    async def _on_message(event):
        chat = await event.get_chat()
        username = (getattr(chat, "username", "") or "").lstrip("@")
        if not username:
            username = source_by_id.get(int(getattr(chat, "id", 0) or 0), "")
        if not username:
            username = sources[0]
        try:
            await _handle_message(client, username, event.message, target=target)
        except Exception as e:
            print(f"[news_relay] handler error: {e}", flush=True)

    await client.start()
    me = await client.get_me()
    print(f"[news_relay] authorized as @{getattr(me, 'username', None) or me.id}", flush=True)

    for username in sources:
        try:
            ent = await client.get_entity(username)
            source_by_id[int(ent.id)] = username
            try:
                await client(JoinChannelRequest(ent))
            except Exception:
                pass
        except Exception as e:
            print(f"[news_relay] resolve @{username}: {e}", flush=True)

    if STARTUP_LOOKBACK > 0:
        for username in sources:
            try:
                recent = await client.get_messages(username, limit=STARTUP_LOOKBACK)
                for msg in reversed(list(recent or [])):
                    try:
                        await _handle_message(client, username, msg, target=target)
                    except Exception as e:
                        print(f"[news_relay] startup @{username}: {e}", flush=True)
                print(
                    f"[news_relay] startup lookback @{username}: {len(recent or [])}",
                    flush=True,
                )
            except Exception as e:
                print(f"[news_relay] cannot read @{username}: {e}", flush=True)
    else:
        print("[news_relay] startup lookback disabled — только live", flush=True)

    print(
        f"[news_relay] listening: {', '.join('@'+s for s in sources)} → {target}",
        flush=True,
    )
    try:
        await client.run_until_disconnected()
    finally:
        print("[news_relay] disconnected", flush=True)


async def run() -> None:
    if not is_configured():
        print(
            "[news_relay] не сконфигурирован "
            "(TELEGRAM_NEWS_SESSION / SOURCE_CHANNELS / TARGET_CHANNEL) — пропуск",
            flush=True,
        )
        return
    delay = 5
    while True:
        try:
            await _run_once()
            delay = 5
        except Exception as e:
            print(f"[news_relay] Упал: {e}", flush=True)
        print(f"[news_relay] Переподключение через {delay}с…", flush=True)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 120)
