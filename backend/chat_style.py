"""
Стиль чатов для chat_engage: грузим живые сообщения → пишем «как они».

Сэмплы в БД (chat_style_samples). Генерация через OpenAI с few-shot из истории;
если ключа/сэмплов нет — вызывающая сторона использует шаблоны.
"""

from __future__ import annotations

import asyncio
import os
import random
import re

import httpx

import anthropic
import database as db

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Для чата — лёгкая модель (выше лимиты); тяжёлый gpt-4o часто упирается в 429 от ingest
AI_MODEL = (
    os.getenv("CHAT_ENGAGE_AI_MODEL")
    or os.getenv("AI_MODEL_CHAT")
    or "gpt-4o-mini"
).strip() or "gpt-4o-mini"

# Модель Claude для максимальной живости ответов
CLAUDE_MODEL = "claude-3-5-sonnet-20240620"

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

# Типичные AI-штампы — регенерация / отсев
_AI_TELL_RE = re.compile(
    r"(абсолютно|безусловно|в\s+сегодняшнем\s+мире|давайте\s+разбер|"
    r"как\s+(ии|ai|бот|нейросеть)|я\s+(языковая|искусственн)|"
    r"в\s+качестве\s+ии|оптимальн\w*\s+решени|важно\s+отметить|"
    r"подвед[её]м\s+итог|в\s+заключение|разумеется)",
    re.IGNORECASE,
)

_CRYPTO_RE = re.compile(
    r"\b(btc|eth|sol|long|short|лонг|шорт|ликвидац|фьюч|леверидж|"
    r"маржа|памп|дамп|альт|биток|эфир|вход|выход|тейк|стоп|"
    r"рынок|тренд|график|свеч)\b",
    re.IGNORECASE,
)

_SPAM_RE = re.compile(
    r"(подпиш|реклам|vip\b|сигнал\s+на|бесплатн|промокод|заработок\s+\d|"
    r"пиши\s+в\s+лс|гарант\w*\s+доход)",
    re.IGNORECASE,
)

_CASUAL_FALLBACKS = [
    "норм, ты как?",
    "да ничего особого",
    "ку, норм",
    "пока тихо относительно",
]

_CRYPTO_FALLBACKS = [
    "хз, смотрю пока",
    "ну рынок странный сегодня",
    "имхо рано ещё",
    "осторожно там",
    "посмотрим",
]

_MONEY_FALLBACKS = [
    "сканер гоняю + смотрю поток, без магии",
    "ну сетапы по сканеру, иногда в тг кидают",
    "просто фильтрую шум, не сигнальный чат всякий",
    "есть сканер, плюс свой канал — оттуда идеи",
]

_GREET_RE = re.compile(
    r"^(ку|привет|здаров|хай|йо|че как|чё как|как дела|ау+|йоу)\b",
    re.I,
)
_MONEY_RE = re.compile(
    r"(деньг|поднима|заработ|плюс|сделк|как\s*\?|как\s+ты\s+|откуда|где\s+бер|"
    r"как\s+(вход|торгу|бер))",
    re.I,
)


def fallback_reply(kind: str, incoming: str = "") -> str:
    """Умный fallback без LLM — чтобы при 429 не отвечать тупым «ага»."""
    t = (incoming or "").strip()
    if _GREET_RE.search(t) or re.search(r"как дела|че как|чё как", t, re.I):
        return random.choice([
            "норм, ты как?",
            "да ничего, потихоньку",
            "ку, норм)",
            "хай, пока ок",
        ])
    if kind == "reply_crypto" or _CRYPTO_RE.search(t):
        if _MONEY_RE.search(t):
            return random.choice(_MONEY_FALLBACKS)
        return random.choice(_CRYPTO_FALLBACKS)
    if _MONEY_RE.search(t):
        return random.choice(_MONEY_FALLBACKS)
    if "?" in t:
        return random.choice([
            "хз если честно",
            "ну смотря как смотреть",
            "короче по ситуации",
            "могу попозже скинуть как делаю",
        ])
    return random.choice(_CASUAL_FALLBACKS)


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
    if not _CYR_RE.search(t) and not re.search(r"[a-zA-Z]", t):
        return None
    low = t.lower()
    if any(x in low for x in ("подпиш", "реклам", "vip", "сигнал на", "бесплатн", "промокод")):
        return None
    return t


def passes_human_filter(text: str, *, allow_links: bool = False) -> bool:
    """Откинуть AI-штампы / слишком длинное / ссылки (если не промо)."""
    if not text:
        return False
    t = _WS_RE.sub(" ", text).strip()
    if len(t) < 2 or len(t) > 140:
        return False
    if not allow_links and _LINK_RE.search(t):
        return False
    if _AI_TELL_RE.search(t):
        return False
    return True


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


def heuristic_intent(text: str, *, ask_re) -> str:
    """Быстрая классификация без LLM: ignore | ask_source | smalltalk | crypto_chat."""
    t = (text or "").strip()
    if not t or len(t) > 280:
        return "ignore"
    if _SPAM_RE.search(t) or (_LINK_RE.search(t) and "http" in t.lower()):
        return "ignore"
    if ask_re.search(t):
        return "ask_source"
    if _CRYPTO_RE.search(t):
        return "crypto_chat"
    if len(t) <= 120 and (
        "?" in t
        or re.search(r"^(ку|привет|здаров|хай|йо|как дела|чо как|ну как)", t, re.I)
        or _CYR_RE.search(t)
    ):
        return "smalltalk"
    return "ignore"


async def classify_intent(text: str, *, ask_re) -> str:
    """ignore | smalltalk | crypto_chat | ask_source."""
    base = heuristic_intent(text, ask_re=ask_re)
    if base in ("ask_source", "ignore") or not OPENAI_API_KEY:
        return base
    if len(text) < 40:
        return base
    try:
        payload = {
            "model": AI_MODEL,
            "max_tokens": 12,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Классифицируй сообщение из крипто-Telegram чата. "
                        "Ответь ОДНИМ словом: ignore | smalltalk | crypto_chat | ask_source. "
                        "ask_source — спрашивают откуда сигналы/канал/сайт. "
                        "ignore — спам, реклама, оффтоп не к разговору, команды ботов."
                    ),
                },
                {"role": "user", "content": text[:400]},
            ],
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            resp.raise_for_status()
            raw = (resp.json()["choices"][0]["message"]["content"] or "").strip().lower()
        for label in ("ask_source", "crypto_chat", "smalltalk", "ignore"):
            if label in raw:
                return label
    except Exception as e:
        print(f"[chat_style] classify: {e}")
    return base


_OARS_FALLBACKS = {
    1: [
        "а ты сам откуда обычно смотришь?",
        "ну хз, а тебе что заходит больше?",
        "а ты давно в теме?",
    ],
    2: [
        "ага понял, сам через кучу шума пробираюсь",
        "ну да, везде одно и то же льют",
        "жиза, сам устал от шлака",
    ],
    3: [
        "я просто сканер гоняю + канал, без магии",
        "ну у меня свой поток, не сигнальный чат всякий",
        "смотрю по сканеру, иногда кидают в тг",
    ],
}


def memory_block(rows: list | None) -> str:
    if not rows:
        return ""
    lines = []
    for r in rows[-8:]:
        role = "я" if r.get("role") == "assistant" else "он"
        lines.append(f"{role}: {r.get('text', '')}")
    return "Недавний диалог:\n" + "\n".join(lines)


def oars_fallback(step: int) -> str:
    return random.choice(_OARS_FALLBACKS.get(step, _OARS_FALLBACKS[1]))


def _normalize_reply(text: str, *, keep_newlines: bool = False) -> str:
    t = (text or "").strip().strip('"').strip("'")
    if keep_newlines:
        lines = [_WS_RE.sub(" ", ln).strip() for ln in t.splitlines()]
        t = "\n".join(ln for ln in lines if ln)
    else:
        t = _WS_RE.sub(" ", t)
    return t


async def _generate_claude(system: str, user: str, max_tokens: int = 120) -> str | None:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, max_retries=2)
        resp = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            temperature=0.9,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    except Exception as e:
        print(f"[chat_style] claude fail: {e}")
        return None


async def compose_natural(kind: str, **ctx) -> str | None:
    """Сгенерировать фразу. kinds: greet|open|close_win|reply_casual|reply_crypto|oars."""
    if not ANTHROPIC_API_KEY and not OPENAI_API_KEY:
        return None
    shots = _few_shot_block()
    incoming = (ctx.get("incoming") or "").strip()[:300]
    mem = memory_block(ctx.get("memory"))
    keep_nl = kind in ("reply_casual", "reply_crypto", "oars")

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
    elif kind == "reply_casual":
        task = (
            "Ответь на сообщение коротко и ПО СМЫСЛУ (не «ага/понял/ок»). "
            "Если спросили как дела — скажи как ты и спроси обратно. "
            "Если спросили как зарабатываешь/откуда сделки — мягко про сканер/поток, без ссылок. "
            "Можно 1–2 короткие реплики через перевод строки.\n"
            f"{mem}\nСообщение:\n{incoming or '(пусто)'}"
        )
    elif kind == "reply_crypto":
        task = (
            "Ответь как обычный трейдер ПО СМЫСЛУ на реплику. Не односложное «ага». "
            "Если спрашивают как берёшь плюс/сделки — скажи что смотришь сканер/сетапы. "
            "1–2 коротких пузыря. Без «входи сюда», без ссылок.\n"
            f"{mem}\nСообщение:\n{incoming or '(пусто)'}"
        )
    elif kind == "oars":
        step = int(ctx.get("oars_step") or 1)
        goals = {
            1: "Шаг Open: задай короткий живой вопрос, покажи интерес. БЕЗ ссылок и рекламы.",
            2: "Шаг Affirm: коротко согласись/посочувствуй. БЕЗ решений и ссылок.",
            3: "Шаг Reflect: мягко намекни что смотришь свой поток/сканер, без ссылок и без «купи».",
            4: "Шаг Summary: можно мягко дать сайт nowicki.trade и канал — коротко, по-свойски.",
        }
        task = (
            f"OARS шаг {step}/4. {goals.get(step, goals[1])}\n"
            f"{mem}\nСообщение собеседника:\n{incoming or '(пусто)'}"
        )
    else:
        return None

    # Динамическое настроение (влияет на многословность и стиль)
    states = [
        "ты сейчас занят, отвечаешь на бегу, очень коротко",
        "ты немного раздражён тупыми вопросами, отвечаешь односложно или с сарказмом",
        "у тебя хорошее настроение, можешь ответить чуть подробнее",
        "ты уставший, хочешь спать, отвечаешь лениво",
        "ты обычный, просто листаешь ленту"
    ]
    current_state = random.choice(states)

    system = (
        "Ты обычный русскоязычный парень в Telegram-чате (не гуру). "
        f"Твоё состояние сейчас: {current_state}. "
        "Пишешь разговорно, сленг (ку, норм, имхо, лол, хз, бро, ля, капец). "
        "Пиши все с маленькой буквы (как делают в мессенджерах). Точки в конце предложений не ставь. "
        "Никогда не пиши что ты бот/AI. Без канцелярита и AI-штампов. "
        "Если две мысли — раздели перевод строки. Верни только текст."
    )
    if kind != "oars" or int(ctx.get("oars_step") or 1) < 4:
        system += " Не вставляй ссылки и @юзернеймы."

    user = task
    if shots:
        user = f"Примеры из твоего чата (как пишут другие пацаны):\n{shots}\n\nТвоя задача:\n{task}"

    allow_links = kind == "oars" and int(ctx.get("oars_step") or 1) >= 4

    for _attempt in range(3):
        try:
            if ANTHROPIC_API_KEY:
                # Пытаемся сначала Клодом
                text = await _generate_claude(system, user, max_tokens=120)
            else:
                # Fallback на OpenAI
                payload = {
                    "model": AI_MODEL,
                    "max_tokens": 120,
                    "temperature": 0.95,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                }
                async with httpx.AsyncClient(timeout=25) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    )
                    if resp.status_code == 429:
                        wait = 2.0 * (_attempt + 1)
                        print(f"[chat_style] compose {kind}: 429, retry in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                text = data["choices"][0]["message"]["content"] or ""

            if not text:
                continue

            text = _normalize_reply(text, keep_newlines=keep_nl)
            
            ok = True
            for part in (text.splitlines() or [text]):
                if part and not passes_human_filter(part, allow_links=allow_links):
                    ok = False
                    break
            if ok and text:
                return text
        except Exception as e:
            print(f"[chat_style] compose {kind}: {e}")
            await asyncio.sleep(1.0 * (_attempt + 1))
    return None
