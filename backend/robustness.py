"""
Robustness — проверка стратегии «на прочность» перед тем, как верить бэктесту.

Автоматизация нашей методологии (см. историю проекта: PF разваливался от сдвига
таймаута на одну свечу; xsec показывал Sharpe 1.3, честная проверка дала 0.38).
Ни один одиночный бэктест-результат не считается доказательством, пока не пройдёт:

  1. walk-forward   — работает ли на последовательных отрезках, а не «в среднем за период»
  2. cost stress    — выживает ли при комиссии/проскальзывании x1.5 и x2
  3. parameter jitter — рушится ли от малых сдвигов параметров (таймаут, трейлинг)
  4. Monte-Carlo    — bootstrap перестановки сделок: разброс исходов и риск просадки
  5. Deflated Sharpe — поправка Sharpe на подбор параметров (Bailey & Lopez de Prado, 2014)

Реализация своя (формула DSR — из публичной статьи). Все симуляции гоняются по
ОДНИМ И ТЕМ ЖЕ предзагруженным свечам — честное сравнение и никакого спама биржи.

Вердикты обязательно честные: недостаток данных = «недостаточно данных»,
а не натянутый «passed».
"""

import math
import random
import threading
import time
import uuid

# ── Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014) ─────────

_EULER_GAMMA = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Обратная CDF нормального распределения (метод Acklam, достаточная точность)."""
    if p <= 0 or p >= 1:
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _moments(returns):
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / n
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd == 0:
        return mean, sd, 0.0, 3.0
    skew = sum((r - mean) ** 3 for r in returns) / (n * sd ** 3)
    kurt = sum((r - mean) ** 4 for r in returns) / (n * sd ** 4)
    return mean, sd, skew, kurt


def deflated_sharpe(returns, n_trials: int):
    """
    Вероятность [0..1], что истинный Sharpe > порога, ожидаемого от случайного
    подбора лучшего из n_trials вариантов. >= 0.95 — общепринятая планка «не артефакт».
    returns — список PnL по сделкам (единицы не важны, масштаб сокращается).
    """
    n = len(returns)
    if n < 10:
        return None  # честно: слишком мало сделок для статистики
    mean, sd, skew, kurt = _moments(returns)
    if sd == 0:
        return None
    sr = mean / sd  # per-trade Sharpe

    # Ожидаемый максимум Sharpe из n_trials случайных (E[max] аппроксимация)
    trials = max(2, n_trials)
    var_sr = 1.0 / n
    e_max = math.sqrt(var_sr) * (
        (1 - _EULER_GAMMA) * _norm_ppf(1 - 1.0 / trials)
        + _EULER_GAMMA * _norm_ppf(1 - 1.0 / (trials * math.e))
    )

    denom = math.sqrt(max(1e-12, (1 - skew * sr + (kurt - 1) / 4.0 * sr * sr) / (n - 1)))
    z = (sr - e_max) / denom
    return round(_norm_cdf(z), 4)


# ── Monte-Carlo bootstrap по сделкам ─────────────────────────────

def monte_carlo(trades_pnl_usdt, deposit: float, n_sims: int = 1000, seed: int = 42):
    """Перемешиваем порядок сделок (bootstrap с возвратом) — смотрим разброс
    итогового PnL и максимальной просадки. Отвечает на вопрос: результат
    держится на последовательности удачных сделок или устойчив к порядку?"""
    if len(trades_pnl_usdt) < 5:
        return None
    rng = random.Random(seed)
    finals, maxdds = [], []
    n = len(trades_pnl_usdt)
    for _ in range(n_sims):
        eq = deposit
        peak = deposit
        dd = 0.0
        for _ in range(n):
            eq += rng.choice(trades_pnl_usdt)
            peak = max(peak, eq)
            if peak > 0:
                dd = max(dd, (peak - eq) / peak * 100)
        finals.append((eq - deposit) / deposit * 100)
        maxdds.append(dd)
    finals.sort(); maxdds.sort()
    q = lambda arr, p: arr[min(len(arr) - 1, int(p * len(arr)))]
    return {
        "pnl_p5": round(q(finals, 0.05), 2),
        "pnl_p50": round(q(finals, 0.50), 2),
        "pnl_p95": round(q(finals, 0.95), 2),
        "dd_p95": round(q(maxdds, 0.95), 2),
        "prob_loss": round(sum(1 for f in finals if f < 0) / len(finals), 3),
    }


# ── Джобы (фоновое выполнение с прогрессом) ──────────────────────

_jobs: dict = {}
_jobs_lock = threading.Lock()
MAX_JOBS = 20


def create_job() -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        # не даём словарю расти бесконечно
        if len(_jobs) >= MAX_JOBS:
            oldest = sorted(_jobs.items(), key=lambda kv: kv[1]['created'])[0][0]
            del _jobs[oldest]
        _jobs[job_id] = {"status": "running", "progress": {"step": "старт", "done": 0, "total": 1},
                         "result": None, "error": None, "created": time.time()}
    return job_id


def get_job(job_id: str):
    with _jobs_lock:
        return _jobs.get(job_id)


def _update(job_id, step, done, total):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = {"step": step, "done": done, "total": total}


def _finish(job_id, result=None, error=None):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "failed" if error else "done"
            _jobs[job_id]["result"] = result
            _jobs[job_id]["error"] = error


# ── Основной прогон ──────────────────────────────────────────────

def run_robustness(job_id: str, run_one, fetch_raw, symbol: str, period_days: int,
                   deposit: float, commission: float, slippage: float):
    """
    run_one   — функция бэктеста (main._run_one), передаётся чтобы избежать циклического импорта
    fetch_raw — main.fetch_ohlcv_paginated
    """
    try:
        checks = []
        TOTAL_STEPS = 17  # 1 fetch + 1 base + 4 wf + 2 cost + 9 jitter (+MC/DSR мгновенны)
        step_n = 0

        # ── Данные один раз ──
        _update(job_id, "загрузка данных", step_n, TOTAL_STEPS)
        raw = fetch_raw(symbol, '1h', period_days)
        step_n += 1
        if not raw or len(raw) < 200:
            _finish(job_id, error="Недостаточно исторических данных для проверки")
            return

        def sim(candles=None, comm=None, slip=None, timeout=36, trail=0.8):
            return run_one(symbol, period_days, deposit,
                           comm if comm is not None else commission,
                           slip if slip is not None else slippage,
                           single_mode=False, timeframe='1h',
                           raw_candles=candles if candles is not None else raw,
                           btc_regimes={},  # без BTC-фильтра: одинаковые условия во всех прогонах
                           timeout_candles=timeout, trail_atr_mult=trail)

        # ── Базовый прогон ──
        _update(job_id, "базовый бэктест", step_n, TOTAL_STEPS)
        base = sim()
        step_n += 1
        if not base or base["total"] < 10:
            _finish(job_id, result={
                "verdict": "insufficient",
                "verdict_text": "Слишком мало сделок за период — статистически проверить нечего. "
                                "Возьми более длинный период.",
                "base": base, "checks": [],
            })
            return

        base_pf = base["profit_factor"]

        # ── 1. Walk-forward: 4 последовательных окна ──
        wf_windows = []
        n_win = 4
        win_len = len(raw) // n_win
        for w in range(n_win):
            _update(job_id, f"walk-forward {w+1}/{n_win}", step_n, TOTAL_STEPS)
            chunk = raw[w * win_len: (w + 1) * win_len]
            r = sim(candles=chunk)
            step_n += 1
            wf_windows.append({
                "window": w + 1,
                "trades": r["total"] if r else 0,
                "pnl_pct": r["total_pnl_pct"] if r else 0,
                "pf": r["profit_factor"] if r else None,
            })
        wf_with_trades = [w for w in wf_windows if w["trades"] >= 3]
        wf_positive = sum(1 for w in wf_with_trades if w["pnl_pct"] > 0)
        if len(wf_with_trades) < 2:
            wf_status = "insufficient"
        elif wf_positive >= max(2, len(wf_with_trades) - 1):
            wf_status = "passed"
        elif wf_positive * 2 >= len(wf_with_trades):
            wf_status = "warning"
        else:
            wf_status = "failed"
        checks.append({
            "key": "walk_forward", "name": "Walk-forward (4 окна)",
            "status": wf_status, "detail": wf_windows,
            "summary": f"{wf_positive}/{len(wf_with_trades)} окон с достаточными сделками в плюсе",
        })

        # ── 2. Cost stress ──
        stress_rows = []
        for label, mult in (("x1.5", 1.5), ("x2", 2.0)):
            _update(job_id, f"стресс по костам {label}", step_n, TOTAL_STEPS)
            r = sim(comm=commission * mult, slip=slippage * mult)
            step_n += 1
            stress_rows.append({
                "costs": label,
                "pnl_pct": r["total_pnl_pct"] if r else 0,
                "pf": r["profit_factor"] if r else None,
            })
        s15 = stress_rows[0]
        s20 = stress_rows[1]
        if s15["pf"] and s15["pf"] >= 1.0 and s20["pf"] and s20["pf"] >= 0.9:
            cost_status = "passed"
        elif s15["pf"] and s15["pf"] >= 0.9:
            cost_status = "warning"
        else:
            cost_status = "failed"
        checks.append({
            "key": "cost_stress", "name": "Стресс по комиссии/проскальзыванию",
            "status": cost_status, "detail": stress_rows,
            "summary": f"PF при костах x1.5: {s15['pf']}, x2: {s20['pf']}",
        })

        # ── 3. Parameter jitter (таймаут x трейлинг) ──
        jitter_rows = []
        for timeout in (30, 36, 42):
            for trail in (0.6, 0.8, 1.0):
                _update(job_id, f"jitter t={timeout} trail={trail}", step_n, TOTAL_STEPS)
                if timeout == 36 and trail == 0.8:
                    r = base  # базовый уже есть
                else:
                    r = sim(timeout=timeout, trail=trail)
                step_n += 1
                jitter_rows.append({
                    "timeout": timeout, "trail": trail,
                    "pnl_pct": r["total_pnl_pct"] if r else 0,
                    "pf": r["profit_factor"] if r else None,
                })
        pfs = [j["pf"] for j in jitter_rows if j["pf"]]
        if pfs:
            pf_min, pf_max = min(pfs), max(pfs)
            spread = (pf_max - pf_min) / base_pf if base_pf > 0 else 99
            profitable = sum(1 for j in jitter_rows if j["pnl_pct"] > 0)
            if spread <= 0.35 and profitable >= 7:
                jit_status = "passed"
            elif profitable >= 5:
                jit_status = "warning"
            else:
                jit_status = "failed"
            jit_summary = (f"PF от {pf_min} до {pf_max} по 9 вариантам "
                           f"(разброс {round(spread*100)}% от базового), в плюсе {profitable}/9")
        else:
            jit_status = "insufficient"
            jit_summary = "Мало данных"
        checks.append({
            "key": "parameter_jitter", "name": "Устойчивость к сдвигу параметров",
            "status": jit_status, "detail": jitter_rows, "summary": jit_summary,
        })

        # ── 4. Monte-Carlo ──
        pnls = [t["pnl_usdt"] for t in base["trades"]]
        mc = monte_carlo(pnls, deposit)
        if mc:
            if mc["prob_loss"] <= 0.2:
                mc_status = "passed"
            elif mc["prob_loss"] <= 0.4:
                mc_status = "warning"
            else:
                mc_status = "failed"
            mc_summary = (f"Вероятность убытка {round(mc['prob_loss']*100)}%, "
                          f"итог от {mc['pnl_p5']}% до {mc['pnl_p95']}%, просадка p95 {mc['dd_p95']}%")
        else:
            mc_status = "insufficient"
            mc_summary = "Мало сделок"
        checks.append({
            "key": "monte_carlo", "name": "Monte-Carlo (1000 перестановок сделок)",
            "status": mc_status, "detail": mc, "summary": mc_summary,
        })

        # ── 5. Deflated Sharpe ──
        # n_trials = 9 вариантов jitter — честный учёт того, что параметры подбирались
        dsr = deflated_sharpe(pnls, n_trials=9)
        if dsr is None:
            dsr_status = "insufficient"
            dsr_summary = "Меньше 10 сделок — DSR не считается"
        elif dsr >= 0.95:
            dsr_status = "passed"
            dsr_summary = f"DSR {dsr} — эдж вряд ли артефакт подбора"
        elif dsr >= 0.7:
            dsr_status = "warning"
            dsr_summary = f"DSR {dsr} — уверенности мало, возможен артефакт подбора"
        else:
            dsr_status = "failed"
            dsr_summary = f"DSR {dsr} — результат неотличим от удачного подбора параметров"
        checks.append({
            "key": "deflated_sharpe", "name": "Deflated Sharpe (поправка на подбор)",
            "status": dsr_status, "detail": {"dsr": dsr}, "summary": dsr_summary,
        })

        # ── Вердикт ──
        statuses = [c["status"] for c in checks]
        fails = statuses.count("failed")
        warns = statuses.count("warning")
        insuf = statuses.count("insufficient")
        if insuf >= 3:
            verdict, verdict_text = "insufficient", (
                "Данных мало для уверенного вывода. Это не приговор стратегии — "
                "возьми более длинный период и больше сделок.")
        elif fails == 0 and warns <= 1:
            verdict, verdict_text = "robust", (
                "Результат устойчив: держится на разных отрезках, выживает при повышенных костах "
                "и не рушится от сдвига параметров. Это НЕ гарантия будущей прибыли — "
                "только признак, что бэктест не является явным артефактом.")
        elif fails <= 1:
            verdict, verdict_text = "fragile", (
                "Результат частично устойчив, но есть слабые места (смотри проверки ниже). "
                "Доверять такому бэктесту деньги рано — нужен дальран.")
        else:
            verdict, verdict_text = "artifact", (
                "Результат похож на артефакт: он рассыпается при честных проверках. "
                "Красивая итоговая цифра, скорее всего, следствие удачного подбора "
                "параметров или везучего отрезка истории.")

        _finish(job_id, result={
            "verdict": verdict,
            "verdict_text": verdict_text,
            "base": {
                "total": base["total"], "winrate": base["winrate"],
                "total_pnl_pct": base["total_pnl_pct"], "profit_factor": base_pf,
                "max_drawdown": base["max_drawdown"],
            },
            "checks": checks,
            "symbol": symbol,
            "period_days": period_days,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        _finish(job_id, error=f"Ошибка проверки: {e}")
