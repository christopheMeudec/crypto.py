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
from strategy import get_signal_with_reason
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
    latest_signal_reasons: dict[str, str] = {}
    state_lock = threading.Lock()
    symbol_profiles = {symbol: config.get_symbol_config(symbol) for symbol in config.SYMBOLS}
    symbol_intervals_seconds = {
        symbol: config.timeframe_to_seconds(str(profile["timeframe"]))
        for symbol, profile in symbol_profiles.items()
    }
    next_run_at = {symbol: time.time() for symbol in config.SYMBOLS}

    logger.info("Bot démarré | Capital initial : $%.2f USDT", config.INITIAL_CAPITAL_USDT)
    logger.info("Paires : %s", config.SYMBOLS)
    for symbol in config.SYMBOLS:
        profile = symbol_profiles[symbol]
        logger.info(
            "[%s] groupe=%s | timeframe=%s | alloc=%.2f%% | SL=%.2f%% | TP=%.2f%%",
            symbol,
            profile["group"],
            profile["timeframe"],
            float(profile["trade_allocation"]) * 100,
            float(profile["stop_loss_pct"]),
            float(profile["take_profit_pct"]),
        )

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
                    "signal_diagnostics": dict(latest_signal_reasons),
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
            if cmd == "symbols":
                lines = ["\U0001f4ca Symboles trades"]
                for s in config.SYMBOLS:
                    profile = symbol_profiles[s]
                    lines.append(f"  - {s} | {profile['group']} | {profile['timeframe']}")
                return "\n".join(lines)
            if cmd == "config":
                stops = "Actif" if config.ENABLE_STOPS else "Inactif"
                lines = [
                    "\u2699\ufe0f Configuration\n"
                    f"Capital: ${config.INITIAL_CAPITAL_USDT:,.0f} USDT\n"
                    f"Frais: {config.TAKER_FEE_PCT}% | Slippage: {config.SLIPPAGE_PCT}%\n"
                    f"Stops globaux: {stops}"
                ]
                for group_name, group_cfg in config.STRATEGY_GROUPS.items():
                    lines.append(
                        f"\n- {group_name}: tf={group_cfg['timeframe']} | alloc={float(group_cfg['trade_allocation']) * 100:.0f}% "
                        f"| RSI={group_cfg['rsi_oversold']}/{group_cfg['rsi_overbought']} "
                        f"| MACD={group_cfg['macd_fast']}/{group_cfg['macd_slow']}/{group_cfg['macd_signal']} "
                        f"| SL={group_cfg['stop_loss_pct']}% TP=+{group_cfg['take_profit_pct']}%"
                    )
                return "\n".join(lines)
            if cmd in {"diagnostic", "diag"}:
                if not latest_signal_reasons:
                    return "Diagnostic indisponible: aucun cycle encore traite."
                lines = ["Diagnostic signaux"]
                for s in config.SYMBOLS:
                    timeframe = str(symbol_profiles[s]["timeframe"])
                    reason = latest_signal_reasons.get(s, "Aucun diagnostic pour ce symbole")
                    lines.append(f"- {s} [{timeframe}] | {reason}")
                return "\n".join(lines)
            return "Commandes: /stats, /positions, /trades [N], /symbols, /config, /diagnostic"

        notifier.start_command_listener(command_handler)

    if notifier.enabled:
        notifier.send_message(
            f"Bot started\nPairs: {', '.join(config.SYMBOLS)}\nProfiles: majors={config.STRATEGY_GROUPS['majors']['timeframe']}, alts={config.STRATEGY_GROUPS['alts']['timeframe']}\nCapital: ${config.INITIAL_CAPITAL_USDT:,.2f}"
        )
    else:
        logger.info("Telegram desactive (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquants).")

    while True:
        cycle_started_at = time.time()
        prices: dict[str, float] = {}
        processed_symbols: list[str] = []

        for symbol in config.SYMBOLS:
            if cycle_started_at < next_run_at[symbol]:
                continue

            processed_symbols.append(symbol)
            profile = symbol_profiles[symbol]
            timeframe = str(profile["timeframe"])

            try:
                df = fetch_ohlcv(symbol, timeframe)
                current_price = float(df["close"].iloc[-1])
                prices[symbol] = current_price
                with state_lock:
                    latest_prices[symbol] = current_price

                # Vérifier & fermer automatiquement les SL/TP
                closed_entries = trader._auto_close_entries(symbol, current_price)
                if closed_entries:
                    logger.info("[%s] %d position(s) fermée(s) par SL/TP", symbol, len(closed_entries))

                signal, signal_reason = get_signal_with_reason(df, symbol=symbol)
                with state_lock:
                    latest_signal_reasons[symbol] = signal_reason
                logger.info(
                    "[%s][%s] Prix : $%.2f  |  Signal : %s | %s",
                    symbol,
                    timeframe,
                    current_price,
                    signal,
                    signal_reason,
                )

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
            finally:
                next_run_at[symbol] = cycle_started_at + symbol_intervals_seconds[symbol]

        if processed_symbols:
            # Résumé du portefeuille après chaque cycle utile
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

        next_due_at = min(next_run_at.values()) if next_run_at else (time.time() + 1)
        sleep_seconds = max(1, min(30, int(next_due_at - time.time())))
        if processed_symbols:
            logger.info("Cycle traité (%s). Prochaine vérification dans %d secondes.", ", ".join(processed_symbols), sleep_seconds)
        time.sleep(sleep_seconds)


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
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run comprehensive backtest with advanced metrics (Sharpe, Sortino, etc.)",
    )
    parser.add_argument(
        "--backtest-symbol",
        type=str,
        default="BTC/USDT",
        help="Symbol for backtest (default: BTC/USDT)",
    )
    parser.add_argument(
        "--backtest-days",
        type=int,
        default=30,
        help="Days of history for backtest (default: 30)",
    )
    parser.add_argument(
        "--backtest-timeframe",
        type=str,
        default="15m",
        help="Timeframe for backtest (default: 15m)",
    )
    parser.add_argument(
        "--backtest-export",
        type=str,
        default=None,
        help="Export backtest results to JSON file",
    )
    
    args = parser.parse_args()

    if args.optimize:
        run_timeframe_optimization(history_limit=args.history_limit)
    elif args.backtest:
        from backtest import run_backtest, print_backtest_report
        logger.info("Starting comprehensive backtest...")
        metrics = run_backtest(
            symbol=args.backtest_symbol,
            timeframe=args.backtest_timeframe,
            days_back=args.backtest_days,
            initial_capital=config.INITIAL_CAPITAL_USDT,
        )
        print_backtest_report(metrics)
        
        if args.backtest_export:
            import json
            from pathlib import Path
            output_file = Path(args.backtest_export)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w") as f:
                json.dump(metrics.to_dict(), f, indent=2)
            logger.info("Results exported to: %s", output_file)
    else:
        run()
