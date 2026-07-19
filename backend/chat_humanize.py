"""
Humanize helpers for chat_engage (ideas from NexusTG / tg-agent-leadgen):
  jagged typing, multi-bubble split, light typo, PeerFlood cooldown.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import time
from io import BytesIO

PEER_FLOOD_COOLDOWN_SEC = float(os.getenv("CHAT_ENGAGE_PEER_FLOOD_SEC", "600") or "600")
IGNORE_PROB_LIGHT = float(os.getenv("CHAT_ENGAGE_IGNORE_LIGHT", "0.12") or "0.12")
IGNORE_PROB_DIRECT = float(os.getenv("CHAT_ENGAGE_IGNORE_DIRECT", "0.05") or "0.05")
TYPO_PROB = float(os.getenv("CHAT_ENGAGE_TYPO_PROB", "0.05") or "0.05")
MULTI_BUBBLE_PROB = float(os.getenv("CHAT_ENGAGE_MULTI_BUBBLE", "0.45") or "0.45")

_peer_flood_until = 0.0
_WS = re.compile(r"\s+")


def peer_flood_active() -> bool:
    return time.monotonic() < _peer_flood_until


def trip_peer_flood(seconds: float | None = None) -> None:
    global _peer_flood_until
    _peer_flood_until = time.monotonic() + float(seconds or PEER_FLOOD_COOLDOWN_SEC)
    print(f"[chat_humanize] PeerFlood cooldown {PEER_FLOOD_COOLDOWN_SEC:.0f}s")


def should_ignore(*, direct: bool, is_ask: bool) -> bool:
    """Иногда «занят» — как живой человек. На явный ask_source не игнорим."""
    if is_ask:
        return False
    p = IGNORE_PROB_DIRECT if direct else IGNORE_PROB_LIGHT
    return random.random() < p


def split_bubbles(text: str) -> list[str]:
    """Разбить ответ на 1–3 коротких пузыря (как в мессенджере)."""
    t = (text or "").strip()
    if not t:
        return []
    # явные переносы от LLM
    parts = [p.strip() for p in re.split(r"\n+", t) if p.strip()]
    if len(parts) == 1 and random.random() < MULTI_BUBBLE_PROB and len(t) > 35:
        # режем по предложению / запятой
        chunks = re.split(r"(?<=[.!?…])\s+|(?<=,)\s+", t)
        chunks = [_WS.sub(" ", c).strip(" ,") for c in chunks if c.strip()]
        if len(chunks) >= 2:
            parts = chunks[:3]
    out: list[str] = []
    for p in parts[:3]:
        p = _WS.sub(" ", p).strip()
        if 1 < len(p) <= 140:
            out.append(p)
    return out or [t[:140]]


def _make_typo(text: str) -> str | None:
    if len(text) < 8 or " " not in text:
        return None
    chars = list(text)
    # перестановка соседних букв в середине слова
    idxs = [i for i in range(1, len(chars) - 1) if chars[i].isalpha() and chars[i + 1].isalpha()]
    if not idxs:
        return None
    i = random.choice(idxs)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]
    typo = "".join(chars)
    return typo if typo != text else None


async def jagged_typing(client, entity, text: str, *, read_msg_id: int | None = None) -> None:
    """Read delay + typing bursts with pauses (NexusTG-style)."""
    try:
        if read_msg_id is not None:
            await asyncio.sleep(random.uniform(0.6, 2.2))
            await client.send_read_acknowledge(entity, max_id=read_msg_id)
    except Exception:
        pass

    # время «прочтения» входящего + набор
    remaining = max(1.2, len(text or "") * 0.06 + random.uniform(0.8, 2.8))
    if random.random() < 0.12:
        remaining += random.uniform(2.0, 6.0)

    while remaining > 0:
        burst = min(remaining, random.uniform(1.2, 3.2))
        try:
            async with client.action(entity, "typing"):
                await asyncio.sleep(burst)
        except Exception:
            await asyncio.sleep(burst)
        remaining -= burst
        if remaining > 0.4:
            await asyncio.sleep(random.uniform(0.35, 1.6))


async def send_human(
    client,
    entity,
    text: str,
    *,
    photo: bytes | None = None,
    reply_to: int | None = None,
    read_msg_id: int | None = None,
    allow_split: bool = True,
) -> None:
    """Full human send: jagged typing, optional multi-bubble / typo, flood handling."""
    from telethon.errors import FloodWaitError, PeerFloodError

    if peer_flood_active():
        raise RuntimeError("peer_flood_cooldown")

    bubbles = [text] if photo or not allow_split else split_bubbles(text)
    if not bubbles and not photo:
        return

    first_reply_to = reply_to
    for i, bubble in enumerate(bubbles):
        await jagged_typing(
            client, entity, bubble,
            read_msg_id=read_msg_id if i == 0 else None,
        )

        # редкая опечатка → потом исправление
        typo = _make_typo(bubble) if (not photo and random.random() < TYPO_PROB) else None

        async def _send(payload: str, *, use_photo: bool = False):
            if use_photo and photo:
                bio = BytesIO(photo)
                bio.name = "pnl.png"
                await client.send_file(
                    entity, bio, caption=payload or None,
                    force_document=False, reply_to=first_reply_to if i == 0 else None,
                )
            else:
                await client.send_message(
                    entity, payload,
                    reply_to=first_reply_to if i == 0 else None,
                )

        try:
            if typo:
                await _send(typo, use_photo=False)
                await jagged_typing(client, entity, bubble)
                await _send(f"*{bubble}")
            else:
                await _send(bubble, use_photo=bool(photo) and i == 0)
                # если фото — только в первом пузыре
                photo = None
        except PeerFloodError:
            trip_peer_flood()
            raise
        except FloodWaitError as e:
            wait = int(getattr(e, "seconds", 5) or 5) + random.uniform(2, 8)
            print(f"[chat_humanize] FloodWait {wait:.0f}s")
            await asyncio.sleep(wait)
            await _send(bubble, use_photo=False)

        if i < len(bubbles) - 1:
            await asyncio.sleep(random.uniform(0.8, 2.5))
