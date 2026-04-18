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
TELEGRAM_SEND_LOOP_SUMMARY = True

# --- Pairs & timeframe ---
SYMBOLS = ["BTC/USDT", "ETH/USDT"]
TIMEFRAME = "30m"          # '1m', '5m', '15m', '1h', '4h', '1d'
OHLCV_LIMIT = 200         # nombre de bougies à récupérer

# --- Paper trading ---
INITIAL_CAPITAL_USDT = 100.0   # capital fictif de départ
TRADE_ALLOCATION = 0.10           # fraction du capital par trade (10%)

# --- Stratégie RSI ---
RSI_PERIOD = 14
RSI_OVERSOLD = 35         # signal BUY en dessous de ce seuil
RSI_OVERBOUGHT = 65       # signal SELL au-dessus de ce seuil

# --- Stratégie MACD ---
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# --- Boucle principale ---
LOOP_INTERVAL_SECONDS = 1800  # une itération toutes les 30 minutes (aligné sur timeframe 30m)

# --- Optimisation des timeframes ---
OPTIMIZATION_TIMEFRAMES = ["30m", "1h", "4h"]
OPTIMIZATION_OHLCV_LIMIT = 1000
