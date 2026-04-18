import ccxt
import pandas as pd

import config

_exchange = ccxt.binance({
    "apiKey": config.BINANCE_API_KEY,
    "secret": config.BINANCE_API_SECRET,
    "enableRateLimit": True,
})


def fetch_ohlcv(symbol: str, timeframe: str = config.TIMEFRAME, limit: int = config.OHLCV_LIMIT) -> pd.DataFrame:
    """
    Récupère les bougies OHLCV depuis Binance et retourne un DataFrame pandas.
    Colonnes : timestamp, open, high, low, close, volume
    """
    raw = _exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df
