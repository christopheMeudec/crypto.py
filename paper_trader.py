from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config

logger = logging.getLogger(__name__)


def _now_local() -> datetime:
    try:
        return datetime.now(ZoneInfo(config.LOCAL_TIMEZONE))
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc)


@dataclass
class PositionEntry:
    """
    Représente une position unique (un achat avec son potentiel SL/TP).
    Une seule position par entry, avec tracking de l'entrée et de la sortie.
    """
    entry_id: str                              # UUID unique
    symbol: str
    entry_price: float
    entry_quantity: float
    entry_timestamp: datetime
    entry_fee: float                           # Frais payés à l'achat
    entry_cost_basis: float                    # qty * entry_price + entry_fee
    strategy_group: str = "default"
    strategy_timeframe: str = config.TIMEFRAME
    
    stop_loss_price: float | None = None       # Calculé à l'entrée si SL actif
    take_profit_price: float | None = None     # Calculé à l'entrée si TP actif
    
    # Remplies lors de la fermeture
    exit_price: float | None = None
    exit_quantity: float | None = None
    exit_fee: float | None = None
    exit_timestamp: datetime | None = None
    
    # Résultats calculés à la fermeture
    realized_pnl: float | None = None
    realized_pnl_pct: float | None = None
    
    status: str = "OPEN"                       # "OPEN" | "CLOSED" | "SL_HIT" | "TP_HIT"
    
    def __str__(self) -> str:
        """Format lisible de la position."""
        if self.status == "OPEN":
            return f"[OPEN] {self.symbol} @ ${self.entry_price:,.2f} qty={self.entry_quantity:.6f}"
        else:
            pnl_str = f"{self.realized_pnl:+.2f} ({self.realized_pnl_pct:+.2f}%)" if self.realized_pnl is not None else "N/A"
            return f"[{self.status}] {self.symbol} {self.entry_quantity:.6f} @ ${self.entry_price:,.2f} → ${self.exit_price:,.2f} | PnL: {pnl_str}"
    
    def to_dict(self) -> Dict[str, object]:
        """Sérialise la position pour JSON."""
        return {
            "entry_id": self.entry_id,
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "entry_quantity": self.entry_quantity,
            "entry_fee": self.entry_fee,
            "entry_cost_basis": self.entry_cost_basis,
            "strategy_group": self.strategy_group,
            "strategy_timeframe": self.strategy_timeframe,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "entry_timestamp": self.entry_timestamp.isoformat(),
            "exit_price": self.exit_price,
            "exit_quantity": self.exit_quantity,
            "exit_fee": self.exit_fee,
            "exit_timestamp": self.exit_timestamp.isoformat() if self.exit_timestamp else None,
            "realized_pnl": self.realized_pnl,
            "realized_pnl_pct": self.realized_pnl_pct,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "PositionEntry":
        """Reconstruit une PositionEntry depuis un dict JSON."""
        def _opt_float(v: object) -> float | None:
            return float(v) if v is not None else None  # type: ignore[arg-type]

        def _opt_dt(v: object) -> datetime | None:
            return datetime.fromisoformat(str(v)) if v is not None else None

        return cls(
            entry_id=str(data["entry_id"]),
            symbol=str(data["symbol"]),
            entry_price=float(data["entry_price"]),  # type: ignore[arg-type]
            entry_quantity=float(data["entry_quantity"]),  # type: ignore[arg-type]
            entry_timestamp=datetime.fromisoformat(str(data["entry_timestamp"])),
            entry_fee=float(data["entry_fee"]),  # type: ignore[arg-type]
            entry_cost_basis=float(data["entry_cost_basis"]),  # type: ignore[arg-type]
            strategy_group=str(data.get("strategy_group", "default")),
            strategy_timeframe=str(data.get("strategy_timeframe", config.TIMEFRAME)),
            stop_loss_price=_opt_float(data.get("stop_loss_price")),
            take_profit_price=_opt_float(data.get("take_profit_price")),
            exit_price=_opt_float(data.get("exit_price")),
            exit_quantity=_opt_float(data.get("exit_quantity")),
            exit_fee=_opt_float(data.get("exit_fee")),
            exit_timestamp=_opt_dt(data.get("exit_timestamp")),
            realized_pnl=_opt_float(data.get("realized_pnl")),
            realized_pnl_pct=_opt_float(data.get("realized_pnl_pct")),
            status=str(data.get("status", "OPEN")),
        )


@dataclass
class Trade:
    symbol: str
    side: str           # "BUY" | "SELL"
    price: float
    quantity: float
    fee: float = 0.0    # Frais pour ce trade
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        local_ts = self.timestamp.astimezone(_now_local().tzinfo)
        fee_str = f" (fee: ${self.fee:,.2f})" if self.fee > 0 else ""
        return (
            f"[{local_ts.strftime('%Y-%m-%d %H:%M:%S %Z')}] "
            f"{self.side:4s} {self.quantity:.6f} {self.symbol} @ ${self.price:,.2f}{fee_str}"
        )

    def to_dict(self) -> Dict[str, float | str]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "fee": self.fee,
            "timestamp": self.timestamp.isoformat(),
        }


class PaperTrader:
    """
    Moteur de paper trading.

    Maintient un portefeuille fictif : solde USDT + liste d'entries (positions individuelles).
    Chaque entry peut avoir son propre stop-loss et take-profit.
    Les ordres sont exécutés immédiatement au prix de marché transmis.
    """

    def __init__(
        self,
        initial_capital: float = config.INITIAL_CAPITAL_USDT,
        data_dir: str | Path | None = None,
        persist: bool = True,
    ) -> None:
        self.initial_capital: float = initial_capital
        self.usdt_balance: float = initial_capital
        self.entries: List[PositionEntry] = []      # Liste des positions (remplace dict positions)
        self.trades: List[Trade] = []
        self.persist = persist
        self.data_dir = Path(data_dir) if data_dir else Path(config.DATA_DIR)
        if self.persist:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        self.trades_file = self.data_dir / "trades.json"
        self.snapshots_file = self.data_dir / "portfolio_snapshots.json"
        self.state_file = self.data_dir / "state.json"
        # RLock (réentrant) : protège usdt_balance et entries contre les accès concurrents
        self._lock = threading.RLock()
        if self.persist:
            self._load_state()

    # ------------------------------------------------------------------
    # Helpers pour accéder aux positions
    # ------------------------------------------------------------------

    def get_open_entries(self, symbol: str) -> List[PositionEntry]:
        """Retourne toutes les positions ouvertes pour un symbole donné."""
        return [e for e in self.entries if e.symbol == symbol and e.status == "OPEN"]

    def get_total_quantity(self, symbol: str) -> float:
        """Retourne la quantité totale ouverte pour un symbole (somme des quantities)."""
        return sum(e.entry_quantity for e in self.get_open_entries(symbol))

    def get_closed_entries(self) -> List[PositionEntry]:
        """Retourne toutes les positions fermées (CLOSED, SL_HIT, TP_HIT)."""
        return [e for e in self.entries if e.status != "OPEN"]

    def get_positions_by_symbol(self) -> Dict[str, float]:
        """
        Retourne les positions ouvertes agrégées par symbole (pour compatibilité).
        
        Format: {symbol: total_quantity}
        """
        result = {}
        for entry in self.get_open_entries_all():
            result[entry.symbol] = result.get(entry.symbol, 0.0) + entry.entry_quantity
        return result

    # ------------------------------------------------------------------
    # Ordres
    # ------------------------------------------------------------------

    def buy(self, symbol: str, price: float) -> PositionEntry | None:
        """
        Achète pour TRADE_ALLOCATION du solde USDT disponible.

        Calcule la quantité en tenant compte du slippage et des frais.
        Crée une PositionEntry avec stop-loss et take-profit si activés.
        """
        with self._lock:
            symbol_cfg = config.get_symbol_config(symbol)
            spend = self.usdt_balance * float(symbol_cfg["trade_allocation"])
            if spend < 1.0:
                logger.warning("[%s] Solde USDT insuffisant pour acheter (%.2f USDT).", symbol, self.usdt_balance)
                return None

            # Applique slippage et frais au calcul de quantité
            # Slippage réduit la quantité achetée
            # Frais augmentent le coût effectif
            effective_price = price * (1 + config.TAKER_FEE_PCT / 100)
            quantity = (spend * (1 - config.SLIPPAGE_PCT / 100)) / effective_price

            # Frais payés à l'achat
            entry_fee = spend * (config.TAKER_FEE_PCT / 100)

            # Déduire spend + frais du solde
            total_cost = spend + entry_fee
            self.usdt_balance -= total_cost

            # Calculer SL/TP prices si activés
            stop_loss_price = None
            take_profit_price = None
            if config.ENABLE_STOPS:
                stop_loss_price = price * (1 + float(symbol_cfg["stop_loss_pct"]) / 100)
                take_profit_price = price * (1 + float(symbol_cfg["take_profit_pct"]) / 100)

            # Créer la position entry
            entry_cost_basis = quantity * price + entry_fee
            entry_id = f"{symbol}_{uuid.uuid4().hex[:8]}"
            now_ts = datetime.now(timezone.utc)

            entry = PositionEntry(
                entry_id=entry_id,
                symbol=symbol,
                entry_price=price,
                entry_quantity=quantity,
                entry_timestamp=now_ts,
                entry_fee=entry_fee,
                entry_cost_basis=entry_cost_basis,
                strategy_group=str(symbol_cfg["group"]),
                strategy_timeframe=str(symbol_cfg["timeframe"]),
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                status="OPEN"
            )

            self.entries.append(entry)

            # Créer un Trade pour l'historique
            trade = Trade(
                symbol=symbol,
                side="BUY",
                price=price,
                quantity=quantity,
                fee=entry_fee,
                timestamp=now_ts
            )
            self.trades.append(trade)
            self._persist_trade(trade)

            logger.info(
                "%s | Qty: %.6f | Fee: $%.2f | SL: %s | TP: %s | USDT restant: $%.2f",
                trade,
                quantity,
                entry_fee,
                f"${stop_loss_price:,.2f}" if stop_loss_price else "N/A",
                f"${take_profit_price:,.2f}" if take_profit_price else "N/A",
                self.usdt_balance
            )
            self.save_state()
            return entry

    def sell(self, symbol: str, price: float, entry_id: str | None = None) -> PositionEntry | None:
        """
        Vend une position ouverte pour ce symbole.

        Si entry_id est None : ferme la position la plus ancienne (FIFO).
        Sinon : ferme l'entry spécifiée.

        Applique les frais et calcule le PnL réalisé.
        """
        with self._lock:
            open_entries = self.get_open_entries(symbol)
            if not open_entries:
                logger.warning("[%s] Aucune position ouverte à vendre.", symbol)
                return None

            # Sélectionner l'entry à fermer
            if entry_id:
                entry = next((e for e in open_entries if e.entry_id == entry_id), None)
                if not entry:
                    logger.warning("[%s] Entry %s not found or not open.", symbol, entry_id)
                    return None
            else:
                # FIFO : la plus ancienne
                entry = min(open_entries, key=lambda e: e.entry_timestamp)

            # Calcul du proceeds
            proceeds = entry.entry_quantity * price
            exit_fee = proceeds * (config.TAKER_FEE_PCT / 100)
            proceeds_after_fee = proceeds - exit_fee

            # Calcul du PnL réalisé
            realized_pnl = proceeds_after_fee - entry.entry_cost_basis
            realized_pnl_pct = (realized_pnl / entry.entry_cost_basis) * 100 if entry.entry_cost_basis > 0 else 0.0

            # Mettre à jour l'entry
            entry.exit_price = price
            entry.exit_quantity = entry.entry_quantity
            entry.exit_fee = exit_fee
            entry.exit_timestamp = datetime.now(timezone.utc)
            entry.realized_pnl = realized_pnl
            entry.realized_pnl_pct = realized_pnl_pct
            entry.status = "CLOSED"

            # Ajouter au solde
            self.usdt_balance += proceeds_after_fee

            # Créer un Trade pour l'historique
            trade = Trade(
                symbol=symbol,
                side="SELL",
                price=price,
                quantity=entry.entry_quantity,
                fee=exit_fee,
                timestamp=entry.exit_timestamp
            )
            self.trades.append(trade)
            self._persist_trade(trade)

            logger.info(
                "%s | Entry: %s | PnL: %+.2f USDT (%+.2f%%) | Fee: $%.2f | USDT total: $%.2f",
                trade,
                entry.entry_id[:12],
                realized_pnl,
                realized_pnl_pct,
                exit_fee,
                self.usdt_balance
            )
            self.save_state()
            return entry

    def _auto_close_entries(self, symbol: str, price: float) -> List[PositionEntry]:
        """
        Vérifie et ferme automatiquement les entries qui ont atteint SL ou TP.

        Retourne la liste des entries fermées.
        """
        with self._lock:
            closed = []
            open_entries = self.get_open_entries(symbol)

            for entry in open_entries:
                close_reason = None

                # Vérifier SL
                if entry.stop_loss_price is not None and price <= entry.stop_loss_price:
                    close_reason = "SL_HIT"

                # Vérifier TP (prend priorité si les deux sont atteints)
                elif entry.take_profit_price is not None and price >= entry.take_profit_price:
                    close_reason = "TP_HIT"

                if close_reason:
                    # Fermer cette entry (RLock permet la réentrance depuis buy/sell)
                    self._close_entry(entry, price, close_reason)
                    closed.append(entry)

            if closed:
                self.save_state()
            return closed

    def _close_entry(self, entry: PositionEntry, price: float, status: str) -> None:
        """
        Ferme une entry de manière interne.
        
        status: "SL_HIT" ou "TP_HIT"
        """
        proceeds = entry.entry_quantity * price
        exit_fee = proceeds * (config.TAKER_FEE_PCT / 100)
        proceeds_after_fee = proceeds - exit_fee
        
        realized_pnl = proceeds_after_fee - entry.entry_cost_basis
        realized_pnl_pct = (realized_pnl / entry.entry_cost_basis) * 100 if entry.entry_cost_basis > 0 else 0.0
        
        entry.exit_price = price
        entry.exit_quantity = entry.entry_quantity
        entry.exit_fee = exit_fee
        entry.exit_timestamp = datetime.now(timezone.utc)
        entry.realized_pnl = realized_pnl
        entry.realized_pnl_pct = realized_pnl_pct
        entry.status = status
        
        self.usdt_balance += proceeds_after_fee
        
        logger.info(
            "[%s] %s auto-closed | Entry: %s | Price: $%.2f → $%.2f | PnL: %+.2f USDT (%+.2f%%)",
            status,
            entry.symbol,
            entry.entry_id[:12],
            entry.entry_price,
            price,
            realized_pnl,
            realized_pnl_pct
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def portfolio_value(self, prices: Dict[str, float]) -> float:
        """Valeur totale du portefeuille en USDT au prix de marché actuel."""
        value = self.usdt_balance
        for entry in self.get_open_entries_all():
            price = prices.get(entry.symbol, 0.0)
            value += entry.entry_quantity * price
        return value

    def get_open_entries_all(self) -> List[PositionEntry]:
        """Retourne TOUTES les positions ouvertes (de tous symboles)."""
        return [e for e in self.entries if e.status == "OPEN"]

    def pnl_metrics(self, prices: Dict[str, float]) -> Tuple[float, float, float]:
        """
        Retourne (total_value, pnl, pnl_pct).
        
        PnL = Valeur du portefeuille - Capital initial
        """
        total_value = self.portfolio_value(prices)
        pnl = total_value - self.initial_capital
        pnl_pct = (pnl / self.initial_capital) * 100 if self.initial_capital > 0 else 0.0
        return total_value, pnl, pnl_pct

    def print_summary(self, prices: Dict[str, float]) -> None:
        total, pnl, pnl_pct = self.pnl_metrics(prices)

        logger.info("=" * 60)
        logger.info("  Portefeuille - %s", _now_local().strftime("%Y-%m-%d %H:%M %Z"))
        logger.info("  USDT liquide  : $%.2f", self.usdt_balance)
        
        # Afficher positions ouvertes groupées par symbole
        symbols_with_entries = {}
        for entry in self.get_open_entries_all():
            if entry.symbol not in symbols_with_entries:
                symbols_with_entries[entry.symbol] = []
            symbols_with_entries[entry.symbol].append(entry)
        
        for symbol, entries in sorted(symbols_with_entries.items()):
            total_qty = sum(e.entry_quantity for e in entries)
            price = prices.get(symbol, 0.0)
            logger.info("  %-10s    : %.6f  (~$%.2f)  [%d entries]", symbol, total_qty, total_qty * price, len(entries))
        
        logger.info("  Valeur totale : $%.2f", total)
        logger.info("  PnL           : %+.2f USDT (%+.2f%%)", pnl, pnl_pct)
        logger.info("  Trades        : %d", len(self.trades))
        logger.info("=" * 60)

    def create_snapshot(self, prices: Dict[str, float]) -> Dict[str, object]:
        total, pnl, pnl_pct = self.pnl_metrics(prices)
        
        # Positions ouvertes uniquement
        positions = []
        for entry in self.get_open_entries_all():
            price = prices.get(entry.symbol, 0.0)
            unrealized_pnl = (entry.entry_quantity * price) - entry.entry_cost_basis
            positions.append(
                {
                    "entry_id": entry.entry_id,
                    "symbol": entry.symbol,
                    "quantity": entry.entry_quantity,
                    "entry_price": entry.entry_price,
                    "current_price": price,
                    "value": entry.entry_quantity * price,
                    "unrealized_pnl": unrealized_pnl,
                    "strategy_group": entry.strategy_group,
                    "strategy_timeframe": entry.strategy_timeframe,
                    "stop_loss_price": entry.stop_loss_price,
                    "take_profit_price": entry.take_profit_price,
                }
            )
        
        return {
            "timestamp": _now_local().isoformat(),
            "usdt_balance": self.usdt_balance,
            "portfolio_value": total,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "positions": positions,
            "trade_count": len(self.trades),
        }

    def record_snapshot(self, prices: Dict[str, float]) -> None:
        if not self.persist:
            return
        self._append_json_record(
            self.snapshots_file,
            self.create_snapshot(prices),
            max_items=config.MAX_STORED_SNAPSHOTS,
        )

    def get_recent_trades(self, limit: int = 10) -> List[Dict[str, float | str]]:
        """Retourne les derniers trades (les plus récents en premier)."""
        limit = max(1, limit)
        return [trade.to_dict() for trade in self.trades[-limit:]][::-1]

    def get_closed_entries_with_pnl(self, limit: int = 10) -> List[Dict[str, object]]:
        """Retourne les entries fermées récentes avec PnL détaillé."""
        closed = self.get_closed_entries()
        closed_sorted = sorted(closed, key=lambda e: e.exit_timestamp or datetime.min, reverse=True)
        return [e.to_dict() for e in closed_sorted[:limit]]

    def get_history(self, limit: int = 120) -> List[Dict[str, object]]:
        records = self._read_json_array(self.snapshots_file)
        return records[-max(1, limit):]

    # ------------------------------------------------------------------
    # Persistance de l'état entre redémarrages
    # ------------------------------------------------------------------

    def save_state(self) -> None:
        """Persiste le solde USDT et les positions ouvertes pour reprise après redémarrage."""
        if not self.persist:
            return
        state = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "usdt_balance": self.usdt_balance,
            "open_entries": [e.to_dict() for e in self.entries if e.status == "OPEN"],
        }
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Impossible d'écrire l'état : %s", exc)

    def _load_state(self) -> None:
        """Restaure le solde et les positions ouvertes depuis le fichier d'état."""
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("État sauvegardé illisible (%s) — démarrage à zéro.", exc)
            return

        raw_entries: list = data.get("open_entries", [])
        try:
            restored = [PositionEntry.from_dict(e) for e in raw_entries]
        except Exception as exc:
            logger.warning("Erreur lors de la restauration des positions (%s) — démarrage à zéro.", exc)
            return

        self.usdt_balance = float(data.get("usdt_balance", self.usdt_balance))
        self.entries = restored
        logger.info(
            "État restauré (sauvegardé le %s) : USDT=%.2f, %d position(s) ouverte(s).",
            data.get("saved_at", "?"),
            self.usdt_balance,
            len(restored),
        )
        for entry in restored:
            logger.info("  Restaurée : %s", entry)

    def _persist_trade(self, trade: Trade) -> None:
        if not self.persist:
            return
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
