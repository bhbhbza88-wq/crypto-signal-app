"""
Cross-Sectional Momentum — рыночно-нейтральная long-short стратегия.

Идея (валидировано на 5 годах, каждый год в плюсе включая медвежий 2022):
  - Раз в неделю ранжируем вселенную ликвидных монет по доходности за LOOKBACK дней.
  - Лонгуем топ-N (сильнейшие), шортим худшие-N (слабейшие), equal weight.
  - Портфель долларово-нейтральный (50% лонг / 50% шорт) — не зависит от того,
    растёт рынок или падает.

Это ОТДЕЛЬНАЯ стратегия от сигнального сканера (momentum). Здесь нет TP/SL —
выход происходит на ребалансе, когда монета выпадает из топа/дна рейтинга.

Параметры выбраны по валидации (Sharpe ~1.3, устойчив к фазе/lookback/N):
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

# ── Вселенная: 30 ликвидных монет (отобраны по капитализации a-priori) ──
XSEC_UNIVERSE = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
    'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT', 'DOT/USDT', 'LINK/USDT',
    'TRX/USDT', 'LTC/USDT', 'BCH/USDT', 'ATOM/USDT', 'UNI/USDT',
    'NEAR/USDT', 'AAVE/USDT', 'ICP/USDT', 'FIL/USDT', 'ETC/USDT',
    'APT/USDT', 'ARB/USDT', 'OP/USDT', 'INJ/USDT', 'SUI/USDT',
    'SEI/USDT', 'TIA/USDT', 'FET/USDT', 'ALGO/USDT', 'HBAR/USDT',
]

XSEC_LOOKBACK_DAYS = 30   # окно расчёта momentum
XSEC_N             = 3    # монет в каждую сторону (топ-3 лонг / худшие-3 шорт)
XSEC_REBAL_DAYS    = 7    # ребаланс раз в неделю
XSEC_DEPOSIT       = 1000 # стартовый бумажный депозит

# Volatility-managed momentum (Barroso-Santa-Clara): экспозиция ~ 1/недавняя_vol.
# Валидировано: Sharpe 0.38->0.43, медиана по фазам 0.18->0.30, просадка -36%->-30%.
# Мягкий target=2% выбран как самый консервативный (наименьшая просадка).
XSEC_VOL_TARGET = 2.0   # целевая волатильность периода, %
XSEC_VOL_CAP    = 2.0   # макс. плечо на нейтральный портфель
XSEC_VOL_WINDOW = 8     # окно оценки волатильности (периодов)

_daily_cache = {'ts': 0.0, 'data': None}
_CACHE_TTL = 1800  # 30 мин


def fetch_universe_daily(days=120):
    """Дневные close по всей вселенной. Возвращает DataFrame (timestamp index × symbol)."""
    now = time.time()
    if _daily_cache['data'] is not None and now - _daily_cache['ts'] < _CACHE_TTL:
        return _daily_cache['data']

    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    closes = {}
    for sym in XSEC_UNIVERSE:
        try:
            raw = api_call(exchange.fetch_ohlcv, sym, '1d', limit=days + 5)
        except Exception:
            raw = None
        if raw and len(raw) >= XSEC_LOOKBACK_DAYS + 2:
            df = pd.DataFrame(raw, columns=cols)
            closes[sym] = df.set_index('timestamp')['close']
    if not closes:
        return None
    px = pd.DataFrame(closes).sort_index().ffill()
    _daily_cache.update({'ts': now, 'data': px})
    return px


def compute_momentum_ranking(px=None):
    """
    Рейтинг монет по доходности за LOOKBACK дней (на закрытых свечах).
    Возвращает Series: symbol -> momentum %, отсортированный по убыванию.
    """
    if px is None:
        px = fetch_universe_daily()
    if px is None or len(px) < XSEC_LOOKBACK_DAYS + 1:
        return None
    # последняя ЗАКРЫТАЯ свеча — предпоследняя строка (последняя может быть неполной)
    last_closed = -2 if len(px) >= XSEC_LOOKBACK_DAYS + 2 else -1
    cur = px.iloc[last_closed]
    past = px.iloc[last_closed - XSEC_LOOKBACK_DAYS]
    avail = [c for c in px.columns if not pd.isna(cur[c]) and not pd.isna(past[c]) and past[c] > 0]
    if len(avail) < 2 * XSEC_N:
        return None
    mom = (cur[avail] / past[avail] - 1.0) * 100
    return mom.sort_values(ascending=False)


def compute_target_portfolio(px=None):
    """
    Целевой портфель: топ-N в лонг, худшие-N в шорт.
    Возвращает dict: {'longs': [...], 'shorts': [...], 'ranking': {sym: mom%}}.
    """
    ranking = compute_momentum_ranking(px)
    if ranking is None:
        return None
    longs = list(ranking.index[:XSEC_N])
    shorts = list(ranking.index[-XSEC_N:])
    return {
        'longs': longs,
        'shorts': shorts,
        'ranking': {k: round(float(v), 2) for k, v in ranking.items()},
    }


def get_current_prices(symbols):
    """Текущие цены (last) по списку символов."""
    out = {}
    for sym in symbols:
        try:
            t = api_call(exchange.fetch_ticker, sym) or {}
            out[sym] = t.get('last')
        except Exception:
            out[sym] = None
    return out


# ══════════════════════════════════════════════════════════════════
# БУМАЖНАЯ ТОРГОВЛЯ (PAPER) — ребаланс раз в неделю
# ══════════════════════════════════════════════════════════════════
def _now_ms():
    return int(time.time() * 1000)


def should_rebalance():
    """Прошло ли REBAL дней с последнего ребаланса."""
    st = db.xsec_get_state()
    if not st or not st.get('last_rebalance_ts'):
        return True
    elapsed_days = (_now_ms() - st['last_rebalance_ts']) / 86400000
    return elapsed_days >= XSEC_REBAL_DAYS


def _position_pnl_pct(side, entry, price):
    if not entry or not price:
        return 0.0
    chg = (price - entry) / entry * 100
    return chg if side == 'long' else -chg


def _parse_positions_field(raw):
    """
    Разбирает positions_json. Поддерживает оба формата:
      - старый: список позиций (до vol-management)
      - новый: {positions: [...], vol_window: [...], scale: X}
    Возвращает (positions, vol_window, scale).
    """
    if not raw:
        return [], [], 1.0
    data = json.loads(raw)
    if isinstance(data, list):
        return data, [], 1.0
    return data.get('positions', []), data.get('vol_window', []), data.get('scale', 1.0)


def _compute_scale(vol_window):
    """Экспозиция = min(CAP, TARGET / недавняя_волатильность). Без истории — 1.0."""
    if len(vol_window) < XSEC_VOL_WINDOW:
        return 1.0
    v = float(np.std(vol_window[-XSEC_VOL_WINDOW:]))
    if v <= 1e-6:
        return XSEC_VOL_CAP
    return float(min(XSEC_VOL_CAP, XSEC_VOL_TARGET / v))


def rebalance(force=False):
    """
    Выполняет бумажный ребаланс:
      1) Закрывает текущие позиции по live-цене -> период-доходность портфеля.
      2) Открывает новый целевой портфель (топ-N лонг / худшие-N шорт).
      3) Сохраняет состояние и пишет в лог.
    Долларово-нейтрально: 50% капитала в лонг, 50% в шорт, equal weight внутри ноги.
    """
    if not force and not should_rebalance():
        return {'rebalanced': False, 'reason': 'ещё не время'}

    target = compute_target_portfolio()
    if target is None:
        return {'rebalanced': False, 'reason': 'нет данных для рейтинга'}

    st = db.xsec_get_state()
    equity = st['equity'] if st else float(XSEC_DEPOSIT)
    old_positions, vol_window, old_scale = _parse_positions_field(
        st['positions_json'] if st else None)

    # 1) сырая (без плеча) доходность периода по старым позициям + издержки оборота
    raw_gross = 0.0
    period_ret = 0.0  # фактическая (с учётом плеча), идёт в equity
    if old_positions:
        prices = get_current_prices([p['symbol'] for p in old_positions])
        long_rets, short_rets = [], []
        for p in old_positions:
            pnl = _position_pnl_pct(p['side'], p['entry'], prices.get(p['symbol']))
            (long_rets if p['side'] == 'long' else short_rets).append(pnl)
        rl = np.mean(long_rets) if long_rets else 0.0
        rs_dir = np.mean(short_rets) if short_rets else 0.0
        raw_gross = 0.5 * rl + 0.5 * rs_dir   # сырая доходность нейтрального портфеля
        # издержки оборота (как в валидированном бэктесте)
        old_longs  = {p['symbol'] for p in old_positions if p['side'] == 'long'}
        old_shorts = {p['symbol'] for p in old_positions if p['side'] == 'short'}
        turn = (len(set(target['longs']).symmetric_difference(old_longs)) +
                len(set(target['shorts']).symmetric_difference(old_shorts)))
        turnover_cost = turn * (1.0 / XSEC_N) * (COMM + SLIP) * 100
        # плечо периода было задано на ПРОШЛОМ ребалансе (old_scale)
        period_ret = old_scale * (raw_gross - turnover_cost)
        equity *= (1 + period_ret / 100)
        # обновляем окно волатильности СЫРЫМИ доходностями (vol-management)
        vol_window = (vol_window + [raw_gross])[-(XSEC_VOL_WINDOW * 2):]

    # 2) плечо на новый период — по недавней волатильности
    new_scale = _compute_scale(vol_window)

    # 3) новый портфель по текущим ценам
    new_symbols = target['longs'] + target['shorts']
    entry_prices = get_current_prices(new_symbols)
    new_positions = []
    for s in target['longs']:
        new_positions.append({'symbol': s, 'side': 'long',  'entry': entry_prices.get(s),
                              'mom': target['ranking'].get(s)})
    for s in target['shorts']:
        new_positions.append({'symbol': s, 'side': 'short', 'entry': entry_prices.get(s),
                              'mom': target['ranking'].get(s)})

    ts = _now_ms()
    state_blob = json.dumps({'positions': new_positions, 'vol_window': vol_window, 'scale': new_scale})
    db.xsec_save_state(round(equity, 2), ts, state_blob)
    db.xsec_add_log(ts, round(equity, 2), round(period_ret, 3),
                    json.dumps(target['longs']), json.dumps(target['shorts']))
    print(f"🔄 XSEC ребаланс | equity={equity:.1f} | период={period_ret:+.2f}% | плечо x{new_scale:.2f} | "
          f"L:{[s.replace('/USDT','') for s in target['longs']]} "
          f"S:{[s.replace('/USDT','') for s in target['shorts']]}")
    return {'rebalanced': True, 'equity': round(equity, 2), 'period_return_pct': round(period_ret, 3),
            'scale': round(new_scale, 2), 'longs': target['longs'], 'shorts': target['shorts']}


def get_status():
    """Снимок для дашборда: текущий портфель с live-PnL, equity, кривая."""
    st = db.xsec_get_state()
    if not st:
        return {
            'initialized': False, 'equity': float(XSEC_DEPOSIT), 'deposit': XSEC_DEPOSIT,
            'positions': [], 'last_rebalance_ts': None, 'next_rebalance_in_days': 0,
            'lookback_days': XSEC_LOOKBACK_DAYS, 'n_per_side': XSEC_N, 'rebal_days': XSEC_REBAL_DAYS,
        }
    positions, _vw, scale = _parse_positions_field(st.get('positions_json'))
    prices = get_current_prices([p['symbol'] for p in positions]) if positions else {}
    pos_out, long_pnls, short_pnls = [], [], []
    for p in positions:
        price = prices.get(p['symbol'])
        pnl = _position_pnl_pct(p['side'], p['entry'], price)
        (long_pnls if p['side'] == 'long' else short_pnls).append(pnl)
        pos_out.append({**p, 'price': price, 'pnl_pct': round(pnl, 2)})
    raw_unreal = 0.5 * (np.mean(long_pnls) if long_pnls else 0) + 0.5 * (np.mean(short_pnls) if short_pnls else 0)
    last_ts = st.get('last_rebalance_ts')
    next_in = max(0, XSEC_REBAL_DAYS - (_now_ms() - last_ts) / 86400000) if last_ts else 0
    return {
        'initialized': True,
        'equity': st['equity'],
        'deposit': XSEC_DEPOSIT,
        'unrealized_pct': round(raw_unreal * scale, 2),  # с учётом текущего плеча
        'leverage': round(scale, 2),
        'positions': pos_out,
        'last_rebalance_ts': last_ts,
        'next_rebalance_in_days': round(next_in, 1),
        'lookback_days': XSEC_LOOKBACK_DAYS, 'n_per_side': XSEC_N, 'rebal_days': XSEC_REBAL_DAYS,
        'vol_target': XSEC_VOL_TARGET, 'vol_cap': XSEC_VOL_CAP,
    }
