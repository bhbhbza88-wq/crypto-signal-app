"""
Chat Engage — пишет в whitelist-чаты «как человек» по реальным сделкам NOWICKI.

  открыли сигнал  → сначала «привет / как дела», через 1.5–10 мин — ТВХ (вход)
  закрыли в плюс  → в тех же чатах «отработала, +X%»
  в минус         → молчим
  спросили «где берёшь» → мягко сайт + канал

Env:
  TELEGRAM_API_ID / TELEGRAM_API_HASH
  TELEGRAM_CHAT_WHITELIST              — username чатов через запятую
                                         (если пусто — дефолтный набор RU-чатов)
  TELEGRAM_CHAT_SESSION                — опционально, второй аккаунт
  TELEGRAM_SESSION                     — fallback, если CHAT_SESSION пустой
  CHAT_ENGAGE_GREET_MIN_SEC            — мин. пауза привет→ТВХ (default 90)
  CHAT_ENGAGE_GREET_MAX_SEC            — макс. пауза привет→ТВХ (default 600 = 10м)

Режим shared (один аккаунт с ingest): не поднимаем второй Telethon-клиент —
ingest вызывает attach_to_client(client). Иначе AuthKeyDuplicatedError.
Отдельный аккаунт: TELEGRAM_CHAT_SESSION ≠ TELEGRAM_SESSION → run() сам.
"""

from __future__ import annotations

import asyncio
import os
import random
import re

import database as db

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "").strip()
TELEGRAM_CHAT_SESSION = os.getenv("TELEGRAM_CHAT_SESSION", "").strip()

# Отобранные чаты для engage (override через TELEGRAM_CHAT_WHITELIST на Railway).
_DEFAULT_CHAT_WHITELIST = (
    "kriptovaluta_01,bybitrussian,BinanceRussianSpeaking,"
    "cryptoinside_chat,minter_traders_chat,CryptoFLUD,cscalp_crypto"
)
TELEGRAM_CHAT_WHITELIST = (os.getenv("TELEGRAM_CHAT_WHITELIST") or _DEFAULT_CHAT_WHITELIST).strip()

CHANNEL_URL = os.getenv("TELEGRAM_PUBLIC_CHANNEL_URL", "").strip() or "https://t.me/papayaqq"
SITE_URL = "https://nowicki.trade"

# Пауза между «привет» и ТВХ (секунды), по умолчанию до 10 минут.
_GREET_MIN = float(os.getenv("CHAT_ENGAGE_GREET_MIN_SEC", "90") or "90")
_GREET_MAX = float(os.getenv("CHAT_ENGAGE_GREET_MAX_SEC", "600") or "600")
if _GREET_MAX < _GREET_MIN:
    _GREET_MAX = _GREET_MIN

from display_polish import polish_pnl  # noqa: E402

_queue: asyncio.Queue | None = None
_main_loop: asyncio.AbstractEventLoop | None = None
_attached = False

ASK_RE = re.compile(
    r"(где\s+(бер|наход|смотр|берёшь|берешь|нашел|нашёл)|"
    r"какой\s+(сайт|канал|бот)|"
    r"скинь\s+(ссыл|канал|сайт)|"
    r"откуда\s+(сигнал|монет)|"
    r"how\s+do\s+you\s+find|"
    r"what('?s|\s+is)\s+your\s+(channel|site))",
    re.IGNORECASE,
)


def _session_string() -> str:
    return TELEGRAM_CHAT_SESSION or TELEGRAM_SESSION


def uses_ingest_session() -> bool:
    """True = пишем тем же аккаунтом, что и ingest — отдельный клиент нельзя."""
    if not TELEGRAM_CHAT_WHITELIST:
        return False
    if not TELEGRAM_CHAT_SESSION:
        return True
    return TELEGRAM_CHAT_SESSION == TELEGRAM_SESSION


def is_configured() -> bool:
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH and _session_string() and TELEGRAM_CHAT_WHITELIST)


def needs_own_client() -> bool:
    """Отдельный run() только если есть свой CHAT_SESSION, отличный от ingest."""
    return is_configured() and not uses_ingest_session()


def _whitelist() -> list[str]:
    return [p.strip().lstrip("@") for p in TELEGRAM_CHAT_WHITELIST.split(",") if p.strip()]


def _coin(symbol: str) -> str:
    return (symbol or "").replace("/USDT", "").replace("USDT", "").upper()


def _fmt_entry(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 100:
        return f"{n:.2f}"
    if n >= 1:
        return f"{n:.4f}"
    return f"{n:.6f}".rstrip("0").rstrip(".")


# не повторяем одни и те же фразы подряд
_recent_open: list[str] = []
_recent_close: list[str] = []
_recent_greet: list[str] = []


def _pick_unique(candidates: list[str], recent: list[str], remember: int = 8) -> str:
    pool = [c for c in candidates if c not in recent] or candidates
    choice = random.choice(pool)
    recent.append(choice)
    del recent[:-remember]
    return choice


def _greet_text() -> str:
    """Лёгкий small-talk без монет и ссылок — до ТВХ."""
    templates = [
        "Всем привет, как дела?",
        "Здарова народ, как рынок сегодня?",
        "Привет, кто на месте?",
        "Ку, как настроение по рынку?",
        "Всем здарова, живы?",
        "Приветик, как у всех дела?",
        "Йо, что по рынку думаете?",
        "Здарова, тихо сегодня или кто-то в сделках?",
        "Всем ку, как настроение?",
        "Привет всем, как день проходит?",
        "Здарова, кто на графиках?",
        "Всем привет, как оно?",
        "Ку люди, что смотрите?",
        "Привет, есть кто живой?",
        "Здарова чат, как настрой?",
        "Всем хай, спокойный день?",
        "Привет, как у вас по позициям?",
        "Йо народ, что интересного?",
        "Всем ку, кто на месте напишите)",
        "Здарова, просто чекнул чат",
    ]
    return _pick_unique(templates, _recent_greet, remember=10)


def _open_text(symbol: str, side: str, entry) -> str:
    coin = _coin(symbol)
    side_ru = "лонг" if side == "LONG" else "шорт"
    e = _fmt_entry(entry)
    templates = [
        f"Взял {side_ru} по {coin} от {e}, че думаете?",
        f"Зашёл в {side_ru} по {coin} около {e}. Как вам сетап?",
        f"Пробую {side_ru} {coin} от {e}, стоп короткий",
        f"По {coin} взял {side_ru} с {e}, посмотрим",
        f"Зашёл {coin} {side_ru} от {e}. Кто тоже смотрит?",
        f"Взял такой {side_ru} по {coin}, вход {e}",
        f"По {coin} открыл {side_ru} от {e}",
        f"Залетел в {side_ru} по {coin}, {e}. Мнения?",
        f"{coin} — взял {side_ru} около {e}",
        f"Сегодня по {coin} зашёл в {side_ru} с {e}",
        f"Глянул {coin}, открыл {side_ru} от {e}",
        f"На копейку пробую {side_ru} {coin} от {e}",
        f"Чувство что {coin} в {side_ru} пойдёт — уже зашёл от {e}",
        f"По {coin} сетап норм, взял {side_ru} {e}",
        f"Зашёл так по {coin}: {side_ru} от {e}",
        f"Взял {side_ru} {coin}, вход {e}. Держу",
        f"{coin} интересный, я в {side_ru} с {e}",
        f"Короче {coin}, {side_ru} от {e}",
        f"Поймал вход по {coin}, {side_ru} {e}",
        f"Маленьким плечом взял {side_ru} {coin} от {e}",
        f"Есть идея по {coin} — {side_ru} от {e}",
        f"Зашёл по {coin} в {side_ru}, цена {e}. Кто с нами?",
        f"Пробую такой {side_ru} по {coin} от {e}",
        f"По {coin} уже в {side_ru} с {e}, поглядим",
    ]
    return _pick_unique(templates, _recent_open)


def _close_win_text(symbol: str, pnl: float) -> str:
    coin = _coin(symbol)
    show = polish_pnl(pnl, decimals=1)
    if show < 0:
        show = abs(show)
    templates = [
        f"По {coin} закрыл, примерно +{show}%",
        f"{coin} закрыл в плюс, около +{show}%",
        f"По {coin} зафиксировал, вышло ~+{show}%",
        f"Закрыл {coin}, +{show}% примерно. Норм зашло",
        f"По той сделке {coin} вышли около +{show}%",
        f"{coin} отработала, где-то +{show}%",
        f"Вышел по {coin}, плюс около +{show}%",
        f"По {coin} забрал +{show}% примерно",
        f"Фиксанул {coin}, вышло +{show}%",
        f"{coin} закрыл — плюс ~+{show}%. Приятно",
        f"По {coin} всё, +{show}% в кармане",
        f"Сделку по {coin} закрыл в плюс (+{show}%)",
        f"Ок, {coin} дала около +{show}%",
        f"По {coin} вышли чисто, примерно +{show}%",
        f"Закрыл ту по {coin}, +{show}%",
        f"{coin} зашла нормально, +{show}% примерно",
        f"Зафиксировал {coin} около +{show}%",
        f"По {coin} профит ~+{show}%",
        f"Готово по {coin}: примерно +{show}%",
        f"Та {coin} отработала на +{show}%",
        f"Плюсанул по {coin}, где-то +{show}%",
        f"По {coin} закрылись, +{show}%. Не космос, но ок",
    ]
    return _pick_unique(templates, _recent_close)


def _soft_promo_reply() -> str:
    templates = [
        f"Смотрю сканер на {SITE_URL}, ещё кидают в {CHANNEL_URL}",
        f"Обычно через nowicki — {SITE_URL}, канал {CHANNEL_URL}",
        f"Беру оттуда: {SITE_URL} и тг {CHANNEL_URL}",
        f"Есть сканер {SITE_URL}, плюс канал {CHANNEL_URL}",
        f"Если коротко — {SITE_URL} / {CHANNEL_URL}",
        f"Глянь nowicki.trade и канал {CHANNEL_URL}, оттуда идеи",
    ]
    return random.choice(templates)


def _enqueue(job: dict) -> None:
    if _queue is None or _main_loop is None:
        print("[chat_engage] воркер ещё не готов — пост пропущен")
        return
    try:
        _main_loop.call_soon_threadsafe(_queue.put_nowait, job)
    except Exception as e:
        print(f"[chat_engage] enqueue: {e}")


def fire_open(symbol: str, side: str, entry) -> None:
    if not is_configured():
        return
    _enqueue({"kind": "open", "symbol": symbol, "side": side, "entry": entry})


def fire_close(symbol: str, side: str, result: str, pnl: float,
               entry: float | None = None, exit_price: float | None = None) -> None:
    if not is_configured():
        return
    _enqueue({
        "kind": "close",
        "symbol": symbol,
        "side": side,
        "result": result,
        "pnl": pnl,
        "entry": entry,
        "exit_price": exit_price,
    })


async def _do_open_one_chat(client, chat: str, symbol: str, side: str, entry,
                            stagger_sec: float = 0) -> None:
    """Привет → пауза 1.5–10 мин → ТВХ в одном чате."""
    try:
        if stagger_sec > 0:
            await asyncio.sleep(stagger_sec)
        entity = await client.get_entity(chat)
        greet = _greet_text()
        await client.send_message(entity, greet)
        print(f"[chat_engage] greet → {chat}")

        delay = random.uniform(_GREET_MIN, _GREET_MAX)
        print(f"[chat_engage] {chat}: ТВХ через {delay / 60:.1f} мин")
        await asyncio.sleep(delay)

        text = _open_text(symbol, side, entry)
        msg = await client.send_message(entity, text)
        db.save_chat_engage_post(symbol, int(entity.id), int(msg.id), str(chat))
        print(f"[chat_engage] open → {chat}: {symbol} {side}")
    except Exception as e:
        print(f"[chat_engage] не смог написать в {chat}: {e}")


async def _do_open(client, symbol: str, side: str, entry) -> None:
    chats = _whitelist()
    if not chats:
        return
    # Параллельно по чатам, старт приветов разнесён на ~0–2 мин,
    # чтобы не слать во все сразу одним пакетом.
    tasks = [
        asyncio.create_task(
            _do_open_one_chat(
                client, chat, symbol, side, entry,
                stagger_sec=i * random.uniform(8, 25),
            )
        )
        for i, chat in enumerate(chats)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for chat, res in zip(chats, results):
        if isinstance(res, Exception):
            print(f"[chat_engage] open task fail {chat}: {res}")


async def _do_close(client, symbol: str, side: str, result: str, pnl: float,
                    entry=None, exit_price=None) -> None:
    if pnl is None or float(pnl) <= 0:
        db.clear_chat_engage_posts(symbol)
        return
    posts = db.list_chat_engage_posts(symbol)
    if not posts:
        return
    text = _close_win_text(symbol, float(pnl))
    photo = None
    if entry is not None:
        try:
            from profit_card import render_profit_card
            photo = render_profit_card(
                symbol=symbol, side=side, entry=float(entry),
                pnl_pct=float(pnl), exit_price=exit_price,
            )
        except Exception as e:
            print(f"[chat_engage] profit_card: {e}")

    for i, row in enumerate(posts):
        try:
            if i:
                await asyncio.sleep(random.uniform(3, 9))
            target = row.get("chat_ref") or row["chat_id"]
            reply_to = row.get("msg_id")
            if photo:
                from io import BytesIO
                bio = BytesIO(photo)
                bio.name = "pnl.png"  # без .png Telethon шлёт как файл-документ
                await client.send_file(
                    target,
                    bio,
                    caption=text,
                    reply_to=reply_to,
                    force_document=False,
                )
            else:
                await client.send_message(target, text, reply_to=reply_to)
            print(f"[chat_engage] close+ → {target}: {symbol} {float(pnl):+.1f}%")
        except Exception as e:
            print(f"[chat_engage] close fail {row}: {e}")
    db.clear_chat_engage_posts(symbol)


async def _worker_loop(client):
    while True:
        job = await _queue.get()
        try:
            if job["kind"] == "open":
                await _do_open(client, job["symbol"], job["side"], job["entry"])
            elif job["kind"] == "close":
                await _do_close(
                    client, job["symbol"], job["side"],
                    job.get("result", ""), job.get("pnl", 0),
                    entry=job.get("entry"),
                    exit_price=job.get("exit_price"),
                )
        except Exception as e:
            print(f"[chat_engage] job error: {e}")
        finally:
            _queue.task_done()


def _register_ask_handler(client, me):
    from telethon import events

    @client.on(events.NewMessage(incoming=True))
    async def on_msg(event):
        text = event.raw_text or ""
        if not ASK_RE.search(text):
            return
        if event.sender_id == me.id:
            return
        if not event.is_private:
            mentioned = bool(getattr(event.message, "mentioned", False))
            is_reply_to_us = False
            if event.is_reply and event.reply_to:
                try:
                    replied = await event.get_reply_message()
                    is_reply_to_us = replied and replied.sender_id == me.id
                except Exception:
                    pass
            if not (mentioned or is_reply_to_us):
                return
        await asyncio.sleep(random.uniform(2, 6))
        await event.respond(_soft_promo_reply())


async def attach_to_client(client) -> asyncio.Task | None:
    """Подцепить очередь к уже запущенному ingest-клиенту (один аккаунт)."""
    global _queue, _main_loop, _attached
    if not is_configured() or not uses_ingest_session():
        return None
    if _attached:
        return None
    _main_loop = asyncio.get_running_loop()
    _queue = asyncio.Queue()
    me = await client.get_me()
    _register_ask_handler(client, me)
    task = asyncio.create_task(_worker_loop(client))
    _attached = True
    print(
        f"[chat_engage] shared с ingest: @{me.username or me.id}, "
        f"чаты: {', '.join(_whitelist())}"
    )
    return task


def detach():
    """Сброс при disconnect ingest — следующий _run_once снова attach."""
    global _queue, _main_loop, _attached
    _attached = False
    _queue = None
    _main_loop = None


async def run():
    """Отдельный аккаунт (TELEGRAM_CHAT_SESSION свой)."""
    global _queue, _main_loop
    if not needs_own_client():
        if is_configured() and uses_ingest_session():
            print("[chat_engage] режим shared — ждём attach от telegram_ingest")
        else:
            print("[chat_engage] не сконфигурирован (нужен WHITELIST) — пропуск")
        return

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    _main_loop = asyncio.get_running_loop()
    _queue = asyncio.Queue()
    print(f"[chat_engage] отдельный аккаунт, чаты: {', '.join(_whitelist())}")

    while True:
        client = None
        worker_task = None
        try:
            client = TelegramClient(
                StringSession(TELEGRAM_CHAT_SESSION),
                int(TELEGRAM_API_ID),
                TELEGRAM_API_HASH,
            )
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("TELEGRAM_CHAT_SESSION не авторизована")
            me = await client.get_me()
            print(f"[chat_engage] online as {me.first_name} (@{me.username or me.id})")
            _register_ask_handler(client, me)
            worker_task = asyncio.create_task(_worker_loop(client))
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            if client:
                await client.disconnect()
            raise
        except Exception as e:
            print(f"[chat_engage] упал: {e}, рестарт через 20с")
        finally:
            if worker_task:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        await asyncio.sleep(20)
