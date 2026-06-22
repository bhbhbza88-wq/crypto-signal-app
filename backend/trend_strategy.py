"""
Trend-Following — позиционная стратегия "в рынке / в кэше" по золотому кресту.

Идея (валидировано на 5 годах, реальные издержки, walk-forward, весь грид параметров,
честно по каждой монете):
  - На топ-5 ликвидных монетах: EMA50 > EMA200 -> держим (лонг). Иначе -> кэш.
  - Это НЕ источник альфы — это снижение риска: в среднем идёт вровень с buy&hold
    в обычные годы, но сильно меньше теряет в крахи (2022: -64% holding vs гораздо
    мягче с трендом). Топ-5: ROI +161% / Sharpe 0.73 / maxDD -33% за 5 лет
    (buy&hold BTC: +91% / 0.51 / -77%).
  - ОЧЕНЬ редкие сделки по дизайну (~7/год на 5 монет, ~раз в 7 недель) — это
    и есть причина, почему он работает: мало шума, мало издержек. Не нужно
    форсировать частоту — на полной вселенной 39 монет результат УЖЕ ХУЖЕ
    buy&hold (whipsaw на шумных альтах). Топ-5 — проверенный предел.

Это ОТДЕЛЬНАЯ стратегия от momentum-сканера (который остаётся "высокочастотной"
стороной) и от cross-sectional long-short. Здесь нет TP/SL — выход при
пересечении EMA вниз. Проверяется раз в день (тренд не меняется внутри дня).
"""
import time
import json
import datetime
import pandas as pd
import numpy as np

from data_layer import exchange, api_call
import database as db

COMM = 0.055 / 100
SLIP = 0.10 / 100

TREND_UNIVERSE = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT']
TREND_EMA_FAST = 50
TREND_EMA_SLOW = 200
TREND_DEPOSIT = 1000   # бумажный депозит на каждую монету (independent allocation)

_daily_cache = {'ts': 0.0, 'data': {}}
_CACHE_TTL = 3600 * 4  # 4 часа — тренд меняется редко, не нужно дёргать биржу часто


def fetch_daily_history(symbol, days=400):
    """Дневные свечи — нужно >= EMA_SLOW+несколько для надёжного сигнала."""
    now = time.time()
    cache = _daily_cache['data'].get(symbol)
    if cache is not None and now - _daily_cache['ts'] < _CACHE_TTL:
        return cache
    try:
        raw = api_call(exchange.fetch_ohlcv, symbol, '1d', limit=days)
    except Exception:
        raw = None
    if not raw or len(raw) < TREND_EMA_SLOW + 5:
        return None
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df = pd.DataFrame(raw, columns=cols)
    _daily_cache['data'][symbol] = df
    _daily_cache['ts'] = now
    return df


def compute_signal(symbol):
    """Возвращает (in_trend: bool, close, ema_fast, ema_slow) по последней ЗАКРЫТОЙ свече."""
    df = fetch_daily_history(symbol)
    if df is None or len(df) < TREND_EMA_SLOW + 2:
        return None
    close = df['close']
    ef = close.ewm(span=TREND_EMA_FAST, adjust=False).mean()
    es = close.ewm(span=TREND_EMA_SLOW, adjust=False).mean()
    # последняя закрытая свеча — предпоследняя строка (последняя может быть неполной)
    i = -2 if len(df) >= TREND_EMA_SLOW + 3 else -1
    return {
        'in_trend': bool(ef.iloc[i] > es.iloc[i]),
        'close': float(close.iloc[i]),
        'ema_fast': float(ef.iloc[i]),
        'ema_slow': float(es.iloc[i]),
    }


def compute_all_signals():
    out = {}
    for sym in TREND_UNIVERSE:
        sig = compute_signal(sym)
        if sig:
            out[sym] = sig
    return out


def get_current_prices(symbols):
    out = {}
    for sym in symbols:
        try:
            t = api_call(exchange.fetch_ticker, sym) or {}
            out[sym] = t.get('last')
        except Exception:
            out[sym] = None
    return out


# ══════════════════════════════════════════════════════════════════
# БУМАЖНАЯ ТОРГОВЛЯ — проверка раз в день (тренд не меняется внутри дня)
# ══════════════════════════════════════════════════════════════════
def _now_ms():
    return int(time.time() * 1000)


def _tg(coro_factory):
    """Безопасно отправить Telegram-уведомление из синхронного кода."""
    try:
        import asyncio, telegram_bot
        loop = asyncio.new_event_loop()
        loop.run_until_complete(coro_factory(telegram_bot))
        loop.close()
    except Exception as e:
        print(f"[trend telegram] {e}")


def _load_positions():
    st = db.trend_get_state()
    if not st or not st.get('positions_json'):
        return {}
    return json.loads(st['positions_json'])


def tick():
    """
    Раз в день (вызывается из scanner) — для каждой монеты:
      - если сигнал стал in_trend и позиции нет -> открыть
      - если сигнал стал не-in_trend и позиция есть -> закрыть, записать в лог
    """
    positions = _load_positions()
    signals = compute_all_signals()
    if not signals:
        return

    changed = False
    for sym, sig in signals.items():
        has_pos = sym in positions
        if sig['in_trend'] and not has_pos:
            positions[sym] = {'entry': sig['close'], 'opened_at': _now_ms()}
            db.add_event(sym, 'trend_enter', f"Trend-Following: вход (EMA{TREND_EMA_FAST}>{TREND_EMA_SLOW}) @ {sig['close']:.4f}")
            _tg(lambda tg, s=sym, p=sig['close']: tg.notify_trend_signal(s, 'enter', p))
            changed = True
        elif not sig['in_trend'] and has_pos:
            entry = positions[sym]['entry']
            pnl_pct = (sig['close'] - entry) / entry * 100 - (COMM + SLIP) * 100
            db.trend_add_log(_now_ms(), sym, entry, sig['close'], round(pnl_pct, 3))
            db.add_event(sym, 'trend_exit', f"Trend-Following: выход @ {sig['close']:.4f} ({pnl_pct:+.1f}%)")
            _tg(lambda tg, s=sym, p=sig['close'], pn=pnl_pct: tg.notify_trend_signal(s, 'exit', p, pn))
            del positions[sym]
            changed = True

    # всегда обновляем last_check_ts (чтобы дневной гейт в scanner работал),
    # позиции сохраняем актуальные
    db.trend_save_state(_now_ms(), json.dumps(positions))


# Вселенная для расчёта breadth (доля монет в аптренде) — 30 ликвидных монет.
BREADTH_UNIVERSE = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
    'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT', 'DOT/USDT', 'LINK/USDT',
    'TRX/USDT', 'LTC/USDT', 'BCH/USDT', 'ATOM/USDT', 'UNI/USDT',
    'NEAR/USDT', 'AAVE/USDT', 'ICP/USDT', 'FIL/USDT', 'ETC/USDT',
    'APT/USDT', 'ARB/USDT', 'OP/USDT', 'INJ/USDT', 'SUI/USDT',
    'SEI/USDT', 'TIA/USDT', 'FET/USDT', 'ALGO/USDT', 'HBAR/USDT',
]
PHASE_CONFIRM_DAYS = 5  # подтверждение фазы (анти-whipsaw) — валидировано


def _compute_breadth(btc_index):
    """Доля монет вселенной выше своей 100-дневной EMA, выровнено по датам BTC."""
    fracs = []
    cols = {}
    for s in BREADTH_UNIVERSE:
        df = fetch_daily_history(s)
        if df is None:
            continue
        c = df.set_index('timestamp')['close']
        cols[s] = (c > c.ewm(span=100, adjust=False).mean()).astype(float)
    if not cols:
        return None
    breadth = pd.DataFrame(cols).mean(axis=1)
    return breadth.reindex(btc_index).ffill()


def get_market_phase():
    """
    Индикатор фазы рынка (UPTREND / DOWNTREND / SIDEWAYS) — ТОЛЬКО для отображения.
    Не управляет капиталом ни в одной стратегии (авто-переключение протестировано
    и отклонено: оно ухудшало результат).

    Детектор подобран по предсказательной силе (разделение будущих доходностей
    BTC по фазам): консенсус 4 сигналов + подтверждение 5 дней. Спред будущей
    доходности UP-DOWN = +4.0% за 20д, правильный порядок UP>SIDE>DOWN,
    устойчив (~34 смены фазы за 5 лет вместо 150 у сырого консенсуса).
    """
    df = fetch_daily_history('BTC/USDT')
    if df is None or len(df) < TREND_EMA_SLOW + 2:
        return None
    close = df['close'].reset_index(drop=True)
    ts = df['timestamp'].reset_index(drop=True)

    e50 = close.ewm(span=50, adjust=False).mean()
    e200 = close.ewm(span=200, adjust=False).mean()
    mom60 = close / close.shift(60) - 1
    breadth = _compute_breadth(ts)
    if breadth is None:
        return None
    breadth = breadth.reset_index(drop=True)

    # консенсус 4 голосов risk-on -> сырая фаза
    score = ((e50 > e200).astype(int) + (close > e200).astype(int)
             + (mom60 > 0).astype(int) + (breadth > 0.55).astype(int))
    raw = pd.Series('SIDEWAYS', index=close.index)
    raw[score >= 3] = 'UPTREND'
    raw[score <= 1] = 'DOWNTREND'

    # подтверждение N дней (анти-whipsaw): меняем фазу только если держится >= N подряд
    committed = 'SIDEWAYS'; run_val = None; run = 0
    committed_series = []
    for v in raw:
        if v == run_val:
            run += 1
        else:
            run_val = v; run = 1
        if run >= PHASE_CONFIRM_DAYS:
            committed = v
        committed_series.append(committed)

    i = len(close) - 2 if len(close) >= 3 else len(close) - 1  # последняя закрытая свеча
    phase = committed_series[i]
    return {
        'phase': phase,
        'btc_close': round(float(close.iloc[i]), 2),
        'ema_fast': round(float(e50.iloc[i]), 2),
        'ema_slow': round(float(e200.iloc[i]), 2),
        'momentum_60d_pct': round(float(mom60.iloc[i] * 100), 2),
        'breadth_pct': round(float(breadth.iloc[i] * 100), 1),
        'risk_on_score': int(score.iloc[i]),
        'note': 'Только информационно — не переключает стратегии (проверено и отклонено)',
    }


def check_phase_change():
    """
    Сравнивает текущую фазу с последней зафиксированной (через таблицу events).
    При смене — пишет событие и шлёт Telegram. Вызывается из scanner раз в день.
    """
    cur = get_market_phase()
    if not cur:
        return
    # последняя зафиксированная фаза — из событий kind='phase_change'
    last_phase = None
    for ev in db.load_events(limit=200):
        if ev.get('kind') == 'phase_change':
            last_phase = (ev.get('message') or '').strip()
            break
    if cur['phase'] == last_phase:
        return  # без изменений
    db.add_event('BTC/USDT', 'phase_change', cur['phase'])
    if last_phase is not None:  # не шлём на самый первый запуск (нет "было")
        _tg(lambda tg, o=last_phase, n=cur['phase'], d=cur: tg.notify_market_phase(o, n, d))


def get_status():
    """Снимок для дашборда: открытые позиции с live-PnL + сигналы по всей вселенной."""
    positions = _load_positions()
    prices = get_current_prices(list(positions.keys())) if positions else {}
    pos_out = []
    for sym, p in positions.items():
        price = prices.get(sym)
        pnl = ((price - p['entry']) / p['entry'] * 100) if price and p['entry'] else 0.0
        pos_out.append({'symbol': sym, 'entry': p['entry'], 'price': price,
                        'pnl_pct': round(pnl, 2), 'opened_at': p.get('opened_at')})

    signals = compute_all_signals()
    sig_out = [{'symbol': s, 'in_trend': v['in_trend'], 'close': v['close'],
               'ema_fast': round(v['ema_fast'], 4), 'ema_slow': round(v['ema_slow'], 4),
               'distance_pct': round((v['ema_fast'] - v['ema_slow']) / v['ema_slow'] * 100, 2)}
              for s, v in signals.items()]

    log = db.trend_load_log(limit=200)
    closed_pnls = [r['pnl_pct'] for r in log]
    total_pnl = sum(closed_pnls)
    wins = sum(1 for p in closed_pnls if p > 0)

    return {
        'positions': pos_out,
        'signals': sig_out,
        'universe_size': len(TREND_UNIVERSE),
        'ema_fast': TREND_EMA_FAST, 'ema_slow': TREND_EMA_SLOW,
        'closed_trades': len(log),
        'wins': wins,
        'total_realized_pnl_pct': round(total_pnl, 2),
    }
