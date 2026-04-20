# Comprehensive Backtesting Guide

This document explains how to use the advanced backtesting engine with Stop-Loss, Take-Profit, Fees, and Slippage simulation.

## Overview

The backtesting engine simulates the trading strategy on historical data with realistic conditions:
- **Stop-Loss & Take-Profit**: Automatic position closing at configured levels
- **Fees**: 0.1% taker fee on buy and sell (Binance standard)
- **Slippage**: 0.05% simulated slippage on order execution
- **Advanced Metrics**: Sharpe ratio, Sortino ratio, Calmar ratio, drawdown, win rate, profit factor

## Quick Start

### Method 1: Using the CLI Tool (Recommended)

```bash
# Single symbol backtest (30 days)
python run_backtest.py --symbol BTC/USDT --days 30 --timeframe 15m

# Multi-symbol backtest
python run_backtest.py --multi-symbol --days 365 --timeframe 1h

# Export results to JSON
python run_backtest.py --symbol BTC/USDT --days 90 --export data/backtest_results.json

# Custom initial capital
python run_backtest.py --symbol ETH/USDT --days 60 --capital 1000
```

### Method 2: Using main.py

```bash
# Run single backtest
python main.py --backtest --backtest-symbol BTC/USDT --backtest-days 30

# Run with export
python main.py --backtest --backtest-symbol ETH/USDT --backtest-days 365 --backtest-export results.json
```

### Method 3: Python API

```python
from backtest import run_backtest, print_backtest_report

# Run backtest
metrics = run_backtest(
    symbol="BTC/USDT",
    timeframe="15m",
    days_back=365,
    initial_capital=1000.0,
)

# Print report
print_backtest_report(metrics)

# Access metrics programmatically
print(f"Return: {metrics.realized_pnl_pct:.2f}%")
print(f"Win Rate: {metrics.win_rate_pct:.1f}%")
print(f"Sharpe: {metrics.sharpe_ratio:.2f}")
print(f"Drawdown: {metrics.max_drawdown_pct:.2f}%")
```

## Configuration

Edit `config.py` to customize backtesting parameters:

```python
# Risk Management
ENABLE_STOPS = True               # Enable SL/TP
STOP_LOSS_PCT = -3.0              # Stop-loss at -3% from entry
TAKE_PROFIT_PCT = 5.0             # Take-profit at +5% from entry

# Fees & Slippage
TAKER_FEE_PCT = 0.1               # 0.1% taker fee (Binance)
SLIPPAGE_PCT = 0.05               # 0.05% average slippage

# Trading Strategy
RSI_PERIOD = 14
RSI_OVERSOLD = 40
RSI_OVERBOUGHT = 60
MACD_FAST = 8
MACD_SLOW = 21
MACD_SIGNAL = 5
TRADE_ALLOCATION = 0.25           # 25% of capital per trade
```

## Output Metrics

### Trade Statistics

- **Total Trades**: Sum of BUY and SELL signals
- **Buy Trades**: Number of entry signals
- **Sell Trades**: Number of exit signals  
- **Winning Trades**: Trades with positive PnL
- **Losing Trades**: Trades with negative PnL
- **Win Rate %**: (Winning Trades / Sell Trades) × 100

### PnL Analysis

- **Realized PnL**: Actual profit/loss from closed positions
- **Avg Win**: Average profit per winning trade
- **Avg Loss**: Average loss per losing trade
- **Profit Factor**: Sum of wins / Sum of losses (>1 is good)
- **Largest Win/Loss**: Best and worst individual trade

### Risk Metrics

- **Max Drawdown %**: Largest peak-to-trough decline
- **Max Drawdown Amount**: Dollar value of max drawdown
- **Sharpe Ratio**: Risk-adjusted return (annual, >1 is good)
- **Sortino Ratio**: Like Sharpe but only penalizes downside
- **Calmar Ratio**: Annual return / max drawdown (>0.5 is good)
- **Daily Volatility %**: Standard deviation of returns

## Example Output

```
==========================================================================================
BACKTEST REPORT: BTC/USDT | 15m
==========================================================================================

Period: 2026-04-15 → 2026-04-20
Initial Capital: $100.00
Final Value:     $102.45
Realized PnL:    +2.45 USDT (+2.45%)

--- TRADE STATISTICS ---
Total Trades:      15
  Buy Trades:      8
  Sell Trades:     7
  Winning Trades:  5
  Losing Trades:   2
  Win Rate:        71.43%
  Profit Factor:   2.15

--- TRADE PnL ANALYSIS ---
Avg Win:           $+0.65
Avg Loss:          $-0.32
Avg Trade PnL:     $+0.35
Largest Win:       $+1.20
Largest Loss:      $-0.45
Max Consecutive Wins:  3
Max Consecutive Losses: 1

--- RISK METRICS ---
Max Drawdown:      2.34% ($2.34)
Sharpe Ratio:      1.85
Sortino Ratio:     2.12
Calmar Ratio:      1.05
Daily Volatility:  0.15%

==========================================================================================
```

## Important Notes

### Data Fetching

- **Limit**: CCXT/Binance API typically returns last 500-1000 candles per request
- **Long History**: For 1+ years of data, the system automatically batches requests
- **Rate Limiting**: 0.5s delay between batches to respect API rate limits
- **Incomplete Data**: Recent periods may have fewer candles than requested

### Performance

- Small datasets (1 month, 15m): ~1-2 seconds
- Medium datasets (3 months, 1h): ~5-10 seconds
- Large datasets (1 year, 15m): ~30-60 seconds

### Recommendations

1. **Start Small**: Test with 30 days first to validate strategy
2. **Multiple Timeframes**: Test 15m, 1h, 4h, 1d to find best timeframe
3. **Compare Pairs**: Run backtest on BTC, ETH, and other pairs
4. **Monitor Drawdown**: Stop trading if max drawdown > 20%
5. **Export Results**: Save JSON for further analysis

## Troubleshooting

### Error: "Not enough data"
- Reduce days_back or use a higher timeframe (e.g., 1h instead of 15m)

### Error: "API rate limit exceeded"
- Wait a few minutes before retrying
- Increase batch_size in fetch_ohlcv_long() (if you have API credentials)

### Missing trades
- Check that RSI and MACD settings match config.py
- Verify SL/TP are not triggering immediately (check initial capital)

## Advanced Usage

### Batch Backtest Multiple Symbols

```python
from backtest import run_backtest, print_backtest_report
import config

symbols = ["BTC/USDT", "ETH/USDT", "XRP/USDT"]
capital_per_pair = config.INITIAL_CAPITAL_USDT / len(symbols)

results = []
for symbol in symbols:
    metrics = run_backtest(
        symbol=symbol,
        timeframe="1h",
        days_back=180,
        initial_capital=capital_per_pair,
    )
    results.append(metrics)
    print_backtest_report(metrics)

# Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)
for m in results:
    print(f"{m.symbol:12} | Return: {m.realized_pnl_pct:+7.2f}% | Sharpe: {m.sharpe_ratio:+6.2f}")
```

### Optimize Parameters

```python
from backtest import run_backtest
import config

# Test different SL/TP levels
for sl in [-1.0, -2.0, -3.0, -5.0]:
    for tp in [3.0, 5.0, 7.0, 10.0]:
        config.STOP_LOSS_PCT = sl
        config.TAKE_PROFIT_PCT = tp
        
        metrics = run_backtest("BTC/USDT", days_back=90)
        print(f"SL={sl}% TP={tp}% → Return={metrics.realized_pnl_pct:.2f}% Sharpe={metrics.sharpe_ratio:.2f}")
```

## See Also

- [config.py](config.py) - Configuration parameters
- [paper_trader.py](paper_trader.py) - Trading engine with SL/TP logic
- [strategy.py](strategy.py) - RSI + MACD strategy implementation
