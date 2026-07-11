"""
In-memory трекер фоновых задач анализа каналов — тот же паттерн, что и job-стор
в robustness.py (create_job/get_job/_update/_finish), под отдельный сценарий:
ingest истории канала + бэктест + сохранение отчёта в channel_stats.

Не персистентный: если backend перезапустится посреди анализа, задача теряется
(как и у robustness) — это ок, т.к. клиент просто увидит 404 и предложит начать
заново, а не зависшую вечно "running" задачу.
"""

import asyncio
import json
import threading
import time
import uuid

import database as db
from channel_backtest import SignalBacktester

_jobs = {}
_jobs_lock = threading.Lock()
MAX_JOBS = 50


def create_job() -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        if len(_jobs) >= MAX_JOBS:
            oldest = sorted(_jobs.items(), key=lambda kv: kv[1]['created'])[0][0]
            del _jobs[oldest]
        _jobs[job_id] = {"status": "running", "step": "старт", "result": None,
                          "error": None, "created": time.time()}
    return job_id


def get_job(job_id: str):
    with _jobs_lock:
        return _jobs.get(job_id)


def _update(job_id, step):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["step"] = step


def _finish(job_id, result=None, error=None):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "failed" if error else "done"
            _jobs[job_id]["result"] = result
            _jobs[job_id]["error"] = error


def run_channel_analysis(job_id: str, channel: str, days: int, entry_timeout_hours: int = 6,
                          max_hold_hours: int = 168, risk_per_trade_usd: float = 100.0):
    """Синхронная точка входа для threading.Thread (как в /api/backtest/robustness) —
    сама открывает свой asyncio event loop для ingest_channel_history (Telethon async)."""
    try:
        bt = SignalBacktester(entry_timeout_hours=entry_timeout_hours,
                               max_hold_hours=max_hold_hours,
                               risk_per_trade_usd=risk_per_trade_usd)

        _update(job_id, "загрузка истории канала из Telegram")
        asyncio.run(bt.ingest_channel_history(channel, days=days))

        _update(job_id, "сверка сигналов с рыночными данными (ccxt)")
        bt.run_backtest(channel)

        _update(job_id, "формирование отчёта")
        report = bt.build_report(channel)
        curve = bt.build_equity_curve(channel)
        db.save_channel_stats(channel, days, report, json.dumps(curve),
                               entry_timeout_hours=entry_timeout_hours,
                               max_hold_hours=max_hold_hours,
                               risk_per_trade_usd=risk_per_trade_usd)

        _finish(job_id, result={"report": report, "equity_curve": curve})
    except Exception as e:
        _finish(job_id, error=str(e))
