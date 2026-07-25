"""
Ретрансляция market-analysis (график + разбор монеты) → @nowicki_news.

Формат как у Fed. Russian Insiders: chart + $TICKER ANALYSIS + уровни/сценарии.
Не лента headline-новостей.

Env:
  TELEGRAM_NEWS_SESSION / TELEGRAM_NEWS_SOURCE_CHANNELS / TELEGRAM_NEWS_TARGET_CHANNEL
  NEWS_RELAY_MAX_PER_HOUR     default 4
  NEWS_RELAY_MIN_SCORE        default 8
  NEWS_RELAY_MIN_GAP_SEC      default 900 (15 мин)
  NEWS_RELAY_STARTUP_LOOKBACK default 0
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

MAX_PER_HOUR = int(os.getenv("NEWS_RELAY_MAX_PER_HOUR", "4") or "4")
MIN_SCORE = int(os.getenv("NEWS_RELAY_MIN_SCORE", "8") or "8")
MIN_GAP_SEC = int(os.getenv("NEWS_RELAY_MIN_GAP_SEC", "900") or "900")
STARTUP_LOOKBACK = int(os.getenv("NEWS_RELAY_STARTUP_LOOKBACK", "0") or "0")

# Analysis-first sources (Fed-style TA / coin outlook). Override via env.
DEFAULT_NEWS_SOURCES = (
    "FedRussianInsiders,"   # chart + $TICKER ANALYSIS (эталон формата)
    "rektchat,"             # BTC/alt cycle & watchlists
    "CryptoBusy,"           # market structure commentary
    "lookonchainchannel,"   # whale/flow charts that move coins
    "cryptoquant_official," # on-chain BTC positioning
    "glassnode,"            # supply / regime structure
    "WatcherGuru,"          # only strong market-moving (AI still filters hard)
    "TreeNewsFeed,"         # BBG/RTRS wires with price impact
    "wublockchainenglish,"  # Asia ETF/flows
    "the_block_crypto"      # institutional
)

_PROC_PREFIX = "news:"

_hour_bucket: str | None = None
_hour_count = 0
_last_publish_ts = 0.0
_recent_fingerprints: list[tuple[float, frozenset[str]]] = []

_VIP_RE = re.compile(
    r"(?im)(?:👉\s*)?(?:join\s+our\s+vip|vip\s*->|@\w*vip\w*|t\.me/\w*vip\w*).*$"
)
_ANALYSIS_HINT = re.compile(
    r"(?i)(\$[A-Z0-9]{2,15}\s+ANALYSIS|analysis\s*-{3,}|"
    r"trendline|higher\s+lows|support|resistance|"
    r"price\s+discovery|bull\s+trend|bear\s+trend|"
    r"trading\s+at\s+\$?\d|breaking\s+\$?\d|losing\s+\$?\d)"
)


def is_configured() -> bool:
    sources = TELEGRAM_NEWS_SOURCE_CHANNELS or DEFAULT_NEWS_SOURCES
    return bool(
        TELEGRAM_API_ID
        and TELEGRAM_API_HASH
        and TELEGRAM_NEWS_SESSION
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
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9$]{3,}", (text or "").lower())
    stop = {
        "this", "that", "with", "from", "have", "will", "just", "about", "after",
        "analysis", "trading", "trend", "price", "market", "support", "resistance",
        "разбор", "анализ", "уровень", "цена", "рынок", "если", "тогд",
    }
    return frozenset(w for w in words if w not in stop) 


def _is_near_duplicate(text: str) -> bool:
    global _recent_fingerprints
    now = time.time()
    _recent_fingerprints = [(ts, fp) for ts, fp in _recent_fingerprints if now - ts < 8 * 3600]
    fp = _fingerprint(text)
    tickers = {w for w in fp if w.startswith("$") or (w.isalpha() and w.upper() == w and 2 <= len(w) <= 6)}
    for _, prev in _recent_fingerprints:
        # same ticker recently = dup
        prev_tickers = {w for w in prev if w.startswith("$") or (len(w) <= 6 and w.isalpha())}
        if tickers and prev_tickers and (tickers & prev_tickers):
            overlap = len(fp & prev)
            if overlap >= 4:
                return True
        overlap = len(fp & prev)
        union = len(fp | prev) or 1
        if overlap / union >= 0.4 or overlap >= 6:
            return True
    return False


def _remember_fingerprint(text: str) -> None:
    _recent_fingerprints.append((time.time(), _fingerprint(text)))


def _plain_text(msg) -> str:
    return (getattr(msg, "message", None) or getattr(msg, "text", None) or "").strip()


def _strip_promo(text: str) -> str:
    text = _VIP_RE.sub("", text)
    text = re.sub(r"(?im)^.*(?:join our vip|@\w*bot).*$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _looks_like_noise(text: str) -> bool:
    text = _strip_promo(text)
    if len(text) < 70:
        return True
    low = text.lower()
    # Hard signal spam (entry/TP/SL packs), not scenario TA
    if re.search(r"\b(entry\s*[:=]|leverage\s*\d|liq(uidation)?\s*price)\b", low):
        return True
    if re.search(r"\b(tp\s*[1-3]\s*[:=]|take[\s-]?profit\s*[:=]|stop[\s-]?loss\s*[:=])\b", low):
        return True
    if re.search(
        r"(ref(erral)?\s*link|promo code|airdrop claim|claim bonus|first deposit|"
        r"sponsored|партн[её]р|сигнал(ы)?\s+vip)",
        low,
    ):
        return True
    # Pure headline fluff without levels/analysis
    if re.search(r"^\s*(just in|breaking|🚨)", low) and not _ANALYSIS_HINT.search(text):
        if not re.search(r"\b(etf|fed|sec|hack|exploit|outflow|inflow)\b", low):
            return True
    return False


def _is_analysis_shaped(text: str, has_media: bool) -> bool:
    if _ANALYSIS_HINT.search(text):
        return True
    if has_media and re.search(r"\$[A-Z]{2,10}", text) and re.search(r"\$?\d", text):
        return True
    return False


async def _score_and_rewrite(text: str, source: str, *, has_chart: bool) -> dict | None:
    """Prefer Fed-style coin TA; rewrite in Russian without VIP spam."""
    system = (
        "Ты редактор Nowicki News. Эталон формата — разбор монеты как у Fed. Russian Insiders:\n"
        "график + заголовок $TICKER ANALYSIS + цена сейчас + тренд + уровни вверх/вниз + короткий вывод.\n\n"
        "БЕРИ (score 8–10) если это КАЧЕСТВЕННЫЙ market analysis:\n"
        "• разбор конкретной монеты/BTC/ETH с уровнями (support/resistance/targets);\n"
        "• сценарии «если пробьёт X → Y», «если потеряет X → Z»;\n"
        "• структура тренда (higher lows, trendline, discovery mode) с цифрами;\n"
        "• сильный on-chain/flow outlook, который объясняет, куда может пойти цена.\n\n"
        "ОТКЛОНЯЙ:\n"
        "• голые headlines без уровней; мемы; VIP/реклама; сигналы entry/TP/SL пакетом;\n"
        "• новости про AI/политику без цены; дубликаты; пустой хайп без цифр.\n\n"
        f"У поста {'ЕСТЬ' if has_chart else 'НЕТ'} графика — при наличии графика повышай score для TA.\n"
        "Если берёшь — ПЕРЕВЕДИ и адаптируй на русском в том же стиле:\n"
        "headline вида «$TICKER — разбор» или «$TICKER ANALYSIS»,\n"
        "body 3–7 предложений: цена → тренд → цели вверх → риски вниз → короткий вывод.\n"
        "Без упоминания исходного канала, без VIP/ботов, без «покупай сейчас».\n"
        "JSON: {\"keep\":bool,\"score\":1-10,\"headline\":str,\"body\":str,\"ticker\":str,\"reason\":str}"
    )
    user = f"Источник: @{source}\n\n{_strip_promo(text)[:3500]}"
    try:
        return await ai_client.fast_json_completion(
            system=system,
            user_text=user,
            max_tokens=480,
        )
    except Exception as e:
        print(f"[news_relay] AI fail: {e}", flush=True)
        return None


async def _download_chart(msg) -> bytes | None:
    try:
        if not getattr(msg, "photo", None) and not getattr(msg, "media", None):
            return None
        # Prefer photo; skip huge videos/docs
        if getattr(msg, "video", None) or getattr(msg, "document", None):
            # allow image documents
            doc = getattr(msg, "document", None)
            mime = ""
            if doc is not None:
                mime = getattr(doc, "mime_type", "") or ""
            if mime and not mime.startswith("image/"):
                return None
            if getattr(msg, "video", None):
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
    if not text or _looks_like_noise(text):
        db.mark_message_processed(key_ch, msg_id)
        return

    # Soft prefer analysis shape from Fed-like sources; still allow strong wires via AI
    analysis_shaped = _is_analysis_shaped(text, has_media)

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

    verdict = await _score_and_rewrite(text, source, has_chart=has_media and analysis_shaped)
    if not verdict or not isinstance(verdict, dict):
        return

    keep = bool(verdict.get("keep"))
    try:
        score = int(verdict.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    # Non-analysis posts need a higher bar
    need = MIN_SCORE if analysis_shaped else max(MIN_SCORE, 9)
    headline = (verdict.get("headline") or "").strip()
    body = (verdict.get("body") or "").strip()
    reason = (verdict.get("reason") or "").strip()
    ticker = (verdict.get("ticker") or "").strip().upper()

    if not keep or score < need or not body:
        db.mark_message_processed(key_ch, msg_id)
        print(
            f"[news_relay] skip @{source}/{msg_id} score={score}/{need} "
            f"analysis={analysis_shaped} ({reason[:80]})",
            flush=True,
        )
        return

    if ticker and not headline.upper().startswith("$"):
        headline = f"${ticker} — разбор" if "разбор" not in headline.lower() else headline
    caption = f"<b>{headline}</b>\n\n{body}" if headline else body
    caption = _strip_promo(caption)[:1024]  # Telegram caption limit for photos

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

    sources = _parse_sources(TELEGRAM_NEWS_SOURCE_CHANNELS or DEFAULT_NEWS_SOURCES)
    target = _target()
    print(
        f"[news_relay] connect… sources={len(sources)} target={target} "
        f"mode=analysis min_score={MIN_SCORE} max/h={MAX_PER_HOUR} gap={MIN_GAP_SEC}s",
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
            from telethon.tl.functions.channels import JoinChannelRequest
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
                print(f"[news_relay] startup lookback @{username}: {len(recent or [])}", flush=True)
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
