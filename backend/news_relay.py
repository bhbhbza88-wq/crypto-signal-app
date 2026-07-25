"""
Ретрансляция лучших crypto-новостей из TG-источников → наш новостной канал.

Отдельная Telethon-сессия (TELEGRAM_NEWS_SESSION), не смешивать с сигнальным ingest.

Env:
  TELEGRAM_API_ID / TELEGRAM_API_HASH
  TELEGRAM_NEWS_SESSION          — StringSession новостного аккаунта
  TELEGRAM_NEWS_SOURCE_CHANNELS  — CSV usernames источников (без @)
  TELEGRAM_NEWS_TARGET_CHANNEL   — username или @username целевого канала
  NEWS_RELAY_MAX_PER_HOUR        — лимит постов (default 6)
  NEWS_RELAY_MIN_SCORE           — порог AI 1–10 (default 7)
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta

import ai_client
import database as db

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_NEWS_SESSION = os.getenv("TELEGRAM_NEWS_SESSION", "").strip()
TELEGRAM_NEWS_SOURCE_CHANNELS = os.getenv("TELEGRAM_NEWS_SOURCE_CHANNELS", "").strip()
TELEGRAM_NEWS_TARGET_CHANNEL = os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL", "").strip()

MAX_PER_HOUR = int(os.getenv("NEWS_RELAY_MAX_PER_HOUR", "6") or "6")
MIN_SCORE = int(os.getenv("NEWS_RELAY_MIN_SCORE", "7") or "7")
STARTUP_LOOKBACK = int(os.getenv("NEWS_RELAY_STARTUP_LOOKBACK", "8") or "8")

# Prefixed so signal ingest processed_messages don't collide.
_PROC_PREFIX = "news:"

_hour_bucket: str | None = None
_hour_count = 0


def is_configured() -> bool:
    return bool(
        TELEGRAM_API_ID
        and TELEGRAM_API_HASH
        and TELEGRAM_NEWS_SESSION
        and TELEGRAM_NEWS_SOURCE_CHANNELS
        and TELEGRAM_NEWS_TARGET_CHANNEL
    )


def _parse_sources(raw: str) -> list[str]:
    out = []
    for part in raw.split(","):
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
    if len(text) < 80:
        return True
    low = text.lower()
    # Сигналы / трейдинг-коллы — не новости
    if re.search(r"\b(long|short|entry|tp\s*\d|sl\b|leverage|сигнал)\b", low):
        return True
    if re.search(r"\$?\d[\d,]*(?:\.\d+)?\s*[-–]\s*\$?\d", text) and "tp" in low:
        return True
    return False


async def _score_and_rewrite(text: str, source: str) -> dict | None:
    """AI: keep only high-value market news; rewrite cleanly in Russian."""
    system = (
        "Ты редактор крипто-новостного канала. Оцени пост источника.\n"
        "Бери ТОЛЬКО важные рыночные новости: регуляторика, крупные листинги/делистинги, "
        "ETF, хаки/эксплойты с ущербом, макровлияние на crypto, крупные M&A, "
        "заявления SEC/Fed/крупных банков/бирж, on-chain события с реальным эффектом.\n"
        "ОТКЛОНЯЙ: сигналы/трейдинг, прайсинговые спам-посты, мем-шутки без факта, "
        "рекламу курсов/рефералок, дубликаты слухов без источника, «GM» и мотивацию.\n"
        "Если берёшь — перепиши кратко и нейтрально на русском, 2–5 предложений, "
        "без эмодзи-спама, без упоминания исходного канала, без призывов к сделкам.\n"
        "JSON: {\"keep\":bool,\"score\":1-10,\"headline\":str,\"body\":str,\"reason\":str}"
    )
    user = f"Источник: @{source}\n\n{text[:3500]}"
    try:
        parsed = await ai_client.fast_json_completion(
            system=system,
            user_text=user,
            max_tokens=320,
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

    sources = _parse_sources(TELEGRAM_NEWS_SOURCE_CHANNELS)
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

    @client.on(events.NewMessage(chats=sources))
    async def _on_message(event):
        chat = await event.get_chat()
        username = (getattr(chat, "username", "") or "").lstrip("@") or sources[0]
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
