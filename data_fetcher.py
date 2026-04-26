import logging
import time

import ccxt
import pandas as pd

import config

logger = logging.getLogger(__name__)

_exchange = ccxt.binance({
    "apiKey": config.BINANCE_API_KEY,
    "secret": config.BINANCE_API_SECRET,
    "enableRateLimit": True,
})

_MAX_RETRIES = 3
_RETRY_DELAY_S = 5.0


def fetch_ohlcv(
    symbol: str,
    timeframe: str = config.TIMEFRAME,
    limit: int = config.OHLCV_LIMIT,
    since: int | None = None,
) -> pd.DataFrame:
    """
    Récupère les bougies OHLCV depuis Binance et retourne un DataFrame pandas.
    Colonnes : timestamp, open, high, low, close, volume
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            raw = _exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, since=since)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "fetch_ohlcv [%s] tentative %d/%d échouée : %s. Nouvelle tentative dans %.0fs.",
                    symbol, attempt, _MAX_RETRIES, exc, _RETRY_DELAY_S,
                )
                time.sleep(_RETRY_DELAY_S)
            else:
                logger.error(
                    "fetch_ohlcv [%s] échec après %d tentatives : %s",
                    symbol, _MAX_RETRIES, exc,
                )
    raise last_exc  # type: ignore[misc]
