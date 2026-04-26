#!/usr/bin/env python3
"""
CLI Tool for Running Backtests.

Usage:
    python run_backtest.py --symbol BTC/USDT --days 365 --timeframe 15m
    python run_backtest.py --symbol ETH/USDT --days 730 --timeframe 1h
"""

import argparse
import json
import logging
from pathlib import Path

import config
from backtest import (
    print_backtest_report,
    print_walk_forward_report,
    run_backtest,
    run_walk_forward,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run backtest on historical data")
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDT",
        help="Trading pair (default: BTC/USDT)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Days of history to backtest (default: 365)"
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="15m",
        help="Candle timeframe (default: 15m)"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100.0,
        help="Initial capital in USDT (default: 100)"
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Export results to JSON file (optional)"
    )
    parser.add_argument(
        "--multi-symbol",
        action="store_true",
        help="Run backtest on all symbols in config"
    )
    parser.add_argument(
        "--grouped-timeframes",
        action="store_true",
        help="Use timeframe from strategy group for each symbol"
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward validation instead of a single backtest"
    )
    parser.add_argument(
        "--wf-windows",
        type=int,
        default=5,
        help="Number of walk-forward windows (default: 5)"
    )
    parser.add_argument(
        "--wf-warmup",
        type=int,
        default=100,
        help="Warmup candles excluded from each window's metrics (default: 100)"
    )

    args = parser.parse_args()
    
    symbols = config.SYMBOLS if args.multi_symbol else [args.symbol]
    
    logger.info("=" * 90)
    logger.info("BACKTEST ENGINE - Advanced Analysis with Stop-Loss, Take-Profit, Fees & Slippage")
    logger.info("=" * 90)
    logger.info("Config: SL=%s%%, TP=%s%%, Fee=%s%%, Slippage=%s%%",
                config.STOP_LOSS_PCT, config.TAKE_PROFIT_PCT,
                config.TAKER_FEE_PCT, config.SLIPPAGE_PCT)
    logger.info("")
    
    all_results = []
    
    for symbol in symbols:
        try:
            symbol_cfg = config.get_symbol_config(symbol)
            timeframe = config.get_symbol_timeframe(symbol) if args.grouped_timeframes else args.timeframe
            logger.info("Backtesting %s...", symbol)
            logger.info(
                "Profile=%s | Timeframe=%s | Allocation=%.2f%% | SL=%.2f%% | TP=%.2f%%",
                symbol_cfg["group"],
                timeframe,
                float(symbol_cfg["trade_allocation"]) * 100,
                float(symbol_cfg["stop_loss_pct"]),
                float(symbol_cfg["take_profit_pct"]),
            )

            if args.walk_forward:
                wf_result = run_walk_forward(
                    symbol=symbol,
                    timeframe=timeframe,
                    days_back=args.days,
                    n_windows=args.wf_windows,
                    warmup_candles=args.wf_warmup,
                    initial_capital=args.capital,
                )
                print_walk_forward_report(wf_result)
            else:
                metrics = run_backtest(
                    symbol=symbol,
                    timeframe=timeframe,
                    days_back=args.days,
                    initial_capital=args.capital,
                )
                print_backtest_report(metrics)
                all_results.append(metrics)

        except Exception as exc:
            logger.error("Failed to backtest %s: %s", symbol, exc, exc_info=True)
    
    # Export results if requested
    if args.export and all_results:
        output_file = Path(args.export)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        export_data = {
            "backtest_results": [m.to_dict() for m in all_results],
            "config": {
                "enable_stops": config.ENABLE_STOPS,
                "stop_loss_pct": config.STOP_LOSS_PCT,
                "take_profit_pct": config.TAKE_PROFIT_PCT,
                "taker_fee_pct": config.TAKER_FEE_PCT,
                "slippage_pct": config.SLIPPAGE_PCT,
            }
        }
        
        with open(output_file, "w") as f:
            json.dump(export_data, f, indent=2)
        
        logger.info("Results exported to: %s", output_file)
    
    # Summary
    if all_results:
        logger.info("")
        logger.info("=" * 90)
        logger.info("SUMMARY")
        logger.info("=" * 90)
        
        for metrics in all_results:
            print(f"{metrics.symbol:12s} | Return: {metrics.realized_pnl_pct:+7.2f}% | Trades: {metrics.total_trades:4d} | "
                  f"Win Rate: {metrics.win_rate_pct:5.1f}% | Sharpe: {metrics.sharpe_ratio:6.2f} | "
                  f"Drawdown: {metrics.max_drawdown_pct:6.2f}%")


if __name__ == "__main__":
    main()
