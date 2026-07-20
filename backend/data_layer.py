"""
Data Layer — OHLCV/тикеры с Bybit (linear) и Binance USDM + индикаторы.
По умолчанию Bybit; для монет только на Binance — exchange_id='binance'.
"""

import time
import threading
import ccxt
import pandas as pd

exchange = ccxt.bybit({
    'options': {'defaultType': 'linear'},
    'enableRateLimit': True,
    'timeout': 15000,
})

binance = ccxt.binanceusdm({
    'enableRateLimit': True,
    'timeout': 15000,
})

_EXCHANGES = {
    'bybit': exchange,
    'binance': binance,
}

CACHE_TTL = 180
_data_cache = {}


def api_call(func, *args, retries=3, delay=2, **kwargs):
    for i in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except (ccxt.NetworkError, ccxt.RequestTimeout,
                ccxt.ExchangeNotAvailable, ccxt.DDoSProtection) as e:
            if i < retries:
                time.sleep(delay * i)
            else:
                print(f"❌ {func.__name__}: {e}")
        except Exception as e:
            print(f"❌ {func.__name__}: {e}")
            return None
    return None


def get_exchange(exchange_id=None):
    """bybit | binance; неизвестный id → bybit."""
    if not exchange_id:
        return exchange
    return _EXCHANGES.get(str(exchange_id).lower().strip(), exchange)


def clean_cache():
    now = time.time()
    for s in [k for k, (t, _) in _data_cache.items() if now - t >= CACHE_TTL]:
        del _data_cache[s]


def _ticker_ok(ticker):
    return bool(ticker and ticker.get('last') is not None)


def parse_listed_on(raw):
    """'bybit,binance' | list → упорядоченный список id."""
    if isinstance(raw, (list, tuple)):
        parts = [str(x).lower().strip() for x in raw]
    elif raw:
        parts = [p.strip().lower() for p in str(raw).split(',')]
    else:
        parts = []
    out = []
    for p in parts:
        if p in ('bybit', 'binance') and p not in out:
            out.append(p)
    return out


def listings_label(listed_on) -> str:
    """Текст для TG/UI: где торгуется монета."""
    listed = parse_listed_on(listed_on)
    has_b = 'bybit' in listed
    has_n = 'binance' in listed
    if has_b and has_n:
        return 'Bybit и Binance Futures'
    if has_n and not has_b:
        return 'только Binance Futures'
    if has_b and not has_n:
        return 'только Bybit Futures'
    return 'Bybit Futures'


def probe_listings(symbol):
    """Проверяет обе биржи. Возвращает (listed_ids, preferred_id, ticker_on_preferred).

    preferred: Bybit если есть, иначе Binance. (None, None, None) если нигде нет.
    """
    listed = []
    tickers = {}
    for ex_id in ('bybit', 'binance'):
        ticker = api_call(get_exchange(ex_id).fetch_ticker, symbol)
        if _ticker_ok(ticker):
            listed.append(ex_id)
            tickers[ex_id] = ticker
    if not listed:
        return [], None, None
    preferred = 'bybit' if 'bybit' in listed else listed[0]
    return listed, preferred, tickers[preferred]


def resolve_listed_exchange(symbol):
    """Сначала Bybit, иначе Binance USDM. None если нигде нет тикера с last."""
    _, preferred, _ = probe_listings(symbol)
    return preferred


def fetch_data(symbol, exchange_id=None):
    ex = get_exchange(exchange_id)
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    d4h = api_call(ex.fetch_ohlcv, symbol, '4h', limit=120)
    d1h = api_call(ex.fetch_ohlcv, symbol, '1h', limit=100)
    d30m = api_call(ex.fetch_ohlcv, symbol, '30m', limit=150)
    if not d4h or not d1h or not d30m:
        return None
    df4h = pd.DataFrame(d4h, columns=cols)
    df1h = pd.DataFrame(d1h, columns=cols)
    df30m = pd.DataFrame(d30m, columns=cols)
    if len(df4h) < 60 or len(df1h) < 50 or len(df30m) < 80:
        return None
    return {'4h': df4h, '1h': df1h, '30m': df30m}


def fetch_data_cached(symbol, exchange_id=None):
    ex_id = (exchange_id or 'bybit').lower().strip()
    cache_key = f"data:{ex_id}:{symbol}"
    now = time.time()
    if cache_key in _data_cache:
        t, d = _data_cache[cache_key]
        if now - t < CACHE_TTL:
            return d
    # legacy key without exchange (старый кэш сканера)
    if ex_id == 'bybit' and symbol in _data_cache:
        t, d = _data_cache[symbol]
        if now - t < CACHE_TTL:
            return d
    d = fetch_data(symbol, exchange_id=ex_id)
    if d:
        _data_cache[cache_key] = (now, d)
    return d


def fetch_ticker(symbol, exchange_id=None):
    """Если exchange_id задан — только эта биржа. Иначе Bybit, затем Binance.
    Кэш 5с — чтобы /api/signals и трекер не долбили биржу."""
    ex_key = (exchange_id or 'any').lower().strip()
    cache_key = f"ticker:{ex_key}:{symbol}"
    now = time.time()
    hit = _data_cache.get(cache_key)
    if hit and now - hit[0] < 5:
        return hit[1]

    ticker = None
    if exchange_id:
        ticker = api_call(get_exchange(exchange_id).fetch_ticker, symbol)
        if not _ticker_ok(ticker):
            ticker = None
    else:
        for ex_id in ('bybit', 'binance'):
            ticker = api_call(get_exchange(ex_id).fetch_ticker, symbol)
            if _ticker_ok(ticker):
                break
            ticker = None

    if ticker:
        _data_cache[cache_key] = (now, ticker)
    return ticker


def fetch_candles_json(symbol, timeframe='1h', limit=60, exchange_id=None):
    """Свечи для графика на карточке сигнала (JSON-строка как в scanner)."""
    import json
    ex_id = (exchange_id or 'bybit').lower().strip()
    ex = get_exchange(ex_id)
    cache_key = f"candles:{ex_id}:{symbol}:{timeframe}:{limit}"
    now = time.time()
    hit = _data_cache.get(cache_key)
    # 15с — график на дашборде ближе к live, без шторма запросов
    if hit and now - hit[0] < 15:
        return hit[1]
    raw = api_call(ex.fetch_ohlcv, symbol, timeframe, limit=limit)
    if not raw:
        return None
    rows = [
        {"timestamp": int(c[0]), "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5]}
        for c in raw
    ]
    payload = json.dumps(rows)
    _data_cache[cache_key] = (now, payload)
    return payload


def fetch_ohlcv_raw(symbol, timeframe='1h', limit=500, exchange_id=None):
    """Сырые свечи [[ts_ms, o, h, l, c, v], ...] — для реконструкции реальной
    сделки (когда цена была на уровне входа)."""
    ex = get_exchange(exchange_id)
    return api_call(ex.fetch_ohlcv, symbol, timeframe, limit=limit)


def build_features(df):
    df = df.copy()
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))

    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs(),
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_trend'] = df['volume'].rolling(5).mean() / (df['volume'].rolling(20).mean() + 1e-10)

    up = df['high'].diff()
    dn = df['low'].diff().mul(-1)
    pdm = up.where((up > dn) & (up > 0), 0.0)
    mdm = dn.where((dn > up) & (dn > 0), 0.0)
    trs = tr.rolling(14).sum()
    pdi = 100 * pdm.rolling(14).sum() / (trs + 1e-10)
    mdi = 100 * mdm.rolling(14).sum() / (trs + 1e-10)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-10)
    df['adx'] = dx.rolling(14).mean()
    df['plus_di'] = pdi
    df['minus_di'] = mdi
    return df


def detect_regime(df):
    if len(df) < 20:
        return 'CHOP', 0
    last = df.iloc[-1]
    prev = df.iloc[-5]
    if pd.isna(last['atr']) or last['close'] == 0:
        return 'CHOP', 0
    atr_pct = last['atr'] / last['close']
    ema_slope = last['ema50'] - prev['ema50']
    adx = last['adx'] if not pd.isna(last['adx']) else 0
    pdi = last['plus_di'] if not pd.isna(last['plus_di']) else 0
    mdi = last['minus_di'] if not pd.isna(last['minus_di']) else 0
    if atr_pct < 0.003:
        return 'FLAT', adx
    if adx < 15:
        return 'CHOP', adx
    if ema_slope > 0 and last['close'] > last['ema50'] and pdi > mdi:
        return 'UPTREND', adx
    if ema_slope < 0 and last['close'] < last['ema50'] and mdi > pdi:
        return 'DOWNTREND', adx
    return 'CHOP', adx


CANDIDATES = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
    'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'ATOM/USDT', 'DOGE/USDT',
    'LINK/USDT', 'UNI/USDT', 'AAVE/USDT', 'ARB/USDT', 'OP/USDT',
    'FET/USDT', 'THETA/USDT', 'WLD/USDT', 'ICP/USDT',
    'SHIB/USDT', 'PEPE/USDT', 'FLOKI/USDT',
    'NEAR/USDT', 'ALGO/USDT',
    'FIL/USDT', 'SAND/USDT', 'ENJ/USDT',
    'LTC/USDT', 'BCH/USDT', 'ETC/USDT', 'TRX/USDT',
    'SUI/USDT', 'APT/USDT', 'INJ/USDT', 'TIA/USDT', 'SEI/USDT',
    'HBAR/USDT', 'STX/USDT', 'VET/USDT',
]


def get_active_symbols():
    return CANDIDATES


# ── Обзор рынка (Скринер) ────────────────────────────────────────
# Снапшот режимов по всем парам. Строится в фоновом потоке, потому что
# холодный проход по 39 парам занимает десятки секунд — HTTP-запрос
# не должен этого ждать. Пока снапшота нет, эндпоинт отдаёт "loading".

OVERVIEW_TTL = 180
_overview_state = {'ts': 0, 'data': None, 'building': False}
_overview_lock = threading.Lock()


def _build_market_overview():
    symbols = []
    for sym in CANDIDATES:
        data = fetch_data_cached(sym)
        if not data:
            continue
        df = build_features(data['1h'])
        regime, adx = detect_regime(df)
        symbols.append({'symbol': sym, 'regime': regime, 'adx': round(float(adx), 1)})
    up = sum(1 for s in symbols if s['regime'] == 'UPTREND')
    down = sum(1 for s in symbols if s['regime'] == 'DOWNTREND')
    btc = next((s for s in symbols if s['symbol'] == 'BTC/USDT'), None)
    return {
        'symbols': symbols,
        'btc_regime': btc['regime'] if btc else 'НЕТ ДАННЫХ',
        'uptrend_count': up,
        'downtrend_count': down,
        'chop_count': len(symbols) - up - down,
    }


def _refresh_overview():
    try:
        data = _build_market_overview()
        with _overview_lock:
            _overview_state['data'] = data
            _overview_state['ts'] = time.time()
    finally:
        with _overview_lock:
            _overview_state['building'] = False


def get_market_overview():
    """Текущий снапшот обзора рынка (может быть None, пока строится первый)."""
    with _overview_lock:
        stale = _overview_state['data'] is None or time.time() - _overview_state['ts'] >= OVERVIEW_TTL
        if stale and not _overview_state['building']:
            _overview_state['building'] = True
            threading.Thread(target=_refresh_overview, daemon=True).start()
        return _overview_state['data']


def fmt_price(p):
    if p >= 1000:
        return f"{p:.2f}"
    elif p >= 1:
        return f"{p:.3f}"
    elif p >= 0.01:
        return f"{p:.5f}"
    return f"{p:.7f}"