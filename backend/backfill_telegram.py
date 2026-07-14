"""
Одноразовый бэкфилл: публикует уже закрытые сделки из history в текущий
TELEGRAM_CHAT_ID (использовалось для проверки только что подключённого
нового канала — старые сделки туда не попали, потому что были закрыты до
смены переменной). Запуск вручную из Railway Console:

    python backfill_telegram.py
"""
import asyncio
import database as db
import telegram_bot


async def main():
    db.init_db()
    history = sorted(db.load_history(limit=200), key=lambda h: h["id"])
    if not history:
        print("Истории нет — нечего публиковать.")
        return
    for h in history:
        signal = {"symbol": h["symbol"], "signal": h["signal"]}
        await telegram_bot.notify_signal_closed(signal, h["result"], h["pnl"])
        print(f"Отправлено: {h['symbol']} {h['signal']} {h['result']} {h['pnl']:+.2f}%")
        await asyncio.sleep(1)  # не спамить Telegram API подряд
    print(f"Готово — отправлено {len(history)} сообщений.")


if __name__ == "__main__":
    asyncio.run(main())
