"""
Data Layer — получение OHLCV данных с Bybit и расчёт технических индикаторов.
Перенесено из Telegram-бота без изменений в логике.
"""

import time
import ccxt
import pandas as pd

exchange = ccxt.bybit({
    'options': {'defaultType': 'linear'},
    'enableRateLimit': True,
    'timeout': 15000,
})

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


def clean_cache():
    now = time.time()
    for s in [k for k, (t, _) in _data_cache.items() if now - t >= CACHE_TTL]:
        del _data_cache[s]


def fetch_data(symbol):
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    d4h = api_call(exchange.fetch_ohlcv, symbol, '4h', limit=120)
    d1h = api_call(exchange.fetch_ohlcv, symbol, '1h', limit=100)
    d30m = api_call(exchange.fetch_ohlcv, symbol, '30m', limit=150)
    if not d4h or not d1h or not d30m:
        return None
    df4h = pd.DataFrame(d4h, columns=cols)
    df1h = pd.DataFrame(d1h, columns=cols)
    df30m = pd.DataFrame(d30m, columns=cols)
    if len(df4h) < 60 or len(df1h) < 50 or len(df30m) < 80:
        return None
    return {'4h': df4h, '1h': df1h, '30m': df30m}


def fetch_data_cached(symbol):
    now = time.time()
    if symbol in _data_cache:
        t, d = _data_cache[symbol]
        if now - t < CACHE_TTL:
            return d
    d = fetch_data(symbol)
    if d:
        _data_cache[symbol] = (now, d)
    return d


def fetch_ticker(symbol):
    return api_call(exchange.fetch_ticker, symbol)


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
    # Top 10 by volume
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
    'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'ATOM/USDT', 'DOGE/USDT',
    
    # Layer 2 & DeFi
    'LINK/USDT', 'UNI/USDT', 'AAVE/USDT', 'ARB/USDT', 'OP/USDT',
    'LIDO/USDT', 'CURVE/USDT', 'MKR/USDT', 'SNX/USDT', 'SUSHI/USDT',
    
    # AI & ML (trending)
    'FET/USDT', 'THETA/USDT', 'WLD/USDT', 'RENDER/USDT', 'TAO/USDT',
    
    # Memes & community
    'SHIB/USDT', 'PEPE/USDT', 'FLOKI/USDT',
    
    # Layer 1 alternatives
    'NEAR/USDT', 'ALGO/USDT', 'FANTOM/USDT',
    
    # Storage & Infrastructure
    'FIL/USDT', 'AR/USDT',
    
    # Gaming
    'GALA/USDT', 'ENJ/USDT', 'SAND/USDT',
    
    # Classic alts
    'LTC/USDT', 'BCH/USDT', 'ETC/USDT', 'TRX/USDT',
    
    # Emerging
    'SUI/USDT', 'APT/USDT', 'INJ/USDT', 'TIA/USDT', 'SEI/USDT',
    'HBAR/USDT', 'STX/USDT', 'VET/USDT', 'ICP/USDT',
]


def get_active_symbols():
    return CANDIDATES


def fmt_price(p):
    if p >= 1000:
        return f"{p:.2f}"
    elif p >= 1:
        return f"{p:.3f}"
    elif p >= 0.01:
        return f"{p:.5f}"
    return f"{p:.7f}"