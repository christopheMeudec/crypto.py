from typing import Literal

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

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

    # Crossover haussier : MACD passe au-dessus du signal
    macd_cross_up = (prev["macd"] < prev["macd_signal"]) and (last["macd"] > last["macd_signal"])
    # Crossover baissier : MACD passe en dessous du signal
    macd_cross_down = (prev["macd"] > prev["macd_signal"]) and (last["macd"] < last["macd_signal"])

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
