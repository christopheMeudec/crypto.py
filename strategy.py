from typing import Literal

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

import config

Signal = Literal["BUY", "SELL", "HOLD"]


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les colonnes RSI et MACD au DataFrame OHLCV."""
    df = df.copy()

    # RSI
    df["rsi"] = RSIIndicator(close=df["close"], window=config.RSI_PERIOD).rsi()

    # MACD
    macd_obj = MACD(
        close=df["close"],
        window_fast=config.MACD_FAST,
        window_slow=config.MACD_SLOW,
        window_sign=config.MACD_SIGNAL,
    )
    df["macd"] = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_hist"] = macd_obj.macd_diff()

    return df


def get_signal(df: pd.DataFrame) -> Signal:
    """
    Calcule le signal de trading sur les deux dernières bougies (crossover).

    Règles :
    - BUY  : RSI < RSI_OVERSOLD  ET MACD vient de croiser AU-DESSUS de la ligne signal
    - SELL : RSI > RSI_OVERBOUGHT ET MACD vient de croiser EN-DESSOUS de la ligne signal
    - HOLD : sinon
    """
    df = compute_indicators(df)
    df.dropna(inplace=True)

    if len(df) < 2:
        return "HOLD"

    prev = df.iloc[-2]
    last = df.iloc[-1]

    rsi = last["rsi"]

    # Crossover haussier : MACD passe au-dessus du signal
    macd_cross_up = (prev["macd"] < prev["macd_signal"]) and (last["macd"] > last["macd_signal"])
    # Crossover baissier : MACD passe en dessous du signal
    macd_cross_down = (prev["macd"] > prev["macd_signal"]) and (last["macd"] < last["macd_signal"])

    if rsi < config.RSI_OVERSOLD and macd_cross_up:
        return "BUY"
    if rsi > config.RSI_OVERBOUGHT and macd_cross_down:
        return "SELL"
    return "HOLD"
