from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import config
from data_fetcher import fetch_ohlcv
from strategy import compute_indicators


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    initial_capital: float
    final_value: float
    pnl: float
    pnl_pct: float
    trades: int
    max_drawdown_pct: float


@dataclass
class TimeframeResult:
    timeframe: str
    initial_capital: float
    final_value: float
    pnl: float
    pnl_pct: float
    trades: int
    max_drawdown_pct: float
    score: float


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak
            if drawdown > max_dd:
                max_dd = drawdown
    return max_dd * 100.0


def _backtest_symbol(symbol: str, timeframe: str, initial_capital: float, limit: int) -> BacktestResult:
    df = fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = compute_indicators(df)
    df.dropna(inplace=True)

    cash = initial_capital
    position_qty = 0.0
    trades = 0
    equity_curve: list[float] = []

    if len(df) < 2:
        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            initial_capital=initial_capital,
            final_value=initial_capital,
            pnl=0.0,
            pnl_pct=0.0,
            trades=0,
            max_drawdown_pct=0.0,
        )

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        price = float(curr["close"])

        macd_cross_up = (prev["macd"] < prev["macd_signal"]) and (curr["macd"] > curr["macd_signal"])
        macd_cross_down = (prev["macd"] > prev["macd_signal"]) and (curr["macd"] < curr["macd_signal"])

        should_buy = curr["rsi"] < config.RSI_OVERSOLD and macd_cross_up
        should_sell = curr["rsi"] > config.RSI_OVERBOUGHT and macd_cross_down

        # Buy with configured allocation, sell full position on SELL signal.
        if should_buy and cash > 1.0:
            spend = cash * config.TRADE_ALLOCATION
            if spend > 0:
                qty = spend / price
                position_qty += qty
                cash -= spend
                trades += 1
        elif should_sell and position_qty > 0.0:
            cash += position_qty * price
            position_qty = 0.0
            trades += 1

        equity_curve.append(cash + (position_qty * price))

    last_price = float(df["close"].iloc[-1])
    final_value = cash + (position_qty * last_price)
    pnl = final_value - initial_capital
    pnl_pct = (pnl / initial_capital) * 100.0 if initial_capital > 0 else 0.0
    max_dd = _max_drawdown_pct(equity_curve)

    return BacktestResult(
        symbol=symbol,
        timeframe=timeframe,
        initial_capital=initial_capital,
        final_value=final_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
        trades=trades,
        max_drawdown_pct=max_dd,
    )


def optimize_timeframes(
    symbols: Iterable[str],
    timeframes: Iterable[str] = config.OPTIMIZATION_TIMEFRAMES,
    history_limit: int = config.OPTIMIZATION_OHLCV_LIMIT,
) -> list[TimeframeResult]:
    """Backtest each timeframe and return ranked aggregate results."""
    symbols = list(symbols)
    if not symbols:
        return []

    per_symbol_capital = config.INITIAL_CAPITAL_USDT / len(symbols)
    results: list[TimeframeResult] = []

    for timeframe in timeframes:
        backtests: list[BacktestResult] = []

        for symbol in symbols:
            result = _backtest_symbol(
                symbol=symbol,
                timeframe=timeframe,
                initial_capital=per_symbol_capital,
                limit=history_limit,
            )
            backtests.append(result)

        initial_capital = sum(bt.initial_capital for bt in backtests)
        final_value = sum(bt.final_value for bt in backtests)
        pnl = final_value - initial_capital
        pnl_pct = (pnl / initial_capital) * 100.0 if initial_capital > 0 else 0.0
        trades = sum(bt.trades for bt in backtests)

        # Conservative aggregate risk: keep the worst drawdown seen among symbols.
        max_drawdown_pct = max((bt.max_drawdown_pct for bt in backtests), default=0.0)

        # Simple risk-adjusted score used only for ranking: more return, less drawdown.
        score = pnl_pct - (0.5 * max_drawdown_pct)

        results.append(
            TimeframeResult(
                timeframe=timeframe,
                initial_capital=initial_capital,
                final_value=final_value,
                pnl=pnl,
                pnl_pct=pnl_pct,
                trades=trades,
                max_drawdown_pct=max_drawdown_pct,
                score=score,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results
