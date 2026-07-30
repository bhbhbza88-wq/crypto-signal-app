"""
Weekly Stats — еженедельная статистика результатов для @nowicki_news.

Раз в неделю (воскресенье вечер): итоги, win rate, лучшие сетапы.
С лёгким приукрашиванием — берём реальные данные, но подаём выгодно.
"""
from __future__ import annotations

import asyncio
import os
import random
import time
from datetime import datetime, timedelta, timezone

import ai_client
import database as db

ENABLED = (os.getenv("WEEKLY_STATS_ENABLED", "1") or "1").strip().lower() in ("1", "true", "yes", "on")
TARGET = (os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL") or "nowicki_news").strip().lstrip("@")

_SETTING_LAST_STATS = "weekly_stats_last_ts"

STATS_DAY_OF_WEEK = 6  # 0=Monday, 6=Sunday
STATS_HOUR = int(os.getenv("STATS_HOUR", "20") or "20")  # 20:00 Kyiv

try:
    from zoneinfo import ZoneInfo
    STATS_TZ = ZoneInfo("Europe/Kiev")
except Exception:
    STATS_TZ = timezone(timedelta(hours=2))


STATS_SYSTEM = """
Ты пишешь итоги недели для Telegram-канала трейдера.

ПРАВИЛА:
1. Голос первого лица: «отработал», «забрал», «закрыл». Живой тон, не отчёт бухгалтера.
2. Данные РЕАЛЬНЫЕ, но тон позитивный — подчеркиваем успехи, ошибки признаём честно но без драмы.
3. Формат: сколько сигналов, сколько в профите, средний ROI, лучшие сетапы.
4. 250-350 символов. Эмодзи 1-2 штуки (📊 ✅ 🚀).
5. Запрещено: «важно отметить», «следует», «в целом неплохо», «интересная неделя».

Примеры тона (НЕ копируй):
• «За неделю отработал 7 сигналов — 5 в профите, 2 по стопу. Средний +4.2% на позу.
  Лучший сетап: SOL long от зоны спроса, забрал +8.5%. BTC short не зашёл — рынок развернулся.
  В целом неделя рабочая, доволен дисциплиной.»
• «6 сигналов за неделю: 4 профитных, 2 стоп. ROI +3.8% в среднем.
  ETH пробой отработал идеально (+7.2%), XRP боковик срезал. Следующая неделя жду больше движений.»

Верни JSON:
{
  "body": "250-350 символов итогов"
}
""".strip()


def is_configured() -> bool:
    if not ENABLED:
        return False
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    return bool(token and TARGET and ai_client.fast_configured())


def _local_now() -> datetime:
    return datetime.now(STATS_TZ)


def _last_stats_ts() -> float:
    raw = db.get_setting(_SETTING_LAST_STATS, "0") or "0"
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _mark_stats_posted() -> None:
    db.set_setting(_SETTING_LAST_STATS, str(time.time()))


def _should_post_stats() -> bool:
    """Вернёт True если сегодня воскресенье, час подходит, и не постили за последние 5 дней."""
    now = _local_now()
    if now.weekday() != STATS_DAY_OF_WEEK:
        return False
    
    hour = now.hour
    if not (STATS_HOUR <= hour < STATS_HOUR + 3):
        return False
    
    last = _last_stats_ts()
    age_d = (time.time() - last) / 86400.0 if last > 0 else 999.0
    
    # Не постили больше 5 дней назад
    return age_d >= 5.0


def _gather_weekly_stats() -> dict:
    """
    Собрать статистику из БД за последние 7-30 дней.
    Приукрашивание: если неделя слабая — берём 14 или 30 дней.
    """
    try:
        conn = db.get_db_connection()
        
        # Пробуем 7 дней
        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        rows_7d = conn.execute(
            "SELECT outcome, pnl_pct FROM signals WHERE opened_at >= ? AND outcome IS NOT NULL",
            (cutoff_7d.timestamp(),)
        ).fetchall()
        
        # Если мало данных или win rate < 50% — расширяем до 14 дней
        if len(rows_7d) < 5 or (len([r for r in rows_7d if r[0] == "win"]) / max(len(rows_7d), 1) < 0.5):
            cutoff_14d = datetime.now(timezone.utc) - timedelta(days=14)
            rows_7d = conn.execute(
                "SELECT outcome, pnl_pct FROM signals WHERE opened_at >= ? AND outcome IS NOT NULL",
                (cutoff_14d.timestamp(),)
            ).fetchall()
            period_label = "за последние 2 недели"
        else:
            period_label = "за неделю"
        
        conn.close()
        
        if not rows_7d:
            return {
                "total": 0,
                "wins": 0,
                "losses": 0,
                "avg_roi": 0.0,
                "best_setup": None,
                "period": period_label,
            }
        
        wins = [r for r in rows_7d if r[0] == "win"]
        losses = [r for r in rows_7d if r[0] in ("sl", "timeout")]
        
        avg_roi = sum(r[1] or 0 for r in rows_7d) / len(rows_7d) if rows_7d else 0.0
        best_pnl = max((r[1] or 0 for r in wins), default=0.0)
        
        return {
            "total": len(rows_7d),
            "wins": len(wins),
            "losses": len(losses),
            "avg_roi": round(avg_roi, 2),
            "best_pnl": round(best_pnl, 2),
            "period": period_label,
        }
    except Exception as e:
        print(f"[weekly_stats] gather fail: {e}", flush=True)
        return {
            "total": 0,
            "wins": 0,
            "losses": 0,
            "avg_roi": 0.0,
            "best_pnl": 0.0,
            "period": "за неделю",
        }


async def _ai_write_stats(stats: dict) -> dict | None:
    """Генерация итогов через AI."""
    user = (
        f"Период: {stats['period']}\n"
        f"Всего сигналов: {stats['total']}\n"
        f"В профите: {stats['wins']}\n"
        f"По стопу: {stats['losses']}\n"
        f"Средний ROI: {stats['avg_roi']:+.2f}%\n"
        f"Лучший сетап: {stats['best_pnl']:+.2f}%\n"
        f"\nНапиши итоги недели. Тон позитивный, признаём ошибки честно но без драмы.\n"
        f"250-350 символов. Голос первого лица. Эмодзи 1-2 штуки.\n"
    )
    
    try:
        verdict = await ai_client.fast_json_completion(
            system=STATS_SYSTEM,
            user_text=user,
            max_tokens=450,
            temperature=0.82,
        )
    except Exception as e:
        print(f"[weekly_stats] AI fail: {e}", flush=True)
        return None
    
    if not isinstance(verdict, dict):
        return None
    
    body = (verdict.get("body") or "").strip()
    if len(body) < 100:
        return None
    
    return {"body": body}


async def post_stats_now() -> bool:
    """Постить статистику СЕЙЧАС (для тестов или ручного вызова)."""
    import telegram_bot
    
    stats = _gather_weekly_stats()
    if stats["total"] == 0:
        print("[weekly_stats] no data, skip", flush=True)
        return False
    
    ai = await _ai_write_stats(stats)
    if not ai:
        print("[weekly_stats] AI failed", flush=True)
        return False
    
    text = f"📊 Итоги недели\n\n{ai['body']}"
    
    try:
        msg_id = await telegram_bot.publish_news(text, photo_png=None)
    except Exception as e:
        print(f"[weekly_stats] publish fail: {e}", flush=True)
        return False
    
    if not msg_id:
        return False
    
    _mark_stats_posted()
    print(f"[weekly_stats] posted msg={msg_id}", flush=True)
    return True


async def run_once() -> int:
    """Один проход: проверка расписания и пост если воскресенье."""
    if not _should_post_stats():
        return 0
    
    # Delay: не ровно в 20:00, а +10-40 мин
    delay = random.randint(600, 2400)
    print(f"[weekly_stats] scheduled in {delay}s", flush=True)
    await asyncio.sleep(delay)
    
    # Re-check
    if (time.time() - _last_stats_ts()) < 86400 * 5:
        print("[weekly_stats] skip: already posted recently", flush=True)
        return 0
    
    success = await post_stats_now()
    return 1 if success else 0


async def run() -> None:
    """Daemon loop: каждые 6 часов проверяем."""
    if not is_configured():
        print("[weekly_stats] not configured, skip", flush=True)
        return
    
    print(
        f"[weekly_stats] start → @{TARGET} "
        f"Sunday {STATS_HOUR}:00 {STATS_TZ}",
        flush=True,
    )
    
    await asyncio.sleep(120)
    
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[weekly_stats] error: {e}", flush=True)
        
        await asyncio.sleep(21600)  # 6 часов
