"""
Стиль чатов для chat_engage: грузим живые сообщения → пишем «как они».

Сэмплы в БД (chat_style_samples). Генерация через OpenAI с few-shot из истории;
если ключа/сэмплов нет — вызывающая сторона использует шаблоны.
"""

from __future__ import annotations

import json
import os
import random
import re

import httpx

import database as db

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o").strip() or "gpt-4o"

# Чаты-«учителя» стиля (можно переопределить env CSV).
_DEFAULT_STYLE_CHATS = "BinanceRussianSpeaking,cryptoinside_chat"
STYLE_SOURCE_CHATS = [
    p.strip().lstrip("@")
    for p in (os.getenv("CHAT_STYLE_SOURCE_CHATS") or _DEFAULT_STYLE_CHATS).split(",")
    if p.strip()
]

_FETCH_PER_CHAT = int(os.getenv("CHAT_STYLE_FETCH_LIMIT", "120") or "120")
_MAX_SAMPLES_TOTAL = int(os.getenv("CHAT_STYLE_MAX_SAMPLES", "250") or "250")

_LINK_RE = re.compile(r"https?://|t\.me/|@\w{4,}", re.I)
_CYR_RE = re.compile(r"[а-яёА-ЯЁ]")
_WS_RE = re.compile(r"\s+")


def _clean_msg(text: str) -> str | None:
    if not text:
        return None
    t = _WS_RE.sub(" ", text).strip()
    if len(t) < 4 or len(t) > 160:
        return None
    if _LINK_RE.search(t):
        return None
    if t.count("\n") > 2:
        return None
    # Нужен живой разговорный текст, желательно с кириллицей
    if not _CYR_RE.search(t) and not re.search(r"[a-zA-Z]", t):
        return None
    # отсев явной рекламы/ботов
    low = t.lower()
    if any(x in low for x in ("подпиш", "реклам", "vip", "сигнал на", "бесплатн", "промокод")):
        return None
    return t


async def fetch_chat_history(client, chat: str, limit: int = _FETCH_PER_CHAT) -> list[str]:
    """Скачать свежие текстовые сообщения из чата (без ссылок/мусора)."""
    out: list[str] = []
    try:
        entity = await client.get_entity(chat)
        async for msg in client.iter_messages(entity, limit=max(limit * 3, 80)):
            if not msg or not getattr(msg, "message", None):
                continue
            if getattr(msg, "out", False):
                continue
            cleaned = _clean_msg(msg.message)
            if not cleaned:
                continue
            out.append(cleaned)
            if len(out) >= limit:
                break
    except Exception as e:
        print(f"[chat_style] fetch @{chat}: {e}")
    return out


async def ingest_style_chats(client, chats: list[str] | None = None) -> dict:
    """Загрузить историю из чатов-учителей в БД. Возвращает статистику."""
    targets = chats or STYLE_SOURCE_CHATS
    total = 0
    per: dict[str, int] = {}
    for chat in targets:
        samples = await fetch_chat_history(client, chat)
        n = db.replace_chat_style_samples(chat, samples)
        per[chat] = n
        total += n
        print(f"[chat_style] @{chat}: сохранено {n} фраз")
        await asyncio_sleep_brief()
    # обрезка глобального хвоста
    db.trim_chat_style_samples(_MAX_SAMPLES_TOTAL)
    return {"ok": True, "total": total, "per_chat": per, "chats": targets}


async def asyncio_sleep_brief():
    import asyncio
    await asyncio.sleep(random.uniform(0.4, 1.2))


def _few_shot_block(n: int = 18) -> str:
    rows = db.list_chat_style_samples(limit=80)
    if not rows:
        return ""
    picks = random.sample(rows, min(n, len(rows)))
    lines = [f"- {r['text']}" for r in picks]
    return "\n".join(lines)


async def compose_natural(kind: str, **ctx) -> str | None:
    """Сгенерировать фразу в стиле чатов. kind: greet | open | close_win."""
    if not OPENAI_API_KEY:
        return None
    shots = _few_shot_block()
    if not shots and kind != "greet":
        # без корпуса всё равно можно, но слабее
        pass

    if kind == "greet":
        task = (
            "Напиши ОДНО короткое сообщение в крипто-чат: просто поздороваться / "
            "спросить как дела / как рынок. Без монет, без цен, без ссылок, без эмодзи-спама."
        )
    elif kind == "open":
        coin = ctx.get("coin", "BTC")
        side_ru = ctx.get("side_ru", "лонг")
        entry = ctx.get("entry", "")
        task = (
            f"Напиши ОДНО короткое сообщение: ты только что зашёл в {side_ru} по {coin} "
            f"примерно от {entry}. Как обычный трейдер в чате, не реклама. "
            f"Можно спросить мнение. Без ссылок, без хештегов, без «сигнал/сетап/ТП/SL»."
        )
    elif kind == "close_win":
        coin = ctx.get("coin", "BTC")
        pnl = ctx.get("pnl_show", "2")
        task = (
            f"Напиши ОДНО короткое сообщение: закрыл {coin} в плюс примерно +{pnl}%. "
            f"Спокойно, по-человечески. Без ссылок и без рекламы."
        )
    else:
        return None

    system = (
        "Ты обычный русскоязычный трейдер в Telegram-чате. "
        "Пишешь коротко (до 90 символов), разговорно, иногда с опечатками или сленгом "
        "(ку, здарова, норм, имхо, лонг/шорт). "
        "Никогда не пиши что ты бот/AI. Не вставляй ссылки и @юзернеймы. "
        "Верни только текст сообщения, без кавычек."
    )
    user = task
    if shots:
        user = f"Как пишут в похожих чатах (примеры):\n{shots}\n\n{task}"

    payload = {
        "model": AI_MODEL,
        "max_tokens": 80,
        "temperature": 0.95,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
        text = (data["choices"][0]["message"]["content"] or "").strip().strip('"').strip("'")
        text = _WS_RE.sub(" ", text)
        if len(text) < 3 or len(text) > 180:
            return None
        if _LINK_RE.search(text):
            return None
        return text
    except Exception as e:
        print(f"[chat_style] compose {kind}: {e}")
        return None
