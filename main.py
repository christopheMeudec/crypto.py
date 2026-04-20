"""
Crypto Trading Bot — BTC/USDT & ETH/USDT
Exchange  : Binance (données publiques OHLCV)
Stratégie : RSI(14) + MACD(12,26,9)
Mode      : Paper trading (aucun ordre réel)
"""

import argparse
import logging
import threading
import time

import config
from api_server import start_server_in_thread
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
    state_lock = threading.Lock()

    logger.info("Bot démarré | Capital initial : $%.2f USDT", config.INITIAL_CAPITAL_USDT)
    logger.info("Paires : %s | Timeframe : %s", config.SYMBOLS, config.TIMEFRAME)

    if config.API_ENABLED:
        def state_provider() -> dict:
            with state_lock:
                prices = dict(latest_prices)
                snapshot = trader.create_snapshot(prices)
                return {
                    "stats": snapshot,
                    "positions": snapshot["positions"],
                    "trades": trader.get_recent_trades(limit=200),
                    "history": trader.get_history(limit=1000),
                }

        start_server_in_thread(state_provider)

    if notifier.enabled and config.TELEGRAM_ENABLE_COMMANDS:
        def command_handler(command: str, args: list[str]) -> str:
            with state_lock:
                prices = dict(latest_prices)
                snapshot = trader.create_snapshot(prices)

            cmd = command.lower()
            if cmd in {"stats", "pnl"}:
                return (
                    "Stats portefeuille\n"
                    f"USDT: ${snapshot['usdt_balance']:,.2f}\n"
                    f"Portfolio: ${snapshot['portfolio_value']:,.2f}\n"
                    f"PnL: {snapshot['pnl']:+,.2f} USDT ({snapshot['pnl_pct']:+.2f}%)\n"
                    f"Trades: {snapshot['trade_count']}"
                )
            if cmd in {"positions", "pos"}:
                positions = snapshot["positions"]
                if not positions:
                    return "Aucune position ouverte."
                lines = ["Positions ouvertes"]
                for item in positions:
                    lines.append(
                        f"- {item['symbol']}: {item['quantity']:.6f} (~${item['value']:,.2f})"
                    )
                return "\n".join(lines)
            if cmd == "trades":
                limit = 5
                if args:
                    try:
                        limit = int(args[0])
                    except ValueError:
                        pass
                rows = trader.get_recent_trades(limit=max(1, min(limit, 20)))
                if not rows:
                    return "Aucun trade enregistre pour le moment."
                lines = ["Derniers trades"]
                for t in rows:
                    lines.append(
                        f"- {t['timestamp'][:19]} | {t['side']} {t['symbol']} @ ${t['price']:,.2f} | q={t['quantity']:.6f}"
                    )
                return "\n".join(lines)
            return "Commandes: /stats, /positions, /trades [N]"

        notifier.start_command_listener(command_handler)

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
                with state_lock:
                    latest_prices[symbol] = current_price

                # Vérifier & fermer automatiquement les SL/TP
                closed_entries = trader._auto_close_entries(symbol, current_price)
                if closed_entries:
                    logger.info("[%s] %d position(s) fermée(s) par SL/TP", symbol, len(closed_entries))

                signal = get_signal(df)
                logger.info("[%s] Prix : $%.2f  |  Signal : %s", symbol, current_price, signal)

                entry_result = None
                if signal == "BUY":
                    entry_result = trader.buy(symbol, current_price)
                elif signal == "SELL":
                    # Vérifier s'il y a des positions ouvertes à vendre
                    if trader.get_total_quantity(symbol) > 0:
                        entry_result = trader.sell(symbol, current_price)
                    else:
                        logger.info("[%s] Aucune position ouverte à vendre.", symbol)

                if entry_result and notifier.enabled:
                    with state_lock:
                        prices_for_metrics = dict(latest_prices)
                    total, pnl, pnl_pct = trader.pnl_metrics(prices_for_metrics)
                    
                    # Déterminer le side pour la notification
                    if entry_result.status == "OPEN":
                        side = "BUY"
                        price = entry_result.entry_price
                        quantity = entry_result.entry_quantity
                    else:
                        # Fermée (CLOSED, SL_HIT, TP_HIT)
                        side = f"SELL ({entry_result.status})"
                        price = entry_result.exit_price or entry_result.entry_price
                        quantity = entry_result.entry_quantity
                    
                    notifier.send_trade(
                        symbol=symbol,
                        side=side,
                        price=price,
                        quantity=quantity,
                        total_value=total,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        usdt_balance=trader.usdt_balance,
                    )

            except Exception as exc:
                logger.error("[%s] Erreur lors du traitement : %s", symbol, exc)

        # Résumé du portefeuille après chaque itération
        with state_lock:
            current_prices = dict(latest_prices)
        trader.print_summary(current_prices)
        trader.record_snapshot(current_prices)

        if notifier.enabled and config.TELEGRAM_SEND_LOOP_SUMMARY:
            total, pnl, pnl_pct = trader.pnl_metrics(current_prices)
            notifier.send_loop_summary(
                prices=current_prices,
                total_value=total,
                pnl=pnl,
                pnl_pct=pnl_pct,
                usdt_balance=trader.usdt_balance,
                positions=trader.get_positions_by_symbol(),
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
