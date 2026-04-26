# CLAUDE.md

## Project overview

Python paper-trading bot for Binance crypto pairs. No real orders are ever placed — all execution is simulated by `PaperTrader`. The bot fetches public OHLCV data via CCXT, computes RSI + MACD indicators, and runs a 30-minute loop that generates BUY/SELL/HOLD signals.

## Key files

| File | Role |
|------|------|
| `main.py` | Entry point. Trading loop, circuit breaker, Telegram commands, graceful shutdown |
| `config.py` | All parameters (env-overridable). Validates strategy groups at import time |
| `paper_trader.py` | `PaperTrader` + `PositionEntry`. Thread-safe with `RLock`. JSON persistence |
| `strategy.py` | `get_signal_with_reason()`, `compute_indicators()`, `compute_atr()` |
| `data_fetcher.py` | `fetch_ohlcv()` with 3-attempt retry + exponential backoff |
| `backtest.py` | `BacktestRunner`, `run_backtest()`, `run_walk_forward()` |
| `run_backtest.py` | CLI for backtests. Supports `--walk-forward --wf-windows N --wf-warmup N` |
| `api_server.py` | Read-only REST API (FastAPI) for mobile dashboard |
| `optimizer.py` | Timeframe optimizer (grid search over historical data) |
| `telegram_notifier.py` | Telegram bot: push notifications + `/stats`, `/positions`, `/diagnostic` |

## Development commands

```bash
# Run the bot
python main.py

# Run tests (fast — no network calls)
python -m pytest tests/ -v

# Backtest a single symbol
python run_backtest.py --symbol BTC/USDT --days 365 --timeframe 30m

# Walk-forward validation (5 windows, 100 warmup candles)
python run_backtest.py --symbol BTC/USDT --walk-forward --wf-windows 5 --wf-warmup 100

# Backtest all symbols with per-group timeframes
python run_backtest.py --multi-symbol --grouped-timeframes --days 180
```

## Architecture decisions to respect

**Thread safety**: `PaperTrader` uses `threading.RLock` (reentrant). `_auto_close_entries()` holds the lock and calls `_close_entry()` — keep it reentrant. Never replace `RLock` with `Lock`.

**Strategy groups**: symbols are declared in `STRATEGY_GROUPS` in `config.py`, not in a database or env file. Adding a symbol means adding it to the right group dict. `_validate_strategy_groups()` runs at import time and will raise if misconfigured.

**SL/TP modes**: two mutually exclusive modes controlled by `USE_ATR_STOPS`.
- `False` (default): fixed percentage from `stop_loss_pct` / `take_profit_pct` in the group config
- `True`: `SL = price − ATR_MULTIPLIER_SL × ATR`, `TP = price + ATR_MULTIPLIER_TP × ATR`
If `USE_ATR_STOPS=True` but ATR cannot be computed (not enough candles), it silently falls back to percentage stops.

**Trailing stop**: opt-in via `ENABLE_TRAILING_STOP`. Tracked via `peak_price` on each `PositionEntry`. Status `"TS_HIT"` is distinct from `"SL_HIT"`. Can coexist with ATR stops or percentage stops.

**Persistence**: only OPEN entries are stored in `state.json`. Closed entries live in `trades.json`. `initial_capital` is never overwritten at restore — only `usdt_balance` and `entries`.

**Backtest isolation**: `BacktestRunner` creates a `PaperTrader` with `persist=config.BACKTEST_PERSIST_TRADES` (default `False`). Never pass a live trader to backtest code.

## Testing conventions

Tests live in `tests/`. All tests run without network access — `data_fetcher` and `strategy.compute_indicators` are monkeypatched where needed.

```bash
python -m pytest tests/ -v --tb=short   # standard run
```

- `conftest.py` exposes shared fixtures (`trader`, `trader_no_stops`) and indicator scenario constants (`BUY_DIRECT`, `SELL_DIRECT`, etc.)
- Use `monkeypatch.setattr(config, "PARAM", value)` to override config in a test — never mutate `config` directly
- Walk-forward tests monkeypatch `backtest.fetch_ohlcv_long` to avoid network calls
- `persist=False` on every `PaperTrader` created in tests

## Configuration

Copy `.env.example` to `.env`. The most important variables:

```
BINANCE_API_KEY / BINANCE_API_SECRET   # optional for public OHLCV
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  # required for Telegram features
INITIAL_CAPITAL_USDT=100.0
MAX_OPEN_POSITIONS=5
DAILY_DRAWDOWN_LIMIT_PCT=-5.0
USE_ATR_STOPS=false
ENABLE_TRAILING_STOP=false
TRAILING_STOP_PCT=-2.0
LOG_DIR=logs
DATA_DIR=data
API_TOKEN=change_me
```

Strategy parameters (RSI thresholds, MACD windows, allocation %, SL/TP %) are defined directly in `config.py` under `STRATEGY_GROUPS` — they are not env-overridable per group by design.

## CI

GitHub Actions (`.github/workflows/tests.yml`) runs `pytest tests/` on every push/PR to `main` using Python 3.12. Requirements are cached via `pip`.
