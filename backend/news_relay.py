"""
Ретрансляция рыночной картины / outlook из EN TG-источников → @nowicki_news.

Отдельная Telethon-сессия (TELEGRAM_NEWS_SESSION), не смешивать с сигнальным ingest.

Env:
  TELEGRAM_API_ID / TELEGRAM_API_HASH
  TELEGRAM_NEWS_SESSION          — StringSession новостного аккаунта (@garadaw)
  TELEGRAM_NEWS_SOURCE_CHANNELS  — CSV usernames источников (без @)
  TELEGRAM_NEWS_TARGET_CHANNEL   — username целевого канала (nowicki_news)
  NEWS_RELAY_MAX_PER_HOUR        — лимит постов (default 8)
  NEWS_RELAY_MIN_SCORE           — порог AI 1–10 (default 7)
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime

import ai_client
import database as db

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_NEWS_SESSION = os.getenv("TELEGRAM_NEWS_SESSION", "").strip()
TELEGRAM_NEWS_SOURCE_CHANNELS = os.getenv("TELEGRAM_NEWS_SOURCE_CHANNELS", "").strip()
TELEGRAM_NEWS_TARGET_CHANNEL = os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL", "").strip()

MAX_PER_HOUR = int(os.getenv("NEWS_RELAY_MAX_PER_HOUR", "8") or "8")
MIN_SCORE = int(os.getenv("NEWS_RELAY_MIN_SCORE", "7") or "7")
STARTUP_LOOKBACK = int(os.getenv("NEWS_RELAY_STARTUP_LOOKBACK", "8") or "8")

# Top sources: TGStat citation/reach among quality market news+outlook (not exchange/airdrop spam).
# Override via TELEGRAM_NEWS_SOURCE_CHANNELS.
DEFAULT_NEWS_SOURCES = (
    "WatcherGuru,"          # TGStat CI~1630, ~626k — EN breaking crypto/macro
    "headlines,"            # TGStat CI~930, ~400k — Crypto Headlines wire
    "cointelegraph,"        # TGStat CI~580, ~346k — markets & Web3 news
    "TreeNewsFeed,"         # BBG/RTRS-style market-moving wires
    "wublockchainenglish,"  # Asia ETF/flows / China crypto news
    "the_block_crypto,"     # institutional / The Block
    "rektchat,"             # BTC cycle + alt watchlists (outlook)
    "cryptoquant_official," # on-chain BTC positioning
    "lookonchainchannel,"   # whales / flows that move coins
    "glassnode"             # on-chain structure / BTC supply dynamics
)

# Prefixed so signal ingest processed_messages don't collide.
_PROC_PREFIX = "news:"

_hour_bucket: str | None = None
_hour_count = 0


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
    if _hour_count >= MAX_PER_HOUR:
        return False
    return True


def _bump_hour() -> None:
    global _hour_count
    _hour_count += 1


def _plain_text(msg) -> str:
    text = (getattr(msg, "message", None) or getattr(msg, "text", None) or "").strip()
    return text


def _looks_like_noise(text: str) -> bool:
    if len(text) < 60:
        return True
    low = text.lower()
    # Чистые trade-сигналы (entry/TP/SL), не рыночный outlook
    if re.search(r"\b(entry|leverage|liq(uidation)?\s*price|маржин)\b", low):
        return True
    if re.search(r"\b(tp\s*[1-3]|take[\s-]?profit|stop[\s-]?loss|\bsl\b)\b", low) and re.search(
        r"\b(entry|long|short)\b", low
    ):
        return True
    if re.search(r"\$?\d[\d,]*(?:\.\d+)?\s*[-–]\s*\$?\d", text) and re.search(r"\btp\s*\d\b", low):
        return True
    if re.search(r"(ref(erral)?\s*link|promo code|airdrop claim|dm me for|сигнал(ы)?\s+vip)", low):
        return True
    return False


async def _score_and_rewrite(text: str, source: str) -> dict | None:
    """AI: market outlook / narratives; translate & rewrite in Russian."""
    system = (
        "Ты редактор канала Nowicki News. Из EN-источника отбери полезный рыночный контент.\n"
        "БЕРИ (высокий score): картина рынка; что ждать от Bitcoin/ETH; доминирующие нарративы; "
        "какие сектора/монеты могут расти и ПОЧЕМУ; on-chain/ETF/flows; макро (ставки, ликвидность); "
        "циклы/позиционирование; крупные новости, которые двигают рынок.\n"
        "ОТКЛОНЯЙ: торговые сигналы с entry/TP/SL; рефералки/реклама; пустой хайп без факта; "
        "мемы; дубликаты; узкий проектный PR без рыночного эффекта; «GM».\n"
        "Если берёшь — ПЕРЕВЕДИ и перепиши на русском: ясно, коротко, нейтрально. "
        "2–6 предложений. Можно 1–2 уместных эмодзи максимум. "
        "Не упоминай исходный канал. Не давай прямых инструкций «покупай/продавай». "
        "Можно писать сценарии («если удержит уровень…», «вероятна коррекция…»).\n"
        "JSON: {\"keep\":bool,\"score\":1-10,\"headline\":str,\"body\":str,\"reason\":str}"
    )
    user = f"Источник: @{source}\n\n{text[:3500]}"
    try:
        parsed = await ai_client.fast_json_completion(
            system=system,
            user_text=user,
            max_tokens=420,
        )
    except Exception as e:
        print(f"[news_relay] AI fail: {e}", flush=True)
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


async def _handle_message(client, source: str, msg, *, target: str) -> None:
    msg_id = int(getattr(msg, "id", 0) or 0)
    if not msg_id:
        return
    key_ch = f"{_PROC_PREFIX}{source}"
    if db.is_message_processed(key_ch, msg_id):
        return

    text = _plain_text(msg)
    if not text or _looks_like_noise(text):
        db.mark_message_processed(key_ch, msg_id)
        return

    if not _allow_hour_slot():
        print(f"[news_relay] hour cap ({MAX_PER_HOUR}), skip @{source}/{msg_id}", flush=True)
        return

    verdict = await _score_and_rewrite(text, source)
    if not verdict:
        return

    keep = bool(verdict.get("keep"))
    try:
        score = int(verdict.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    headline = (verdict.get("headline") or "").strip()
    body = (verdict.get("body") or "").strip()
    reason = (verdict.get("reason") or "").strip()

    if not keep or score < MIN_SCORE or not body:
        db.mark_message_processed(key_ch, msg_id)
        print(
            f"[news_relay] skip @{source}/{msg_id} score={score} keep={keep} ({reason[:80]})",
            flush=True,
        )
        return

    post = f"<b>{headline}</b>\n\n{body}" if headline else body
    # Telethon HTML subset
    post = post[:3900]
    try:
        await client.send_message(target, post, parse_mode="html", link_preview=False)
        _bump_hour()
        db.mark_message_processed(key_ch, msg_id)
        print(f"[news_relay] published score={score} from @{source}: {headline[:80]}", flush=True)
    except Exception as e:
        print(f"[news_relay] publish fail @{source}/{msg_id}: {e}", flush=True)


async def _run_once() -> None:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    sources = _parse_sources(TELEGRAM_NEWS_SOURCE_CHANNELS or DEFAULT_NEWS_SOURCES)
    target = _target()
    print(
        f"[news_relay] connect… sources={len(sources)} target={target} "
        f"session_len={len(TELEGRAM_NEWS_SESSION)}",
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
    print(
        f"[news_relay] authorized as @{getattr(me, 'username', None) or me.id}",
        flush=True,
    )

    # Map channel ids → configured usernames (some chats return username=None).
    for username in sources:
        try:
            ent = await client.get_entity(username)
            source_by_id[int(ent.id)] = username
        except Exception as e:
            print(f"[news_relay] resolve @{username}: {e}", flush=True)

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
