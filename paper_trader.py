from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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

    def to_dict(self) -> Dict[str, float | str]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "timestamp": self.timestamp.isoformat(),
        }


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
        self.data_dir = Path(config.DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.trades_file = self.data_dir / "trades.json"
        self.snapshots_file = self.data_dir / "portfolio_snapshots.json"

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
        self._persist_trade(trade)
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
        self._persist_trade(trade)
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

    def create_snapshot(self, prices: Dict[str, float]) -> Dict[str, object]:
        total, pnl, pnl_pct = self.pnl_metrics(prices)
        positions = []
        for symbol, qty in self.positions.items():
            if qty <= 0:
                continue
            price = prices.get(symbol, 0.0)
            positions.append(
                {
                    "symbol": symbol,
                    "quantity": qty,
                    "price": price,
                    "value": qty * price,
                }
            )
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "usdt_balance": self.usdt_balance,
            "portfolio_value": total,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "positions": positions,
            "trade_count": len(self.trades),
        }

    def record_snapshot(self, prices: Dict[str, float]) -> None:
        self._append_json_record(
            self.snapshots_file,
            self.create_snapshot(prices),
            max_items=config.MAX_STORED_SNAPSHOTS,
        )

    def get_recent_trades(self, limit: int = 10) -> List[Dict[str, float | str]]:
        limit = max(1, limit)
        return [trade.to_dict() for trade in self.trades[-limit:]][::-1]

    def get_history(self, limit: int = 120) -> List[Dict[str, object]]:
        records = self._read_json_array(self.snapshots_file)
        return records[-max(1, limit):]

    def _persist_trade(self, trade: Trade) -> None:
        self._append_json_record(
            self.trades_file,
            trade.to_dict(),
            max_items=config.MAX_STORED_TRADES,
        )

    @staticmethod
    def _read_json_array(path: Path) -> List[Dict[str, object]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return payload
        except (OSError, json.JSONDecodeError):
            logger.warning("Impossible de lire %s, reinitialisation de l'historique.", path)
        return []

    @staticmethod
    def _append_json_record(path: Path, record: Dict[str, object], max_items: int) -> None:
        rows = PaperTrader._read_json_array(path)
        rows.append(record)
        if max_items > 0 and len(rows) > max_items:
            rows = rows[-max_items:]
        try:
            path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Impossible d'ecrire %s: %s", path, exc)
