"""
Бэкфилл: публикует уже закрытые сделки из history в публичный канал
результатов (TELEGRAM_PUBLIC_CHANNEL_ID, по умолчанию @papayaqq).

Идемпотентно: помнит id последней опубликованной записи истории
(settings.backfill_channel_last_id) — повторный запуск шлёт только то, что
добавилось после прошлого раза, старое не дублирует.

Крупные минусы (см. telegram_bot.PUBLIC_CHANNEL_MAX_LOSS_PCT) и так
отфильтровываются внутри notify_signal_closed — здесь просто идём по всей
истории по порядку и считаем, что реально ушло в канал.

Запуск вручную (напр. из Railway Console):
    python backfill_telegram.py
Или через API: POST /api/admin/backfill-channel-history (см. main.py).
"""
import asyncio
import random

import database as db
import telegram_bot

_SETTING_KEY = "backfill_channel_last_id"


async def run_backfill(limit: int | None = None, reset: bool = False) -> dict:
    """Публикует историю, которая ещё не была отправлена в канал.

    limit — максимум сообщений за один вызов (по умолчанию без ограничения).
    reset — игнорировать сохранённый маркер и пройти всю историю заново
    (используется только вручную, если нужно перепостить всё)."""
    db.init_db()
    last_id = 0 if reset else int(db.get_setting(_SETTING_KEY, "0") or "0")

    history = sorted(db.load_history(limit=100000), key=lambda h: h["id"])
    todo = [h for h in history if h["id"] > last_id]
    if limit:
        todo = todo[:limit]

    if not todo:
        return {"posted": 0, "skipped": 0, "total_checked": 0, "last_id": last_id}

    posted, skipped = 0, 0
    for h in todo:
        signal = {
            "symbol": h["symbol"], "signal": h["signal"],
            "entry": h.get("entry"), "exit": None,
        }
        try:
            before = telegram_bot.PUBLIC_CHANNEL_MAX_LOSS_PCT
            will_post = not (h["pnl"] < 0 and abs(h["pnl"]) > before)
            await telegram_bot.notify_signal_closed(signal, h["result"], h["pnl"])
            if will_post:
                posted += 1
                print(f"[backfill] отправлено: {h['symbol']} {h['signal']} {h['result']} {h['pnl']:+.2f}%")
            else:
                skipped += 1
                print(f"[backfill] пропущено (крупный минус): {h['symbol']} {h['pnl']:+.2f}%")
        except Exception as e:
            print(f"[backfill] ошибка на {h['symbol']} (id={h['id']}): {e}")
        db.set_setting(_SETTING_KEY, str(h["id"]))
        await asyncio.sleep(random.uniform(2.5, 5.5))  # не спамить Telegram API/подписчиков

    return {"posted": posted, "skipped": skipped, "total_checked": len(todo), "last_id": todo[-1]["id"]}


async def main():
    result = await run_backfill()
    print(f"Готово — опубликовано {result['posted']}, пропущено {result['skipped']} "
          f"из {result['total_checked']} проверенных.")


if __name__ == "__main__":
    asyncio.run(main())
