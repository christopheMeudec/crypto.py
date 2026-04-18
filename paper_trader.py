from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import config

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    symbol: str
    side: str           # "BUY" | "SELL"
    price: float
    quantity: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}] "
            f"{self.side:4s} {self.quantity:.6f} {self.symbol} @ ${self.price:,.2f}"
        )


class PaperTrader:
    """
    Moteur de paper trading.

    Maintient un portefeuille fictif : solde USDT + positions pour chaque symbole.
    Les ordres sont exécutés immédiatement au prix de marché transmis.
    """

    def __init__(self, initial_capital: float = config.INITIAL_CAPITAL_USDT) -> None:
        self.usdt_balance: float = initial_capital
        self.positions: Dict[str, float] = {}   # symbol -> quantité détenue
        self.trades: List[Trade] = []

    # ------------------------------------------------------------------
    # Ordres
    # ------------------------------------------------------------------

    def buy(self, symbol: str, price: float) -> Trade | None:
        """Achète pour TRADE_ALLOCATION du solde USDT disponible."""
        spend = self.usdt_balance * config.TRADE_ALLOCATION
        if spend < 1.0:
            logger.warning("[%s] Solde USDT insuffisant pour acheter (%.2f USDT).", symbol, self.usdt_balance)
            return None

        quantity = spend / price
        self.usdt_balance -= spend
        self.positions[symbol] = self.positions.get(symbol, 0.0) + quantity

        trade = Trade(symbol=symbol, side="BUY", price=price, quantity=quantity)
        self.trades.append(trade)
        logger.info("%s  |  -$%.2f USDT  |  USDT restant : $%.2f", trade, spend, self.usdt_balance)
        return trade

    def sell(self, symbol: str, price: float) -> Trade | None:
        """Vend l'intégralité de la position détenue pour ce symbole."""
        quantity = self.positions.get(symbol, 0.0)
        if quantity <= 0:
            logger.warning("[%s] Aucune position à vendre.", symbol)
            return None

        proceeds = quantity * price
        self.usdt_balance += proceeds
        self.positions[symbol] = 0.0

        trade = Trade(symbol=symbol, side="SELL", price=price, quantity=quantity)
        self.trades.append(trade)
        logger.info("%s  |  +$%.2f USDT  |  USDT total : $%.2f", trade, proceeds, self.usdt_balance)
        return trade

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def portfolio_value(self, prices: Dict[str, float]) -> float:
        """Valeur totale du portefeuille en USDT au prix de marché actuel."""
        value = self.usdt_balance
        for symbol, qty in self.positions.items():
            value += qty * prices.get(symbol, 0.0)
        return value

    def pnl_metrics(self, prices: Dict[str, float]) -> Tuple[float, float, float]:
        """Retourne (total_value, pnl, pnl_pct)."""
        total = self.portfolio_value(prices)
        pnl = total - config.INITIAL_CAPITAL_USDT
        pnl_pct = (pnl / config.INITIAL_CAPITAL_USDT) * 100 if config.INITIAL_CAPITAL_USDT > 0 else 0.0
        return total, pnl, pnl_pct

    def print_summary(self, prices: Dict[str, float]) -> None:
        total, pnl, pnl_pct = self.pnl_metrics(prices)

        logger.info("=" * 60)
        logger.info("  Portefeuille — %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        logger.info("  USDT liquide  : $%.2f", self.usdt_balance)
        for symbol, qty in self.positions.items():
            price = prices.get(symbol, 0.0)
            logger.info("  %-10s    : %.6f  (~$%.2f)", symbol, qty, qty * price)
        logger.info("  Valeur totale : $%.2f", total)
        logger.info("  PnL           : %+.2f USDT (%+.2f%%)", pnl, pnl_pct)
        logger.info("  Trades        : %d", len(self.trades))
        logger.info("=" * 60)
