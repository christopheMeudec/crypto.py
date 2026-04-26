from typing import Literal

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import AverageTrueRange

import config

Signal = Literal["BUY", "SELL", "HOLD"]


def compute_indicators(df: pd.DataFrame, symbol: str | None = None) -> pd.DataFrame:
    """Ajoute les colonnes RSI et MACD au DataFrame OHLCV."""
    df = df.copy()
    symbol_cfg = config.get_symbol_config(symbol) if symbol else config.DEFAULT_SYMBOL_STRATEGY

    # RSI
    df["rsi"] = RSIIndicator(close=df["close"], window=int(symbol_cfg["rsi_period"])).rsi()

    # MACD
    macd_obj = MACD(
        close=df["close"],
        window_fast=int(symbol_cfg["macd_fast"]),
        window_slow=int(symbol_cfg["macd_slow"]),
        window_sign=int(symbol_cfg["macd_signal"]),
    )
    df["macd"] = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_hist"] = macd_obj.macd_diff()

    return df


def get_signal_with_reason(df: pd.DataFrame, symbol: str | None = None) -> tuple[Signal, str]:
    """
    Calcule le signal de trading sur les deux dernières bougies (crossover).

    Règles :
    - BUY  : RSI < RSI_OVERSOLD  ET MACD vient de croiser AU-DESSUS de la ligne signal
    - SELL : RSI > RSI_OVERBOUGHT ET MACD vient de croiser EN-DESSOUS de la ligne signal
    - HOLD : sinon
    """
    df = compute_indicators(df, symbol=symbol)
    df.dropna(inplace=True)
    symbol_cfg = config.get_symbol_config(symbol) if symbol else config.DEFAULT_SYMBOL_STRATEGY
    oversold = float(symbol_cfg["rsi_oversold"])
    overbought = float(symbol_cfg["rsi_overbought"])

    if len(df) < 2:
        return "HOLD", "Pas assez de bougies exploitables apres calcul des indicateurs"

    prev = df.iloc[-2]
    last = df.iloc[-1]

    rsi = float(last["rsi"])

    # Crossover haussier : MACD passe au-dessus du signal (bougie courante)
    macd_cross_up = (prev["macd"] < prev["macd_signal"]) and (last["macd"] > last["macd_signal"])
    # Crossover baissier : MACD passe en dessous du signal (bougie courante)
    macd_cross_down = (prev["macd"] > prev["macd_signal"]) and (last["macd"] < last["macd_signal"])

    # Extension : accepter un crossover survenu il y a 1 bougie si le momentum est confirmé
    if len(df) >= 3:
        prev2 = df.iloc[-3]
        macd_cross_up = macd_cross_up or (
            (prev2["macd"] < prev2["macd_signal"])
            and (prev["macd"] > prev["macd_signal"])
            and (last["macd"] > last["macd_signal"])
            and (float(last["macd_hist"]) >= float(prev["macd_hist"]))  # momentum toujours positif
        )
        macd_cross_down = macd_cross_down or (
            (prev2["macd"] > prev2["macd_signal"])
            and (prev["macd"] < prev["macd_signal"])
            and (last["macd"] < last["macd_signal"])
            and (float(last["macd_hist"]) <= float(prev["macd_hist"]))  # momentum toujours négatif
        )

    buy_ready = (rsi < oversold) and macd_cross_up
    sell_ready = (rsi > overbought) and macd_cross_down

    if buy_ready:
        return "BUY", f"BUY valide: RSI {rsi:.2f} < {oversold:.2f} et MACD cross up"
    if sell_ready:
        return "SELL", f"SELL valide: RSI {rsi:.2f} > {overbought:.2f} et MACD cross down"

    reason = (
        f"HOLD: RSI={rsi:.2f} (buy<{oversold:.2f}, sell>{overbought:.2f}) | "
        f"cross_up={macd_cross_up} | cross_down={macd_cross_down}"
    )
    return "HOLD", reason


def get_signal(df: pd.DataFrame, symbol: str | None = None) -> Signal:
    signal, _ = get_signal_with_reason(df, symbol=symbol)
    return signal


def compute_atr(df: pd.DataFrame, period: int | None = None) -> float | None:
    """Retourne la valeur ATR sur la dernière bougie, ou None si insuffisant."""
    if period is None:
        period = config.ATR_PERIOD
    if len(df) < period + 1:
        return None
    try:
        val = AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=period
        ).average_true_range().iloc[-1]
        return float(val) if pd.notna(val) and val > 0 else None
    except Exception:
        return None
