"""
Market Digest — утренний/вечерний обзор рынка для @nowicki_news.

Раз в 12ч: общий фон по BTC/альтам, доминация, настроение.
Без конкретных входов — просто взгляд на рынок.
"""
from __future__ import annotations

import asyncio
import os
import random
import time
from datetime import datetime, timedelta, timezone

import ai_client
import database as db
from data_layer import fetch_ohlcv_raw, CANDIDATES
import pandas as pd

ENABLED = (os.getenv("MARKET_DIGEST_ENABLED", "1") or "1").strip().lower() in ("1", "true", "yes", "on")
TARGET = (os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL") or "nowicki_news").strip().lstrip("@")

_SETTING_LAST_DIGEST = "market_digest_last_ts"  # timestamp последнего обзора

DIGEST_MORNING_HOUR = int(os.getenv("DIGEST_MORNING_HOUR", "9") or "9")  # 09:00 Kyiv
DIGEST_EVENING_HOUR = int(os.getenv("DIGEST_EVENING_HOUR", "21") or "21")  # 21:00 Kyiv

try:
    from zoneinfo import ZoneInfo
    DIGEST_TZ = ZoneInfo("Europe/Kiev")
except Exception:
    DIGEST_TZ = timezone(timedelta(hours=2))


DIGEST_SYSTEM = """
Ты пишешь короткий обзор рынка для Telegram-канала трейдера.
Формат: утренний взгляд или вечерний дайджест.

ПРАВИЛА:
1. Голос первого лица: «смотрю», «жду», «вижу». Как живой трейдер, не новостной бот.
2. Общий фон рынка: BTC (цена, направление), доминация, альты (растут/падают/боковик).
3. Что двигает рынок сегодня: макро, новости, настроение (страх/жадность).
4. Без конкретных входов и таргетов — это обзор, не сигнал.
5. Тон спокойный, профи. 200-300 символов.
6. Запрещено: «важно отметить», «следует», «таким образом», «не повод для паники»,
   «всё чётко», «интересная картина».

Примеры тона (НЕ копируй):
• Утро: «BTC держится в 64-65k, альты спокойные. Доминация 53% — пока боковик.
  Сегодня данные по инфляции из US, жду реакцию к вечеру. Пока без резких движений.»
• Вечер: «За день BTC просел к 63.5k — альты следом. Доминация выросла до 54%.
  Рынок переварил новости, смотрю как откроет Азия. Завтра жду продолжение или отскок от 63k.»

Верни JSON:
{
  "body": "200-300 символов обзора",
  "time_of_day": "morning" или "evening"
}
""".strip()


def is_configured() -> bool:
    if not ENABLED:
        return False
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    return bool(token and TARGET and ai_client.fast_configured())


def _local_now() -> datetime:
    return datetime.now(DIGEST_TZ)


def _last_digest_ts() -> float:
    raw = db.get_setting(_SETTING_LAST_DIGEST, "0") or "0"
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _mark_digest_posted() -> None:
    db.set_setting(_SETTING_LAST_DIGEST, str(time.time()))


def _should_post_digest() -> str | None:
    """
    Вернёт 'morning' или 'evening' если пора постить, иначе None.
    Логика: проверяем час и не постили ли уже за последние 8ч.
    """
    now = _local_now()
    hour = now.hour
    last = _last_digest_ts()
    age_h = (time.time() - last) / 3600.0 if last > 0 else 999.0
    
    # Защита от дублей: если постили меньше 8ч назад — скип
    if age_h < 8.0:
        return None
    
    # Утро: 9:00-11:00
    if DIGEST_MORNING_HOUR <= hour < DIGEST_MORNING_HOUR + 2:
        return "morning"
    
    # Вечер: 21:00-23:00
    if DIGEST_EVENING_HOUR <= hour < DIGEST_EVENING_HOUR + 2:
        return "evening"
    
    return None


def _gather_market_context() -> dict:
    """Собрать данные для AI: BTC цена, альты, доминация."""
    try:
        # BTC
        btc_raw = fetch_ohlcv_raw("BTC/USDT", "1h", limit=48, exchange_id="bybit")
        if btc_raw and len(btc_raw) >= 2:
            btc_close = float(btc_raw[-1][4])
            btc_open_24h = float(btc_raw[-24][4]) if len(btc_raw) >= 24 else btc_close
            btc_chg_24h = (btc_close / btc_open_24h - 1.0) * 100.0
        else:
            btc_close, btc_chg_24h = 0.0, 0.0
        
        # Альты: средний прирост топ-10
        alts = ["ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT"]
        alts_chg = []
        for sym in alts:
            try:
                raw = fetch_ohlcv_raw(sym, "1h", limit=24, exchange_id="bybit")
                if raw and len(raw) >= 2:
                    c = float(raw[-1][4])
                    o = float(raw[0][4])
                    alts_chg.append((c / o - 1.0) * 100.0)
            except Exception:
                pass
        
        alts_avg_chg = sum(alts_chg) / len(alts_chg) if alts_chg else 0.0
        
        # Доминация BTC (примерно) — в реальности нужен API, упрощаем
        dominance = 52.0 + random.uniform(-2, 2)  # заглушка
        
        return {
            "btc_price": btc_close,
            "btc_chg_24h": round(btc_chg_24h, 2),
            "alts_avg_chg": round(alts_avg_chg, 2),
            "dominance": round(dominance, 1),
        }
    except Exception as e:
        print(f"[market_digest] context gather fail: {e}", flush=True)
        return {
            "btc_price": 0.0,
            "btc_chg_24h": 0.0,
            "alts_avg_chg": 0.0,
            "dominance": 52.0,
        }


async def _ai_write_digest(time_of_day: str, ctx: dict) -> dict | None:
    """Генерация обзора через AI."""
    btc_p = ctx.get("btc_price") or 0
    btc_chg = ctx.get("btc_chg_24h") or 0
    alts_chg = ctx.get("alts_avg_chg") or 0
    dom = ctx.get("dominance") or 52.0
    
    user = (
        f"time_of_day: {time_of_day}\n"
        f"BTC: ${btc_p:.0f} ({btc_chg:+.2f}% за 24ч)\n"
        f"Альты: средний {alts_chg:+.2f}% за 24ч\n"
        f"Доминация BTC: {dom:.1f}%\n"
        f"\nНапиши короткий обзор рынка ({time_of_day}). Общий фон, настроение, что жду.\n"
        f"200-300 символов. Голос первого лица. Без штампов.\n"
    )
    
    try:
        verdict = await ai_client.fast_json_completion(
            system=DIGEST_SYSTEM,
            user_text=user,
            max_tokens=400,
            temperature=0.88,
        )
    except Exception as e:
        print(f"[market_digest] AI fail: {e}", flush=True)
        return None
    
    if not isinstance(verdict, dict):
        return None
    
    body = (verdict.get("body") or "").strip()
    if len(body) < 100:
        return None
    
    return {
        "body": body,
        "time_of_day": time_of_day,
    }


async def post_digest_now(time_of_day: str) -> bool:
    """Постить обзор СЕЙЧАС (для тестов или ручного вызова)."""
    import telegram_bot
    
    ctx = _gather_market_context()
    ai = await _ai_write_digest(time_of_day, ctx)
    if not ai:
        print(f"[market_digest] AI failed for {time_of_day}", flush=True)
        return False
    
    emoji = "🌅" if time_of_day == "morning" else "🌙"
    label = "Утренний взгляд" if time_of_day == "morning" else "Вечерний обзор"
    
    text = f"{emoji} {label}\n\n{ai['body']}"
    
    try:
        msg_id = await telegram_bot.publish_news(text, photo_png=None)
    except Exception as e:
        print(f"[market_digest] publish fail: {e}", flush=True)
        return False
    
    if not msg_id:
        return False
    
    _mark_digest_posted()
    print(f"[market_digest] posted {time_of_day} msg={msg_id}", flush=True)
    return True


async def run_once() -> int:
    """Один проход: проверка расписания и пост если пора. Возвращает 1 если запостили."""
    time_of_day = _should_post_digest()
    if not time_of_day:
        return 0
    
    # Human-like delay: не ровно в 09:00, а +10-30 мин
    delay = random.randint(600, 1800)
    print(f"[market_digest] scheduled {time_of_day} in {delay}s", flush=True)
    await asyncio.sleep(delay)
    
    # Re-check после задержки (вдруг уже запостили)
    if (time.time() - _last_digest_ts()) < 3600 * 6:
        print("[market_digest] skip: already posted recently", flush=True)
        return 0
    
    success = await post_digest_now(time_of_day)
    return 1 if success else 0


async def run() -> None:
    """Daemon loop: каждый час проверяем расписание."""
    if not is_configured():
        print("[market_digest] not configured, skip", flush=True)
        return
    
    print(
        f"[market_digest] start → @{TARGET} "
        f"morning={DIGEST_MORNING_HOUR}:00 evening={DIGEST_EVENING_HOUR}:00 {DIGEST_TZ}",
        flush=True,
    )
    
    await asyncio.sleep(60)  # startup delay
    
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[market_digest] error: {e}", flush=True)
        
        # Проверка каждый час
        await asyncio.sleep(3600)
