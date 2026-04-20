#!/bin/bash
# Quick Backtest Commands
# Copy-paste these commands into your terminal for quick backtesting

# ============================================================================
# SINGLE PAIR BACKTESTS
# ============================================================================

# Quick test: 30 days, BTC
python run_backtest.py --symbol BTC/USDT --days 30

# Quick test: 30 days, ETH
python run_backtest.py --symbol ETH/USDT --days 30

# Medium test: 90 days, BTC with export
python run_backtest.py --symbol BTC/USDT --days 90 --export data/backtest_btc_90d.json

# Long test: 365 days, BTC (takes ~30-60 seconds)
python run_backtest.py --symbol BTC/USDT --days 365 --timeframe 1h

# Different timeframe: 4 hours
python run_backtest.py --symbol BTC/USDT --days 180 --timeframe 4h

# Custom capital
python run_backtest.py --symbol ETH/USDT --days 90 --capital 1000

# ============================================================================
# MULTI-SYMBOL BACKTESTS
# ============================================================================

# Test all symbols (from config.SYMBOLS)
python run_backtest.py --multi-symbol --days 30

# All symbols, 90 days, export
python run_backtest.py --multi-symbol --days 90 --export data/backtest_all_90d.json

# All symbols, 1h timeframe
python run_backtest.py --multi-symbol --days 180 --timeframe 1h

# ============================================================================
# VIA main.py
# ============================================================================

# Basic backtest
python main.py --backtest

# Custom symbol
python main.py --backtest --backtest-symbol ETH/USDT --backtest-days 60

# With export
python main.py --backtest --backtest-symbol BTC/USDT --backtest-export my_backtest.json

# ============================================================================
# PYTHON API (Create a script with these)
# ============================================================================

# Script: my_backtest.py
cat > my_backtest.py << 'EOF'
from backtest import run_backtest, print_backtest_report

# Single symbol
metrics = run_backtest("BTC/USDT", days_back=90)
print_backtest_report(metrics)

# Or programmatic access
print(f"Return: {metrics.realized_pnl_pct:.2f}%")
print(f"Sharpe: {metrics.sharpe_ratio:.2f}")
EOF

python my_backtest.py

# ============================================================================
# BATCH BACKTEST MULTIPLE PAIRS
# ============================================================================

# Script: batch_backtest.py
cat > batch_backtest.py << 'EOF'
from backtest import run_backtest, print_backtest_report

symbols = ["BTC/USDT", "ETH/USDT", "XRP/USDT"]
for symbol in symbols:
    print(f"\n{'='*80}\nBacktesting {symbol}\n{'='*80}")
    metrics = run_backtest(symbol, days_back=30)
    print_backtest_report(metrics)
EOF

python batch_backtest.py

# ============================================================================
# PARAMETER OPTIMIZATION
# ============================================================================

# Script: optimize_sl_tp.py
cat > optimize_sl_tp.py << 'EOF'
from backtest import run_backtest
import config

print("SL%\tTP%\tReturn%\tSharpe\tWinRate%")
print("-" * 50)

for sl in [-1.0, -2.0, -3.0, -5.0]:
    for tp in [3.0, 5.0, 7.0, 10.0]:
        config.STOP_LOSS_PCT = sl
        config.TAKE_PROFIT_PCT = tp
        
        metrics = run_backtest("BTC/USDT", days_back=30)
        print(f"{sl:.1f}\t{tp:.1f}\t{metrics.realized_pnl_pct:+.2f}\t{metrics.sharpe_ratio:+.2f}\t{metrics.win_rate_pct:.0f}")
EOF

python optimize_sl_tp.py

# ============================================================================
# ANALYZE EXPORTED JSON
# ============================================================================

# Script: analyze_results.py
cat > analyze_results.py << 'EOF'
import json
from pathlib import Path

with open("data/backtest_results.json") as f:
    data = json.load(f)

print("Backtest Results Summary")
print("=" * 80)

for result in data["backtest_results"]:
    symbol = result["symbol"]
    return_pct = result["realized_pnl_pct"]
    sharpe = result["sharpe_ratio"]
    dd = result["max_drawdown_pct"]
    trades = result["total_trades"]
    
    print(f"{symbol:12} | Return: {return_pct:+7.2f}% | Sharpe: {sharpe:+6.2f} | DD: {dd:6.2f}% | Trades: {trades:4d}")
EOF

python analyze_results.py

# ============================================================================
# HELPFUL TIPS
# ============================================================================

# View help
python run_backtest.py --help
python main.py --help

# Check current config
python -c "import config; print(f'SL: {config.STOP_LOSS_PCT}%, TP: {config.TAKE_PROFIT_PCT}%, Fee: {config.TAKER_FEE_PCT}%')"

# Quick json formatting
python -m json.tool data/backtest_results.json | head -50

# Count trades in JSON
python -c "import json; d=json.load(open('data/backtest_results.json')); print(f\"Total trades: {sum(r['total_trades'] for r in d['backtest_results'])}\")"
