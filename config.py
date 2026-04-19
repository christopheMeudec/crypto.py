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
TIMEFRAME = "15m"          # '1m', '5m', '15m', '1h', '4h', '1d'
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

# --- Boucle principale ---
LOOP_INTERVAL_SECONDS = 900  # une itération toutes les 15 minutes (aligné sur timeframe 15m)

# --- Optimisation des timeframes ---
OPTIMIZATION_TIMEFRAMES = ["15m","30m", "1h", "4h"]
OPTIMIZATION_OHLCV_LIMIT = 1000
