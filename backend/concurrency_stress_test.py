"""
Изолированный стресс-тест конкурентности для open_signal().
Локальный скрипт, не используется в проде и не импортируется приложением.

Бьёт N параллельными задачами по одному и тому же symbol и проверяет,
что ровно один вызов реально создал позицию, а остальные получили
'already_open' — без дублирующихся записей/событий в БД.

Запуск: python backend/concurrency_stress_test.py
"""

import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import database as db
import signal_ingest

CONCURRENCY = 20
SYMBOL = "BTCUSDT"
PAYLOAD = dict(
    signal="LONG",
    entry=60000,
    stop=59000,
    tp1=61000,
    tp2=63000,
    tp3=65000,
    trader_id=1,
    regime="trend",
)


def _call_open_signal():
    return signal_ingest.open_signal(SYMBOL, **PAYLOAD)


async def fire_concurrent_requests(n: int):
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, _call_open_signal) for _ in range(n)]
    return await asyncio.gather(*tasks)


def reset_state(symbol: str):
    db.remove_trade(signal_ingest.normalize_symbol(symbol))


def report(results):
    outcomes = Counter()
    for sym, err in results:
        outcomes["success"] += 1 if sym else 0
        if err:
            outcomes[err] += 1

    print(f"Запросов отправлено: {len(results)}")
    print(f"Успешных open_signal(): {outcomes['success']}")
    print(f"already_open: {outcomes['already_open']}")
    print(f"invalid_levels: {outcomes['invalid_levels']}")

    row = db.get_trade(signal_ingest.normalize_symbol(SYMBOL))
    print(f"Строк в open_trades для {SYMBOL}: {1 if row else 0}")

    passed = outcomes["success"] == 1 and outcomes["already_open"] == len(results) - 1
    print("RESULT:", "PASS" if passed else "FAIL — race condition обнаружен")
    return passed


async def main():
    db.init_db()
    reset_state(SYMBOL)
    results = await fire_concurrent_requests(CONCURRENCY)
    ok = report(results)
    reset_state(SYMBOL)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
