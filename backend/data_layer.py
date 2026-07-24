"""
Data Layer — OHLCV/тикеры: Bybit, Binance USDM, Bitunix, OKX, Bitget, BingX + индикаторы.
По умолчанию Bybit; иначе exchange_id из списка venues.
"""

import os
import time
import threading
import ccxt
import pandas as pd

import bitunix_client
import futures_venues

exchange = ccxt.bybit({
    'options': {'defaultType': 'linear'},
    'enableRateLimit': True,
    'timeout': 15000,
})

binance = ccxt.binanceusdm({
    'enableRateLimit': True,
    'timeout': 15000,
})

okx = futures_venues.build_okx()
bitget = futures_venues.build_bitget()
bingx = futures_venues.build_bingx()

_EXCHANGES = {
    'bybit': exchange,
    'binance': binance,
    'bitunix': bitunix_client.bitunix,
    'okx': okx,
    'bitget': bitget,
    'bingx': bingx,
}

# Порядок предпочтения при листинге на нескольких биржах
_EXCHANGE_PREFERENCE = ('bybit', 'binance', 'okx', 'bitget', 'bingx', 'bitunix')
_KNOWN_EXCHANGES = frozenset(_EXCHANGE_PREFERENCE)
_EXCHANGE_LABELS = {
    'bybit': 'Bybit',
    'binance': 'Binance',
    'okx': 'OKX',
    'bitget': 'Bitget',
    'bingx': 'BingX',
    'bitunix': 'Bitunix',
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
    """bybit | binance | okx | bitget | bingx | bitunix; неизвестный id → bybit."""
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
    """'bybit,binance,bitunix' | list → упорядоченный список id."""
    if isinstance(raw, (list, tuple)):
        parts = [str(x).lower().strip() for x in raw]
    elif raw:
        parts = [p.strip().lower() for p in str(raw).split(',')]
    else:
        parts = []
    out = []
    for p in parts:
        if p in _KNOWN_EXCHANGES and p not in out:
            out.append(p)
    return out


def listings_label(listed_on) -> str:
    """Текст для TG/UI: где торгуется монета."""
    listed = parse_listed_on(listed_on)
    if not listed:
        return 'Bybit Futures'
    labels = [_EXCHANGE_LABELS[x] for x in listed if x in _EXCHANGE_LABELS]
    if len(labels) == 1:
        return f'только {labels[0]} Futures'
    if len(labels) == 2:
        return f'{labels[0]} и {labels[1]} Futures'
    return ' · '.join(labels) + ' Futures'


def _venue_may_have(ex_id: str, symbol: str) -> bool:
    """Быстрый precheck по кэшу рынков (без ticker), если умеем."""
    ex = get_exchange(ex_id)
    if hasattr(ex, 'has_symbol'):
        try:
            return bool(ex.has_symbol(symbol))
        except Exception:
            return True
    if ex_id == 'bitunix':
        try:
            return bitunix_client.has_symbol(symbol)
        except Exception:
            return True
    return True


def probe_listings(symbol):
    """Проверяет все venues. (listed_ids, preferred_id, ticker).

    preferred по _EXCHANGE_PREFERENCE. ([], None, None) если нигде нет.
    """
    listed = []
    tickers = {}
    for ex_id in _EXCHANGE_PREFERENCE:
        if not _venue_may_have(ex_id, symbol):
            continue
        ticker = api_call(get_exchange(ex_id).fetch_ticker, symbol)
        if _ticker_ok(ticker):
            listed.append(ex_id)
            tickers[ex_id] = ticker
    if not listed:
        return [], None, None
    preferred = next((e for e in _EXCHANGE_PREFERENCE if e in listed), listed[0])
    return listed, preferred, tickers[preferred]


def resolve_listed_exchange(symbol):
    """Preferred venue или None."""
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
        for ex_id in _EXCHANGE_PREFERENCE:
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


def get_exchange_futures_symbols(exchange_id: str, force: bool = False) -> list[str]:
    """USDT-M / swap символы биржи в формате BTC/USDT."""
    ex_id = (exchange_id or "").lower().strip()
    try:
        if ex_id == "bitunix":
            return bitunix_client.list_unified_symbols(force=force)
        ex = get_exchange(ex_id)
        if hasattr(ex, "list_unified_symbols"):
            return ex.list_unified_symbols(force=force)
        markets = api_call(ex.load_markets, True) if force else api_call(ex.load_markets)
        if not markets:
            return []
        out = []
        for sym, m in markets.items():
            if not isinstance(m, dict) or m.get("active") is False:
                continue
            if ex_id == "binance":
                if not (m.get("swap") or m.get("linear") or m.get("contract")):
                    continue
            elif ex_id == "bybit":
                if m.get("spot") and not (m.get("swap") or m.get("linear")):
                    continue
                if m.get("linear") is False and not m.get("swap"):
                    continue
            uni = futures_venues._unified_base_quote(m.get("symbol") or sym)
            if uni.endswith("/USDT") and uni not in out:
                out.append(uni)
        return sorted(out)
    except Exception as e:
        print(f"[data_layer] {ex_id} symbols: {e}")
        return []


_UNIVERSE_TTL = 3600
_universe_state = {"ts": 0.0, "symbols": [], "preferred": {}}
_universe_lock = threading.Lock()


def preferred_exchange_for(symbol: str) -> str | None:
    """Первая биржа из preference, где символ есть в кэше рынков (без live ticker)."""
    uni = futures_venues._unified_base_quote(symbol)
    with _universe_lock:
        pref = _universe_state["preferred"].get(uni)
        if pref:
            return pref
    # лениво обновим universe map
    get_all_venue_symbols()
    with _universe_lock:
        return _universe_state["preferred"].get(uni)


def get_all_venue_symbols(force: bool = False) -> list[str]:
    """Уникальный union USDT-M символов по всем подключённым биржам."""
    now = time.time()
    with _universe_lock:
        if (
            not force
            and _universe_state["symbols"]
            and (now - _universe_state["ts"]) < _UNIVERSE_TTL
        ):
            return list(_universe_state["symbols"])

    preferred_map = {}
    ordered = []
    seen = set()
    # CANDIDATES первыми — привычный топ всегда в начале скана
    for s in CANDIDATES:
        if s not in seen:
            seen.add(s)
            ordered.append(s)

    for ex_id in _EXCHANGE_PREFERENCE:
        for s in get_exchange_futures_symbols(ex_id, force=force):
            if s not in preferred_map:
                preferred_map[s] = ex_id
            if s not in seen:
                seen.add(s)
                ordered.append(s)

    # preferred для CANDIDATES тоже
    for s in ordered:
        preferred_map.setdefault(s, "bybit")

    with _universe_lock:
        _universe_state["ts"] = time.time()
        _universe_state["symbols"] = ordered
        _universe_state["preferred"] = preferred_map
    print(f"[data_layer] universe={len(ordered)} venues={len(_EXCHANGE_PREFERENCE)}")
    return list(ordered)


def get_bitunix_futures_symbols(force: bool = False):
    """Все OPEN USDT-M фьючерсы Bitunix в формате BTC/USDT."""
    return get_exchange_futures_symbols("bitunix", force=force)


def get_active_symbols():
    """Сканер / NFI / overview: полный union бирж (~1200), либо только CANDIDATES.

    SCAN_FULL_UNIVERSE=0 — откат на 39 монет.
    """
    full = (os.getenv("SCAN_FULL_UNIVERSE", "1") or "1").strip().lower()
    if full in ("0", "false", "no", "off"):
        return list(CANDIDATES)
    # legacy alias
    if (os.getenv("BITUNIX_MERGE_UNIVERSE", "") or "").strip().lower() in ("0", "false", "no", "off"):
        # только если явно выключили bitunix merge и не форсили full — не используем
        pass
    return get_all_venue_symbols()


def list_supported_exchanges():
    return [
        {"id": eid, "name": _EXCHANGE_LABELS.get(eid, eid)}
        for eid in _EXCHANGE_PREFERENCE
    ]


# ── Обзор рынка (Скринер) ────────────────────────────────────────
# Снапшот режимов. Полный universe строится в фоне с пулом воркеров.

OVERVIEW_TTL = int(os.getenv("OVERVIEW_TTL_SEC", "600") or "600")
_OVERVIEW_WORKERS = int(os.getenv("OVERVIEW_WORKERS", "12") or "12")
_overview_state = {'ts': 0, 'data': None, 'building': False}
_overview_lock = threading.Lock()


def _overview_symbol_row(sym: str):
    ex_id = preferred_exchange_for(sym) or "bybit"
    # Для обзора хватает 1h — иначе 1200×3 ТФ неподъёмно
    raw = fetch_ohlcv_raw(sym, "1h", limit=120, exchange_id=ex_id)
    if not raw or len(raw) < 50:
        return None
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = build_features(pd.DataFrame(raw, columns=cols))
    regime, adx = detect_regime(df)
    return {
        "symbol": sym,
        "regime": regime,
        "adx": round(float(adx), 1),
        "exchange": ex_id,
    }


def _build_market_overview():
    from concurrent.futures import ThreadPoolExecutor, as_completed

    symbols_in = get_active_symbols()
    symbols = []
    workers = max(2, min(_OVERVIEW_WORKERS, 24))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_overview_symbol_row, sym): sym for sym in symbols_in}
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except Exception:
                row = None
            if row:
                symbols.append(row)
    symbols.sort(key=lambda s: s["symbol"])
    up = sum(1 for s in symbols if s["regime"] == "UPTREND")
    down = sum(1 for s in symbols if s["regime"] == "DOWNTREND")
    btc = next((s for s in symbols if s["symbol"] == "BTC/USDT"), None)
    return {
        "symbols": symbols,
        "btc_regime": btc["regime"] if btc else "НЕТ ДАННЫХ",
        "uptrend_count": up,
        "downtrend_count": down,
        "chop_count": len(symbols) - up - down,
        "universe_size": len(symbols_in),
        "scanned": len(symbols),
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