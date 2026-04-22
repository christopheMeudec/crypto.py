"""
Comprehensive Backtesting Engine with Advanced Metrics.

Backtests the trading strategy over historical data with:
- Stop-Loss and Take-Profit tracking
- Fee and slippage simulation
- Advanced metrics: Sharpe ratio, Sortino, drawdown, win rate, profit factor
- Trade-by-trade analysis
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

import config
from data_fetcher import fetch_ohlcv
from paper_trader import PaperTrader
from strategy import get_signal

logger = logging.getLogger(__name__)


@dataclass
class BacktestMetrics:
    """Complete backtest results with advanced metrics."""
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    
    initial_capital: float
    final_value: float
    realized_pnl: float
    realized_pnl_pct: float
    
    total_trades: int
    buy_trades: int
    sell_trades: int
    winning_trades: int
    losing_trades: int
    
    win_rate_pct: float           # (winning_trades / sell_trades) * 100
    profit_factor: float           # sum(wins) / sum(losses)
    avg_win: float
    avg_loss: float
    avg_trade_pnl: float
    
    largest_win: float
    largest_loss: float
    consecutive_wins: int
    consecutive_losses: int
    
    # Risk metrics
    total_return_pct: float        # (final_value - initial) / initial * 100
    max_drawdown_pct: float
    max_drawdown_amount: float
    sharpe_ratio: float            # Annualized
    sortino_ratio: float           # Annualized
    calmar_ratio: float            # Annual return / max drawdown
    
    # Volatility
    daily_returns_std: float
    equity_curve: List[float] = field(default_factory=list)
    closed_trades: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON export."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "final_value": self.final_value,
            "realized_pnl": self.realized_pnl,
            "realized_pnl_pct": self.realized_pnl_pct,
            "total_trades": self.total_trades,
            "buy_trades": self.buy_trades,
            "sell_trades": self.sell_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "avg_trade_pnl": self.avg_trade_pnl,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_amount": self.max_drawdown_amount,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "daily_returns_std": self.daily_returns_std,
        }


def fetch_ohlcv_long(
    symbol: str,
    timeframe: str = "15m",
    days_back: int = 365,
    batch_size: int = 500
) -> pd.DataFrame:
    """
    Fetch long historical OHLCV data with pagination.
    
    Args:
        symbol: Trading pair (e.g., "BTC/USDT")
        timeframe: Candle size (e.g., "15m", "1h")
        days_back: How many days of history to fetch
        batch_size: Batch size per request (CCXT limit ~1000)
    
    Returns:
        DataFrame with OHLCV data
    """
    # Estimate number of candles needed
    candles_per_day = {
        "1m": 1440,
        "5m": 288,
        "15m": 96,
        "30m": 48,
        "1h": 24,
        "4h": 6,
        "1d": 1,
    }
    
    candles_per_day_count = candles_per_day.get(timeframe, 96)
    total_candles_needed = days_back * candles_per_day_count
    num_batches = (total_candles_needed + batch_size - 1) // batch_size
    
    logger.info(
        "Fetching %s %d days (%d candles total, %d batches of %d)",
        symbol,
        days_back,
        total_candles_needed,
        num_batches,
        batch_size
    )
    
    all_data = []
    
    for batch_idx in range(num_batches):
        try:
            # Fetch batch
            batch_limit = min(batch_size, total_candles_needed - batch_idx * batch_size)
            df_batch = fetch_ohlcv(symbol, timeframe=timeframe, limit=batch_limit)
            
            if df_batch.empty:
                logger.warning("Empty batch %d, stopping.", batch_idx)
                break
            
            all_data.append(df_batch)
            logger.debug("Batch %d/%d: %d candles", batch_idx + 1, num_batches, len(df_batch))
            
            # Respect rate limits (wait 0.5s between requests)
            if batch_idx < num_batches - 1:
                time.sleep(0.5)
        
        except Exception as exc:
            logger.error("Error fetching batch %d: %s", batch_idx, exc)
            break
    
    if not all_data:
        logger.error("No data fetched for %s", symbol)
        return pd.DataFrame()
    
    # Combine all batches and remove duplicates
    df_combined = pd.concat(all_data, ignore_index=False)
    df_combined = df_combined[~df_combined.index.duplicated(keep='first')]
    df_combined = df_combined.sort_index()
    
    logger.info("Total data fetched: %d candles from %s to %s", len(df_combined), df_combined.index[0], df_combined.index[-1])
    
    return df_combined


def _calculate_metrics(
    equity_curve: List[float],
    closed_trades: List[Dict],
    candle_timeframe: str,
    initial_capital: float,
) -> Tuple[float, float, float, float, float]:
    """
    Calculate advanced metrics from equity curve and closed trades.
    
    Returns: (sharpe_ratio, sortino_ratio, calmar_ratio, daily_returns_std, max_dd)
    """
    if len(equity_curve) < 2:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    
    equity_array = np.array(equity_curve)
    returns = np.diff(equity_array) / equity_array[:-1]
    
    # Annualize based on timeframe
    periods_per_year = {
        "1m": 365 * 24 * 60,
        "5m": 365 * 24 * 12,
        "15m": 365 * 24 * 4,
        "30m": 365 * 24 * 2,
        "1h": 365 * 24,
        "4h": 365 * 6,
        "1d": 365,
    }
    periods = periods_per_year.get(candle_timeframe, 365 * 24 * 4)
    
    # Calculate returns
    mean_return = np.mean(returns) if len(returns) > 0 else 0.0
    std_return = np.std(returns) if len(returns) > 1 else 1.0
    
    # Sharpe ratio (assuming 0% risk-free rate)
    sharpe = (mean_return / std_return * np.sqrt(periods)) if std_return > 0 else 0.0
    
    # Sortino ratio (only penalize downside)
    downside_returns = returns[returns < 0]
    downside_std = np.std(downside_returns) if len(downside_returns) > 0 else std_return
    sortino = (mean_return / downside_std * np.sqrt(periods)) if downside_std > 0 else 0.0
    
    # Max drawdown
    peak = equity_array[0]
    max_dd = 0.0
    for value in equity_array:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)
    
    max_dd_pct = max_dd * 100.0
    
    # Calmar ratio
    annual_return_pct = (equity_array[-1] - initial_capital) / initial_capital * 100.0
    calmar = annual_return_pct / max_dd_pct if max_dd_pct > 0 else 0.0
    
    # Daily volatility (annualized)
    daily_vol = std_return * np.sqrt(periods / 365)
    
    return sharpe, sortino, calmar, daily_vol, max_dd_pct


class BacktestRunner:
    """Runs backtest simulation with PaperTrader."""
    
    def __init__(self, symbol: str, timeframe: str, initial_capital: float = 100.0):
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.trader = PaperTrader(
            initial_capital=initial_capital,
            data_dir=config.BACKTEST_DATA_DIR,
            persist=config.BACKTEST_PERSIST_TRADES,
        )
    
    def run(self, df: pd.DataFrame) -> BacktestMetrics:
        """
        Run backtest on historical data.
        
        Args:
            df: DataFrame with OHLCV data and indicators
        
        Returns:
            BacktestMetrics with complete results
        """
        if len(df) < 2:
            logger.error("Not enough data for backtest (need at least 2 candles)")
            return self._empty_metrics(df)
        
        equity_curve = [self.initial_capital]
        buy_prices = {}  # symbol -> [prices]
        
        logger.info("Starting backtest for %s | %s candles", self.symbol, len(df))
        
        for i in range(1, len(df)):
            prev_row = df.iloc[i - 1]
            curr_row = df.iloc[i]
            current_price = float(curr_row["close"])
            
            # 1. Auto-close SL/TP FIRST
            closed = self.trader._auto_close_entries(self.symbol, current_price)
            
            # 2. Generate signal
            signal = get_signal(df.iloc[: i + 1], symbol=self.symbol)
            
            # 3. Execute signal
            if signal == "BUY":
                entry = self.trader.buy(self.symbol, current_price)
                if entry:
                    if self.symbol not in buy_prices:
                        buy_prices[self.symbol] = []
                    buy_prices[self.symbol].append(entry.entry_price)
            
            elif signal == "SELL":
                if self.trader.get_total_quantity(self.symbol) > 0:
                    entry = self.trader.sell(self.symbol, current_price)
            
            # 4. Record equity
            prices = {self.symbol: current_price}
            current_equity = self.trader.portfolio_value(prices)
            equity_curve.append(current_equity)
        
        # Get final metrics
        last_price = float(df["close"].iloc[-1])
        prices = {self.symbol: last_price}
        final_value = self.trader.portfolio_value(prices)
        
        closed_entries = self.trader.get_closed_entries()
        
        # Build results
        return self._build_metrics(
            df=df,
            equity_curve=equity_curve,
            closed_entries=closed_entries,
            final_value=final_value
        )
    
    def _build_metrics(
        self,
        df: pd.DataFrame,
        equity_curve: List[float],
        closed_entries: List,
        final_value: float
    ) -> BacktestMetrics:
        """Compute all metrics from backtest results."""
        
        start_date = df.index[0].isoformat()
        end_date = df.index[-1].isoformat()
        
        realized_pnl = final_value - self.initial_capital
        realized_pnl_pct = (realized_pnl / self.initial_capital * 100.0) if self.initial_capital > 0 else 0.0
        
        # Trade statistics
        total_trades = len(self.trader.trades)
        buy_trades = sum(1 for t in self.trader.trades if t.side == "BUY")
        sell_trades = sum(1 for t in self.trader.trades if t.side == "SELL")
        
        # Closed trade analysis
        winning_trades = 0
        losing_trades = 0
        trade_pnls = []
        consecutive_wins = 0
        consecutive_losses = 0
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        largest_win = 0.0
        largest_loss = 0.0
        
        closed_trades_data = []
        
        for entry in closed_entries:
            if entry.realized_pnl is None:
                continue
            
            pnl = entry.realized_pnl
            trade_pnls.append(pnl)
            
            trade_data = {
                "entry_id": entry.entry_id,
                "symbol": entry.symbol,
                "entry_price": entry.entry_price,
                "exit_price": entry.exit_price,
                "quantity": entry.entry_quantity,
                "entry_fee": entry.entry_fee,
                "exit_fee": entry.exit_fee,
                "realized_pnl": pnl,
                "realized_pnl_pct": entry.realized_pnl_pct,
                "status": entry.status,
                "entry_time": entry.entry_timestamp.isoformat() if entry.entry_timestamp else "",
                "exit_time": entry.exit_timestamp.isoformat() if entry.exit_timestamp else "",
            }
            closed_trades_data.append(trade_data)
            
            if pnl > 0:
                winning_trades += 1
                consecutive_wins += 1
                consecutive_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
                largest_win = max(largest_win, pnl)
            else:
                losing_trades += 1
                consecutive_losses += 1
                consecutive_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                largest_loss = min(largest_loss, pnl)
        
        # Win rate
        sell_trades_count = sell_trades if sell_trades > 0 else 1
        win_rate = (winning_trades / sell_trades_count * 100.0) if sell_trades_count > 0 else 0.0
        
        # Profit factor
        sum_wins = sum(p for p in trade_pnls if p > 0)
        sum_losses = abs(sum(p for p in trade_pnls if p < 0))
        profit_factor = sum_wins / sum_losses if sum_losses > 0 else (1.0 if sum_wins > 0 else 0.0)
        
        avg_win = sum_wins / max(winning_trades, 1)
        avg_loss = sum_losses / max(losing_trades, 1) if losing_trades > 0 else 0.0
        avg_trade_pnl = np.mean(trade_pnls) if trade_pnls else 0.0
        
        # Advanced metrics
        sharpe, sortino, calmar, daily_vol, max_dd = _calculate_metrics(
            equity_curve,
            closed_trades_data,
            self.timeframe,
            self.initial_capital
        )
        
        # Max drawdown in amount
        equity_array = np.array(equity_curve)
        peak = equity_array[0]
        max_dd_amount = 0.0
        for value in equity_array:
            if value > peak:
                peak = value
            drawdown_amount = peak - value
            max_dd_amount = max(max_dd_amount, drawdown_amount)
        
        return BacktestMetrics(
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_value=final_value,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            total_trades=total_trades,
            buy_trades=buy_trades,
            sell_trades=sell_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade_pnl=avg_trade_pnl,
            largest_win=largest_win,
            largest_loss=largest_loss,
            consecutive_wins=max_consecutive_wins,
            consecutive_losses=max_consecutive_losses,
            total_return_pct=realized_pnl_pct,
            max_drawdown_pct=max_dd,
            max_drawdown_amount=max_dd_amount,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            daily_returns_std=daily_vol,
            equity_curve=equity_curve,
            closed_trades=closed_trades_data,
        )
    
    def _empty_metrics(self, df: pd.DataFrame) -> BacktestMetrics:
        """Return empty metrics for insufficient data."""
        start_date = df.index[0].isoformat() if not df.empty else ""
        end_date = df.index[-1].isoformat() if not df.empty else ""
        
        return BacktestMetrics(
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_value=self.initial_capital,
            realized_pnl=0.0,
            realized_pnl_pct=0.0,
            total_trades=0,
            buy_trades=0,
            sell_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0.0,
            profit_factor=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            avg_trade_pnl=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            consecutive_wins=0,
            consecutive_losses=0,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_amount=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            daily_returns_std=0.0,
        )


def print_backtest_report(metrics: BacktestMetrics) -> None:
    """Print detailed backtest report."""
    
    print("\n" + "=" * 90)
    print(f"BACKTEST REPORT: {metrics.symbol} | {metrics.timeframe}")
    print("=" * 90)
    
    print(f"\nPeriod: {metrics.start_date[:10]} → {metrics.end_date[:10]}")
    print(f"Initial Capital: ${metrics.initial_capital:,.2f}")
    print(f"Final Value:     ${metrics.final_value:,.2f}")
    print(f"Realized PnL:    {metrics.realized_pnl:+,.2f} USDT ({metrics.realized_pnl_pct:+.2f}%)")
    
    print("\n--- TRADE STATISTICS ---")
    print(f"Total Trades:      {metrics.total_trades:,}")
    print(f"  Buy Trades:      {metrics.buy_trades:,}")
    print(f"  Sell Trades:     {metrics.sell_trades:,}")
    print(f"  Winning Trades:  {metrics.winning_trades:,}")
    print(f"  Losing Trades:   {metrics.losing_trades:,}")
    print(f"  Win Rate:        {metrics.win_rate_pct:.2f}%")
    print(f"  Profit Factor:   {metrics.profit_factor:.2f}")
    
    print("\n--- TRADE PnL ANALYSIS ---")
    print(f"Avg Win:           ${metrics.avg_win:+,.2f}")
    print(f"Avg Loss:          ${metrics.avg_loss:+,.2f}")
    print(f"Avg Trade PnL:     ${metrics.avg_trade_pnl:+,.2f}")
    print(f"Largest Win:       ${metrics.largest_win:+,.2f}")
    print(f"Largest Loss:      ${metrics.largest_loss:+,.2f}")
    print(f"Max Consecutive Wins:  {metrics.consecutive_wins}")
    print(f"Max Consecutive Losses: {metrics.consecutive_losses}")
    
    print("\n--- RISK METRICS ---")
    print(f"Max Drawdown:      {metrics.max_drawdown_pct:.2f}% (${metrics.max_drawdown_amount:,.2f})")
    print(f"Sharpe Ratio:      {metrics.sharpe_ratio:.2f}")
    print(f"Sortino Ratio:     {metrics.sortino_ratio:.2f}")
    print(f"Calmar Ratio:      {metrics.calmar_ratio:.2f}")
    print(f"Daily Volatility:  {metrics.daily_returns_std:.2f}%")
    
    print("\n" + "=" * 90)


def run_backtest(
    symbol: str,
    timeframe: str | None = None,
    days_back: int = 365,
    initial_capital: float = 100.0,
) -> BacktestMetrics:
    """
    Run complete backtest for a symbol.
    
    Args:
        symbol: Trading pair (e.g., "BTC/USDT")
        timeframe: Candle size
        days_back: Days of history to backtest
        initial_capital: Starting capital
    
    Returns:
        BacktestMetrics with results
    """
    resolved_timeframe = timeframe or config.get_symbol_timeframe(symbol)

    logger.info("Fetching historical data...")
    df = fetch_ohlcv_long(symbol, timeframe=resolved_timeframe, days_back=days_back)
    
    if df.empty:
        logger.error("Failed to fetch data")
        return BacktestMetrics(symbol=symbol, timeframe=resolved_timeframe, start_date="", end_date="", 
                               initial_capital=initial_capital, final_value=initial_capital,
                               realized_pnl=0.0, realized_pnl_pct=0.0, total_trades=0,
                               buy_trades=0, sell_trades=0, winning_trades=0, losing_trades=0,
                               win_rate_pct=0.0, profit_factor=0.0, avg_win=0.0, avg_loss=0.0,
                               avg_trade_pnl=0.0, largest_win=0.0, largest_loss=0.0,
                               consecutive_wins=0, consecutive_losses=0, total_return_pct=0.0,
                               max_drawdown_pct=0.0, max_drawdown_amount=0.0, sharpe_ratio=0.0,
                               sortino_ratio=0.0, calmar_ratio=0.0, daily_returns_std=0.0)
    
    logger.info("Computing indicators...")
    from strategy import compute_indicators
    df = compute_indicators(df, symbol=symbol)
    df.dropna(inplace=True)
    
    logger.info("Running backtest...")
    runner = BacktestRunner(symbol=symbol, timeframe=resolved_timeframe, initial_capital=initial_capital)
    metrics = runner.run(df)
    
    return metrics
