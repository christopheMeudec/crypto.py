import os
from dotenv import load_dotenv

load_dotenv()

# --- Exchange ---
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# --- Telegram notifications ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
TELEGRAM_SEND_LOOP_SUMMARY = False
TELEGRAM_ENABLE_COMMANDS = True
TELEGRAM_POLL_INTERVAL_SECONDS = 1
TELEGRAM_LONG_POLL_TIMEOUT_SECONDS = int(os.getenv("TELEGRAM_LONG_POLL_TIMEOUT_SECONDS", "25"))
TELEGRAM_HTTP_TIMEOUT_SECONDS = int(os.getenv("TELEGRAM_HTTP_TIMEOUT_SECONDS", "35"))
TELEGRAM_POLL_ERROR_BACKOFF_SECONDS = int(os.getenv("TELEGRAM_POLL_ERROR_BACKOFF_SECONDS", "10"))

# --- Pairs & timeframe ---
TIMEFRAME = "30m"          # fallback global
OHLCV_LIMIT = 200         # nombre de bougies à récupérer

# --- Paper trading ---
INITIAL_CAPITAL_USDT = 100.0   # capital fictif de départ
TRADE_ALLOCATION = 0.20           # fraction du capital par trade (10%)

# --- Stratégie RSI ---
RSI_PERIOD = 14
RSI_OVERSOLD = 35         # signal BUY en dessous de ce seuil
RSI_OVERBOUGHT = 65       # signal SELL au-dessus de ce seuil

# --- Stratégie MACD ---
MACD_FAST = 8
MACD_SLOW = 26
MACD_SIGNAL = 9

# --- Gestion du risque : Stop-Loss & Take-Profit ---
ENABLE_STOPS = True               # Activer/désactiver SL & TP
STOP_LOSS_PCT = -3.0              # Stop-loss en % (ex: -5% = ferme à 95% du prix d'entrée)
TAKE_PROFIT_PCT = 6.0             # Take-profit en % (ex: 10% = ferme à 110% du prix d'entrée)

# --- Frais & Slippage (simulation réaliste) ---
TAKER_FEE_PCT = 0.1               # Frais taker Binance (0.1%)
SLIPPAGE_PCT = 0.05               # Slippage moyen sur les ordres (0.05%)

# --- Boucle principale ---
LOOP_INTERVAL_SECONDS = 1800  # une itération toutes les 30 minutes (aligné sur timeframe 30m)

# --- Groupes de stratégie (majors vs alts volatiles) ---
SUPPORTED_TIMEFRAMES_SECONDS = {
	"1m": 60,
	"5m": 300,
	"15m": 900,
	"30m": 1800,
	"1h": 3600,
	"2h": 7200,
	"4h": 14400,
	"1d": 86400,
}

DEFAULT_SYMBOL_STRATEGY = {
	"timeframe": TIMEFRAME,
	"rsi_period": RSI_PERIOD,
	"rsi_oversold": RSI_OVERSOLD,
	"rsi_overbought": RSI_OVERBOUGHT,
	"macd_fast": MACD_FAST,
	"macd_slow": MACD_SLOW,
	"macd_signal": MACD_SIGNAL,
	"trade_allocation": TRADE_ALLOCATION,
	"stop_loss_pct": STOP_LOSS_PCT,
	"take_profit_pct": TAKE_PROFIT_PCT,
}

STRATEGY_GROUPS = {
	"majors": {
		"symbols": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
		"timeframe": "1h",
		"rsi_period": 14,
		"rsi_oversold": 36,
		"rsi_overbought": 67,
		"macd_fast": 8,
		"macd_slow": 26,
		"macd_signal": 9,
		"trade_allocation": 0.20,
		"stop_loss_pct": -4.0,
		"take_profit_pct": 8.0,
	},
	"alts": {
		"symbols": ["ADA/USDT", "XRP/USDT", "DOGE/USDT", "MATIC/USDT"],
		"timeframe": "30m",
		"rsi_period": 14,
		"rsi_oversold": 34,
		"rsi_overbought": 64,
		"macd_fast": 8,
		"macd_slow": 26,
		"macd_signal": 9,
		"trade_allocation": 0.12,
		"stop_loss_pct": -2.5,
		"take_profit_pct": 5.5,
	},
}


def timeframe_to_seconds(timeframe: str) -> int:
	return SUPPORTED_TIMEFRAMES_SECONDS[timeframe]


def _flatten_symbols_from_groups() -> list[str]:
	flattened: list[str] = []
	for group_cfg in STRATEGY_GROUPS.values():
		flattened.extend(group_cfg.get("symbols", []))
	return flattened


def get_symbol_group(symbol: str) -> str | None:
	for group_name, group_cfg in STRATEGY_GROUPS.items():
		if symbol in group_cfg.get("symbols", []):
			return group_name
	return None


def get_symbol_config(symbol: str) -> dict:
	resolved = dict(DEFAULT_SYMBOL_STRATEGY)
	group_name = get_symbol_group(symbol)
	if group_name:
		resolved.update(STRATEGY_GROUPS[group_name])
		resolved["group"] = group_name
	else:
		resolved["symbols"] = [symbol]
		resolved["group"] = "default"
	return resolved


def get_symbol_timeframe(symbol: str) -> str:
	return str(get_symbol_config(symbol)["timeframe"])


def _validate_strategy_groups() -> None:
	seen_symbols: set[str] = set()
	for group_name, group_cfg in STRATEGY_GROUPS.items():
		symbols = group_cfg.get("symbols", [])
		if not symbols:
			raise ValueError(f"Strategy group '{group_name}' has no symbols.")

		timeframe = str(group_cfg.get("timeframe", TIMEFRAME))
		if timeframe not in SUPPORTED_TIMEFRAMES_SECONDS:
			raise ValueError(f"Strategy group '{group_name}' has unsupported timeframe '{timeframe}'.")

		allocation = float(group_cfg.get("trade_allocation", TRADE_ALLOCATION))
		if allocation <= 0 or allocation > 1:
			raise ValueError(f"Strategy group '{group_name}' has invalid trade_allocation {allocation}.")

		for symbol in symbols:
			if symbol in seen_symbols:
				raise ValueError(f"Symbol '{symbol}' is defined in multiple strategy groups.")
			seen_symbols.add(symbol)


_validate_strategy_groups()
SYMBOLS = _flatten_symbols_from_groups()

# --- Persistance locale ---
DATA_DIR = os.getenv("DATA_DIR", "data")
BACKTEST_DATA_DIR = os.getenv("BACKTEST_DATA_DIR", os.path.join(DATA_DIR, "backtest"))
BACKTEST_PERSIST_TRADES = os.getenv("BACKTEST_PERSIST_TRADES", "false").lower() == "true"
MAX_STORED_TRADES = int(os.getenv("MAX_STORED_TRADES", "2000"))
MAX_STORED_SNAPSHOTS = int(os.getenv("MAX_STORED_SNAPSHOTS", "3000"))

# --- API mobile (lecture seule) ---
API_ENABLED = os.getenv("API_ENABLED", "true").lower() == "true"
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_TOKEN = os.getenv("API_TOKEN", "")
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "Europe/Paris")

# --- Optimisation des timeframes ---
OPTIMIZATION_TIMEFRAMES = ["30m", "1h", "2h", "4h"]
OPTIMIZATION_OHLCV_LIMIT = 1000
