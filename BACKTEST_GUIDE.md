# Backtest Quick Guide (Fast Execution)

Use this guide to run backtests quickly with the current project setup.

## 1) Recommended Command (Current Runtime Config)

```bash
python run_backtest.py --multi-symbol --grouped-timeframes --days 90
```

This uses:
- all symbols from `config.SYMBOLS`
- each symbol's group timeframe/settings from `config.STRATEGY_GROUPS`

## 2) Most Useful Commands

```bash
# Single symbol (uses symbol default timeframe from config)
python run_backtest.py --symbol BTC/USDT --days 30

# Single symbol with explicit timeframe override
python run_backtest.py --symbol BTC/USDT --days 30 --timeframe 15m

# Multi-symbol with one shared timeframe for all symbols
python run_backtest.py --multi-symbol --days 180 --timeframe 1h

# Export JSON results
python run_backtest.py --multi-symbol --grouped-timeframes --days 90 --export data/backtest_results.json
```

## 3) What Actually Drives the Strategy

Global fallbacks are in `config.py` (fees, slippage, base RSI/MACD, etc.).

For this repo, active per-symbol behavior is mainly controlled by `STRATEGY_GROUPS`:
- `majors`: timeframe `30m`, allocation `0.16`, SL `-3.8`, TP `7.5`
- `alts`: timeframe `30m`, allocation `0.08`, SL `-2.3`, TP `4.8`

If you run with `--grouped-timeframes`, these group settings are applied.

## 4) Read Results Fast

Focus on these lines first:
- `Realized PnL` and `% Return`
- `Max Drawdown`
- `Sharpe` and `Sortino`
- `Profit Factor`

Win rate definition used by the engine:
- `Win Rate % = Winning Closed Trades / Total Closed Trades * 100`

## 5) Troubleshooting (Only Essentials)

- `Not enough data`: reduce `--days` or use a higher timeframe (`1h`, `4h`).
- `API rate limit exceeded`: wait and rerun.
- No/low trades: check group RSI/MACD + SL/TP in `config.STRATEGY_GROUPS`.

## 6) Optional (via main.py)

```bash
python main.py --backtest --backtest-symbol BTC/USDT --backtest-days 30 --backtest-timeframe 30m
```

## Related Files

- [config.py](config.py)
- [backtest.py](backtest.py)
- [run_backtest.py](run_backtest.py)
- [strategy.py](strategy.py)
