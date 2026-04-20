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
SYMBOLS = ["BTC/USDT", "ETH/USDT"]
TIMEFRAME = "1h"          # '1m', '5m', '15m', '1h', '4h', '1d'
OHLCV_LIMIT = 200         # nombre de bougies à récupérer

# --- Paper trading ---
INITIAL_CAPITAL_USDT = 100.0   # capital fictif de départ
TRADE_ALLOCATION = 0.25           # fraction du capital par trade (10%)

# --- Stratégie RSI ---
RSI_PERIOD = 14
RSI_OVERSOLD = 40         # signal BUY en dessous de ce seuil
RSI_OVERBOUGHT = 60       # signal SELL au-dessus de ce seuil

# --- Stratégie MACD ---
MACD_FAST = 8
MACD_SLOW = 21
MACD_SIGNAL = 5

# --- Gestion du risque : Stop-Loss & Take-Profit ---
ENABLE_STOPS = True               # Activer/désactiver SL & TP
STOP_LOSS_PCT = -5.0              # Stop-loss en % (ex: -5% = ferme à 95% du prix d'entrée)
TAKE_PROFIT_PCT = 10.0             # Take-profit en % (ex: 10% = ferme à 110% du prix d'entrée)

# --- Frais & Slippage (simulation réaliste) ---
TAKER_FEE_PCT = 0.1               # Frais taker Binance (0.1%)
SLIPPAGE_PCT = 0.05               # Slippage moyen sur les ordres (0.05%)

# --- Boucle principale ---
LOOP_INTERVAL_SECONDS = 3600  # une itération toutes les 1 heure (aligné sur timeframe 1h)

# --- Persistance locale ---
DATA_DIR = os.getenv("DATA_DIR", "data")
MAX_STORED_TRADES = int(os.getenv("MAX_STORED_TRADES", "2000"))
MAX_STORED_SNAPSHOTS = int(os.getenv("MAX_STORED_SNAPSHOTS", "3000"))

# --- API mobile (lecture seule) ---
API_ENABLED = os.getenv("API_ENABLED", "true").lower() == "true"
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_TOKEN = os.getenv("API_TOKEN", "")
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "Europe/Paris")

# --- Optimisation des timeframes ---
OPTIMIZATION_TIMEFRAMES = ["15m","30m", "1h", "4h"]
OPTIMIZATION_OHLCV_LIMIT = 1000
