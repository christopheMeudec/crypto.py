"""
Crypto Trading Bot — BTC/USDT & ETH/USDT
Exchange  : Binance (données publiques OHLCV)
Stratégie : RSI(14) + MACD(12,26,9)
Mode      : Paper trading (aucun ordre réel)
"""

import argparse
import logging
import time

import config
from data_fetcher import fetch_ohlcv
from optimizer import optimize_timeframes
from paper_trader import PaperTrader
from strategy import get_signal
from telegram_notifier import TelegramNotifier

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def run() -> None:
    trader = PaperTrader(initial_capital=config.INITIAL_CAPITAL_USDT)
    notifier = TelegramNotifier.from_config()
    latest_prices: dict[str, float] = {}

    logger.info("Bot démarré | Capital initial : $%.2f USDT", config.INITIAL_CAPITAL_USDT)
    logger.info("Paires : %s | Timeframe : %s", config.SYMBOLS, config.TIMEFRAME)
    if notifier.enabled:
        notifier.send_message(
            f"Bot started\nPairs: {', '.join(config.SYMBOLS)}\nTimeframe: {config.TIMEFRAME}\nCapital: ${config.INITIAL_CAPITAL_USDT:,.2f}"
        )
    else:
        logger.info("Telegram desactive (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquants).")

    while True:
        prices: dict[str, float] = {}

        for symbol in config.SYMBOLS:
            try:
                df = fetch_ohlcv(symbol, config.TIMEFRAME)
                current_price = float(df["close"].iloc[-1])
                prices[symbol] = current_price
                latest_prices[symbol] = current_price

                signal = get_signal(df)
                logger.info("[%s] Prix : $%.2f  |  Signal : %s", symbol, current_price, signal)

                trade = None
                if signal == "BUY":
                    trade = trader.buy(symbol, current_price)
                elif signal == "SELL":
                    trade = trader.sell(symbol, current_price)

                if trade and notifier.enabled:
                    total, pnl, pnl_pct = trader.pnl_metrics(latest_prices)
                    notifier.send_trade(
                        symbol=trade.symbol,
                        side=trade.side,
                        price=trade.price,
                        quantity=trade.quantity,
                        total_value=total,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        usdt_balance=trader.usdt_balance,
                    )

            except Exception as exc:
                logger.error("[%s] Erreur lors du traitement : %s", symbol, exc)

        # Résumé du portefeuille après chaque itération
        trader.print_summary(latest_prices)

        if notifier.enabled and config.TELEGRAM_SEND_LOOP_SUMMARY:
            total, pnl, pnl_pct = trader.pnl_metrics(latest_prices)
            notifier.send_loop_summary(
                prices=latest_prices,
                total_value=total,
                pnl=pnl,
                pnl_pct=pnl_pct,
                usdt_balance=trader.usdt_balance,
                positions=trader.positions,
            )

        logger.info("Prochaine itération dans %d secondes…", config.LOOP_INTERVAL_SECONDS)
        time.sleep(config.LOOP_INTERVAL_SECONDS)


def run_timeframe_optimization(history_limit: int) -> None:
    logger.info("Lancement optimisation timeframes %s", config.OPTIMIZATION_TIMEFRAMES)
    logger.info("Paires: %s | Historique: %d bougies", config.SYMBOLS, history_limit)

    results = optimize_timeframes(
        symbols=config.SYMBOLS,
        timeframes=config.OPTIMIZATION_TIMEFRAMES,
        history_limit=history_limit,
    )

    if not results:
        logger.warning("Aucun resultat d'optimisation.")
        return

    logger.info("-" * 88)
    logger.info("Timeframe |   Final Value |       PnL |   PnL%% | Trades | MaxDD%% |   Score")
    logger.info("-" * 88)
    for r in results:
        logger.info(
            "%9s | %12.2f | %+9.2f | %+6.2f | %6d | %6.2f | %7.2f",
            r.timeframe,
            r.final_value,
            r.pnl,
            r.pnl_pct,
            r.trades,
            r.max_drawdown_pct,
            r.score,
        )
    logger.info("-" * 88)

    best = results[0]
    logger.info(
        "Timeframe recommande: %s (score %.2f, PnL %+.2f%%, MaxDD %.2f%%)",
        best.timeframe,
        best.score,
        best.pnl_pct,
        best.max_drawdown_pct,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto paper trading bot")
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Backtest automatiquement les timeframes 30m/1h/4h puis quitter",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=config.OPTIMIZATION_OHLCV_LIMIT,
        help="Nombre de bougies OHLCV utilisees en mode optimisation",
    )
    args = parser.parse_args()

    if args.optimize:
        run_timeframe_optimization(history_limit=args.history_limit)
    else:
        run()
