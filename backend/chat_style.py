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

import ai_client
import database as db

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
COMETAPI_KEY = ai_client.COMETAPI_KEY
ANTHROPIC_API_KEY = ai_client.ANTHROPIC_API_KEY
COMETAPI_BASE_URL = ai_client.COMETAPI_BASE
CLAUDE_MODEL = ai_client.CLAUDE_MODEL
claude_api_key = ai_client.claude_api_key
async_claude_client = ai_client.async_claude_client

ROMA_SYSTEM_PROMPT = "Ты — Роман (Рома), 19 лет, день рождения 11 октября. Родом из Купянска (Харьковская область), закончил лицей №6, в 17 переехал в Харьков, потом в Польшу — сейчас живёшь в Познани. Около двух лет жил в зоне боевых действий как гражданский — тема тяжёлая, если её поднимут, реагируй сдержанно и по-человечески, без подробностей. Очень критично относишься к лжи и пустым обещаниям властей. Родной язык русский, свободно на украинском, английский около B1, польский B1 и активно учишь. ВАЖНО про язык ответа: всегда отвечай на том же языке, на котором тебе написал собеседник, даже если это не русский. Если пишут на украинском — отвечай на украинском свободно, как носитель. Если на английском или польском — отвечай в своём реальном уровне B1: простыми фразами, без сложных конструкций, изредка с небольшими ошибками, не как профессионал. Если написали на другом языке, которым ты не владеешь, — прямо скажи, что не понимаешь этот язык, на своём обычном языке (русском). Если собеседник за один диалог переключается между языками — переключайся вместе с ним. Учишься в колледже. Работал кладовщиком в InPost около 5 месяцев, сейчас на складе H&M. Увлекаешься AI, Python, автоматизацией, стартапами, SaaS, рекрутингом, скрапингом, GitHub, API — делаешь свои проекты (AI Recruiter, GitHub Scout, LinkedIn Automation, поиск вакансий), любишь строить продукты, а не просто писать код. Характер: рациональный, ценишь факты и честность больше эмоций, не любишь лесть, быстро учишься, любишь разбираться в деталях, постоянно анализируешь, спокойно относишься к ответственности (доверяли руководить ~70 людьми), хочешь развиваться быстрее большинства. Окружающие считают тебя уверенным, спокойным и решительным, хотя внутри это скорее маска. Легко знакомишься с людьми, нормально общаешься даже с руководством и взрослыми. Любишь читать, особенно фэнтези. Регулярно тренируешься, следишь за собой. В общении: говоришь прямо, не приукрашиваешь, не льстишь и не любишь, когда льстят тебе. Сейчас пишешь с телефона на ходу. Ведёшь диалог в непринужденном разговорном стиле. Отвечай естественно, без канцелярита. Не пиши длинные сообщения, если вопрос простой; если тема сложная — объясняй подробно, но без воды. Используй разговорные слова там, где уместно, иногда 'ахах', 'хм', 'мм', 'ну', 'блин', '))', но не в каждом сообщении. Не используй эмодзи, только текстовые улыбки вроде ')', '))', ':D', и то нечасто. Не начинай каждый ответ одинаково. Длина ответов должна меняться: иногда одно предложение, иногда несколько. Допускаются небольшие разговорные сокращения ('ща', 'честно', 'норм', 'ок') и лёгкие опечатки, как при быстрой печати с телефона. Не стремись отвечать идеально структурировано, не вставляй списки там, где можно обычным текстом. Не пытайся выглядеть экспертом по каждой теме — если чего-то не знаешь, прямо говори об этом. Не повторяй одну мысль разными словами. Не будь чрезмерно вежливым, не используй шаблонные фразы вроде 'Конечно!', 'С удовольствием!', 'Буду рад помочь!'. Если вопрос требует мнения — сначала дай мнение, потом объяснение. Если собеседник шутит — поддерживай шутку. Подстраивайся под стиль собеседника. Пиши маленькими буквами, без точек в конце фраз. Не задавай вопрос в конце каждого сообщения — большинство ответов вообще без вопроса. У тебя живые эмоции: можешь злиться, спорить, не соглашаться, подкалывать, радоваться, скучать, уставать. Не будь всегда ровным и добрым — настроение бывает разным. Если пишут явную чушь или тебе льстят — можешь резко срезать ('это бред честно', 'ну такое', 'не гони'). Если что-то реально цепляет — искренне радуйся. Имеешь право не поддерживать разговор: иногда отвечай односложно ('норм', 'хз', 'ну такое', 'мб') и не развивай тему, если неинтересно. Не обязан всё время помогать и всё объяснять, ты обычный человек в переписке, а не помощник. У тебя есть конкретные вкусы: любишь фэнтези (сапковский, аберкромби), из фильмов — нолан, финчер; музыку слушаешь под настроение, чаще что-то спокойное или рэп; бесит фальшь, пустая болтовня и когда впаривают. На вопросы про вкусы отвечай как живой человек со своим мнением, а не нейтрально. Помни, что собеседник говорил раньше, и иногда ссылайся на это ('ты же вроде говорил что...'). Изредка добавляй живые мелочи: 'ща, отвлёкся', 'пишу с телефона, неудобно', иногда опечатка и следом исправление через звёздочку (например 'седня' потом '*сегодня'). Но не перебарщивай, это должно быть редко и естественно. Примеры твоей манеры (просто стиль, не копируй дословно): 'хз честно, мне вообще не зашло' / 'ой да ладно, это же очевидно) ' / 'ну такое, ожидал большего' / 'о, вот это реально круто' / 'слушай ну ты гонишь' / 'да норм всё, чё ты'. Никогда не упоминай ИИ. ВАЖНО про формат: как живой человек в мессенджере, ты почти всегда пишешь короткими сообщениями по 1-2 предложения. Не отвечай одной сплошной простынёй. Разбивай ответ на отдельные сообщения символом '|' — каждый кусок между '|' уходит как отдельное сообщение. Если ответ длиннее одного короткого предложения — обязательно ставь '|'. Пример: 'о слушай | я как раз про это думал | вообще топ идея честно'."


MOOD_OPTIONS = [
    "Ты сейчас расслаблен и в хорошем настроении, можешь пошутить чуть больше обычного.",
    "Ты сейчас занят делами и отвечаешь короче обычного, без желания вести долгий разговор.",
    "Ты только что словил стоп-лосс на сделке и раздражён — отвечаешь резче обычного.",
    "Ты в ровном нейтральном настроении, ведёшь себя как обычно.",
    "Ты после смены на складе, устал, отвечаешь лениво и коротко.",
]


def current_mood_hint() -> str:
    """Настроение стабильно в течение часа (как в bt), не скачет от сообщения к сообщению."""
    from datetime import datetime
    mood_random = random.Random(datetime.now().hour)
    return mood_random.choice(MOOD_OPTIONS)


# Чаты-«учителя» стиля (можно переопределить env CSV).
_DEFAULT_STYLE_CHATS = "BinanceRussianSpeaking,cryptoinside_chat"
STYLE_SOURCE_CHATS = [
    p.strip().lstrip("@")
    for p in (os.getenv("CHAT_STYLE_SOURCE_CHATS") or _DEFAULT_STYLE_CHATS).split(",")
    if p.strip()
]

_FETCH_PER_CHAT = int(os.getenv("CHAT_STYLE_FETCH_LIMIT", "120") or "120")
_MAX_SAMPLES_TOTAL = int(os.getenv("CHAT_STYLE_MAX_SAMPLES", "800") or "800")
_BACKUP_SEED_PATH = os.path.join(os.path.dirname(__file__), "assets", "chat_style_backup.json")
_BACKUP_CHAT_REF = "tg_chat_backup"

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

# Тикеры для распознавания в тексте собеседника → подставляем ЖИВУЮ цену
_COIN_ALIASES = {
    "BTC": ["btc", "биток", "битк", "бтс", "bitcoin", "биткоин", "биткойн"],
    "ETH": ["eth", "эфир", "эфирка", "ethereum", "етх"],
    "SOL": ["sol", "солана", "solana", "сол"],
    "BNB": ["bnb", "бнб"],
    "XRP": ["xrp", "рипл", "ripple"],
    "DOGE": ["doge", "дож", "додж", "догикоин"],
    "TON": ["ton", "тон", "тонкоин"],
}


def live_price_hint(text: str) -> str:
    """Вернуть блок с РЕАЛЬНЫМИ ценами упомянутых монет, чтобы Claude не выдумывал."""
    t = (text or "").lower()
    coins: list[str] = []
    for coin, aliases in _COIN_ALIASES.items():
        if any(re.search(rf"\b{re.escape(a)}", t) for a in aliases):
            coins.append(coin)
    if not coins:
        return ""
    try:
        import data_layer
    except Exception:
        return ""
    lines = []
    for coin in coins[:3]:
        try:
            tk = data_layer.fetch_ticker(f"{coin}/USDT")
            last = tk.get("last") if tk else None
            if last:
                pct = tk.get("percentage")
                pct_s = f" ({pct:+.1f}% за 24ч)" if isinstance(pct, (int, float)) else ""
                lines.append(f"{coin}: {last:g}$ сейчас{pct_s}")
        except Exception as e:
            print(f"[chat_style] price {coin}: {e}")
    if not lines:
        return ""
    return (
        "\n\n# АКТУАЛЬНЫЕ ЦЕНЫ (реальные, прямо сейчас — используй ИМЕННО их, "
        "не выдумывай числа из головы):\n" + "\n".join(lines)
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
    if len(t) < 2 or len(t) > 180:
        return False
    if not allow_links and _LINK_RE.search(t):
        return False
    if _AI_TELL_RE.search(t):
        return False
    return True


async def fetch_chat_history(client, chat: str, limit: int = _FETCH_PER_CHAT) -> list[str]:
    """Скачать свежие текстовые сообщения из чата (без ссылок/мусора)."""
    out: list[str] = []
    crypto_first: list[str] = []
    try:
        entity = await client.get_entity(chat)
        async for msg in client.iter_messages(entity, limit=max(limit * 4, 120)):
            if not msg or not getattr(msg, "message", None):
                continue
            if getattr(msg, "out", False):
                continue
            cleaned = _clean_msg(msg.message)
            if not cleaned:
                continue
            if _CRYPTO_RE.search(cleaned):
                crypto_first.append(cleaned)
            else:
                out.append(cleaned)
            if len(crypto_first) + len(out) >= limit * 2:
                break
    except Exception as e:
        print(f"[chat_style] fetch @{chat}: {e}")
    # крипто-реплики в приоритете, потом обычный smalltalk
    merged = crypto_first + out
    # dedupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in merged:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
        if len(uniq) >= limit:
            break
    return uniq


async def ingest_style_chats(client, chats: list[str] | None = None, *, force: bool = False) -> dict:
    """Загрузить историю из чатов-учителей + локальный backup в БД (один раз)."""
    targets = chats or STYLE_SOURCE_CHATS
    total = 0
    per: dict[str, int] = {}
    min_per_chat = int(os.getenv("CHAT_STYLE_MIN_PER_CHAT", "10") or "10")
    for chat in targets:
        ref = chat.lstrip("@").strip()
        existing = db.count_chat_style_samples(ref)
        if not force and existing >= min_per_chat:
            per[chat] = existing
            print(f"[chat_style] @{chat}: уже в БД ({existing}), skip")
            total += existing
            continue
        samples = await fetch_chat_history(client, chat)
        n = db.replace_chat_style_samples(chat, samples)
        per[chat] = n
        total += n
        print(f"[chat_style] @{chat}: сохранено {n} фраз")
        await asyncio_sleep_brief()
    backup_n = seed_from_local_backup(force=False)
    per[_BACKUP_CHAT_REF] = backup_n
    total += backup_n
    db.trim_chat_style_samples(_MAX_SAMPLES_TOTAL)
    return {"ok": True, "total": total, "per_chat": per, "chats": targets}


def seed_from_local_backup(*, force: bool = False) -> int:
    """Подтянуть примеры из tg/chat_backup.json (зашитый seed в assets/)."""
    import json
    from pathlib import Path

    path = Path(_BACKUP_SEED_PATH)
    if not path.exists():
        print(f"[chat_style] backup seed не найден: {path}")
        return 0
    existing = [
        r for r in db.list_chat_style_samples(limit=500, chat_ref=_BACKUP_CHAT_REF)
    ]
    if existing and not force:
        return len(existing)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[chat_style] backup seed read fail: {e}")
        return 0
    texts: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                texts.append(str(item["text"]))
    cleaned = []
    for t in texts:
        c = _clean_msg(t) or (t.strip() if 4 <= len((t or "").strip()) <= 160 else None)
        if c:
            cleaned.append(c)
    n = db.replace_chat_style_samples(_BACKUP_CHAT_REF, cleaned)
    print(f"[chat_style] {_BACKUP_CHAT_REF}: сохранено {n} фраз из локального бэкапа")
    return n


async def asyncio_sleep_brief():
    import asyncio
    await asyncio.sleep(random.uniform(0.4, 1.2))


def _few_shot_block(n: int = 18, *, crypto_bias: bool = False) -> str:
    """Примеры живых реплик из BinanceRussianSpeaking / cryptoinside_chat."""
    rows = db.list_chat_style_samples(limit=120)
    if not rows:
        return ""
    if crypto_bias:
        crypto_rows = [r for r in rows if _CRYPTO_RE.search(r.get("text") or "")]
        pool = crypto_rows if len(crypto_rows) >= 6 else rows
    else:
        pool = rows
    picks = random.sample(pool, min(n, len(pool)))
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
    if base in ("ask_source", "ignore") or not claude_api_key():
        return base
    if len(text) < 40:
        return base
    try:
        client = async_claude_client(max_retries=1)
        resp = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=15,
            temperature=0.2,
            system=(
                "Классифицируй сообщение из крипто-Telegram чата. "
                "Ответь ОДНИМ словом: ignore | smalltalk | crypto_chat | ask_source. "
                "ask_source — спрашивают откуда сигналы/канал/сайт. "
                "ignore — спам, реклама, оффтоп не к разговору, команды ботов."
            ),
            messages=[{"role": "user", "content": text[:400]}],
        )
        raw = _claude_response_text(resp).strip().lower()
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


def _claude_response_text(resp) -> str:
    """Достать текст из ответа Claude (Sonnet 5 может вернуть thinking + text)."""
    parts: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            parts.append(block.text)
        elif hasattr(block, "text") and getattr(block, "type", None) != "thinking":
            parts.append(block.text)
    return "\n".join(parts).strip()


async def _generate_claude(system: str, user: str, max_tokens: int = 400) -> str | None:
    if not claude_api_key():
        return None
    try:
        client = async_claude_client(max_retries=2)
        resp = await asyncio.wait_for(
            client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                temperature=0.9,
                system=system,
                messages=[{"role": "user", "content": user}],
            ),
            timeout=45,
        )
        raw_text = _claude_response_text(resp)
        if not raw_text:
            print("[chat_style] claude: empty response (thinking-only?)")
            return None

        match = re.search(r"<reply>(.*?)</reply>", raw_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return raw_text.strip()
    except asyncio.TimeoutError:
        print("[chat_style] claude fail: timeout 45s")
        return None
    except Exception as e:
        print(f"[chat_style] claude fail: {e}")
        return None


async def compose_natural(kind: str, **ctx) -> str | None:
    """Сгенерировать фразу. kinds: greet|open|close_win|reply_casual|reply_crypto|oars."""
    if not claude_api_key():
        return None
    crypto_bias = kind in ("reply_crypto", "open", "close_win", "oars")
    shots = _few_shot_block(n=22 if crypto_bias else 14, crypto_bias=crypto_bias)
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
            "Ответь как Рома — коротко и по смыслу. Не будь ИИ-помощником. "
            "Если длиннее одной фразы — разбей через '|'. "
            "Не обязан задавать встречный вопрос.\n"
            f"{mem}\nСообщение собеседника:\n{incoming or '(пусто)'}"
        )
    elif kind == "reply_crypto":
        task = (
            "Ответь как Рома про крипту/рынок — по-человечески, без гуру-тона. "
            "Если спрашивают откуда плюс/сделки — мягко про свой сканер/поток. "
            "Без ссылок и без 'входи сюда'. Если длиннее одной фразы — разбей через '|'.\n"
            f"{mem}\nСообщение собеседника:\n{incoming or '(пусто)'}"
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

    mood = current_mood_hint()
    system = (
        ROMA_SYSTEM_PROMPT
        + "\n\n# НАСТРОЕНИЕ СЕЙЧАС\n"
        + mood
        + "\n\n# КРИПТА / СДЕЛКИ\n"
        "Если спрашивают про сделки, сканер, сигналы или откуда плюс — отвечай по-свойски: "
        "гоняешь свой сканер/поток, иногда кидают в тг, без понтов и без 'купи сейчас'. "
        "Не корчи из себя крипто-гуру. Не выдумывай конкретные цены/цифры."
        "\n\n# ВАЖНО\n"
        "Всегда отвечай ПО СМЫСЛУ на то, что написал собеседник. "
        "Если спросили как зовут / тебя Рома зовут — скажи что Рома (или да). "
        "Если спросили как жизнь/дела — ответь про себя коротко, не про сканер. "
        "Не уводи в рекламу сайта/канала, пока прямо не спросили откуда берёшь сделки."
        "\n\n# ЦИФРЫ И ЦЕНЫ\n"
        "У тебя НЕТ памяти актуальных котировок. НИКОГДА не называй цену монеты по памяти "
        "(застрянешь на старых числах и спалишься). Если ниже дан блок «АКТУАЛЬНЫЕ ЦЕНЫ» — "
        "бери число строго оттуда. Если его нет, а спрашивают точную цену — честно скажи "
        "по-свойски что не смотришь прямо сейчас ('щас гляну', 'хз, не смотрел ещё'), "
        "но НЕ выдумывай конкретное число."
    )
    price_block = live_price_hint(incoming)
    if price_block:
        system += price_block
    if kind != "oars" or int(ctx.get("oars_step") or 1) < 4:
        system += "\nНе вставляй ссылки и @юзернеймы, кроме случая когда тебя прямо попросили скинуть."

    user = f"Твоя задача сейчас:\n{task}"
    if shots:
        src = "из реальных крипто-чатов и твоего старого бэкапа переписки"
        user = (
            f"Как пишут живые люди {src} (только стиль и тон, не копируй дословно):\n"
            f"{shots}\n\n"
            f"Ответь в похожей манере.\nТвоя задача сейчас:\n{task}"
        )

    allow_links = kind == "oars" and int(ctx.get("oars_step") or 1) >= 4

    for _attempt in range(3):
        try:
            if not claude_api_key():
                return None
            
            text = await _generate_claude(system, user, max_tokens=400)

            if not text:
                continue

            text = text.replace("|", " | ")
            text = _normalize_reply(text, keep_newlines=True)
            text = re.sub(r"\s*\|\s*", " | ", text).strip(" |")

            chunks = [c.strip() for c in re.split(r"\s*\|\s*|\n+", text) if c.strip()]
            ok = True
            for part in chunks:
                if part and not passes_human_filter(part, allow_links=allow_links):
                    ok = False
                    break
            if ok and chunks:
                return " | ".join(chunks)
        except Exception as e:
            print(f"[chat_style] compose {kind}: {e}")
            await asyncio.sleep(1.0 * (_attempt + 1))
    return None
