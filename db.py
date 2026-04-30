from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)


class BotDatabase:
    """SQLite persistence layer for the trading bot.

    Single connection in WAL mode, protected by a reentrant lock so it is
    safe to call from multiple threads (main loop + API server thread).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        logger.info("Base de données SQLite ouverte : %s", self._path)

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS candles (
                    symbol    TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    ts        INTEGER NOT NULL,
                    open      REAL NOT NULL,
                    high      REAL NOT NULL,
                    low       REAL NOT NULL,
                    close     REAL NOT NULL,
                    volume    REAL NOT NULL,
                    PRIMARY KEY (symbol, timeframe, ts)
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol   TEXT NOT NULL,
                    side     TEXT NOT NULL,
                    price    REAL NOT NULL,
                    quantity REAL NOT NULL,
                    fee      REAL NOT NULL,
                    pnl      REAL,
                    ts       TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts              TEXT NOT NULL,
                    usdt_balance    REAL NOT NULL,
                    portfolio_value REAL NOT NULL,
                    pnl             REAL NOT NULL,
                    pnl_pct         REAL NOT NULL,
                    positions_json  TEXT NOT NULL,
                    trade_count     INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS state (
                    id                INTEGER PRIMARY KEY CHECK (id = 1),
                    saved_at          TEXT NOT NULL,
                    usdt_balance      REAL NOT NULL,
                    open_entries_json TEXT NOT NULL
                );
            """)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── Candles ──────────────────────────────────────────────────────────────

    def upsert_candles(self, symbol: str, timeframe: str, df: "pd.DataFrame") -> None:
        """Upsert all candles from *df* and purge the oldest beyond MAX_CANDLES_PER_SYMBOL."""
        rows = [
            (
                symbol,
                timeframe,
                int(ts.timestamp() * 1000),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
            )
            for ts, row in df.iterrows()
        ]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO candles"
                " (symbol, timeframe, ts, open, high, low, close, volume)"
                " VALUES (?,?,?,?,?,?,?,?)",
                rows,
            )
            # Keep only the newest MAX_CANDLES_PER_SYMBOL rows per (symbol, timeframe).
            # The subquery finds the ts of the oldest row that still fits inside the limit;
            # everything older than that is deleted.
            self._conn.execute(
                """
                DELETE FROM candles
                WHERE symbol = ? AND timeframe = ?
                  AND ts < (
                      SELECT ts FROM candles
                      WHERE symbol = ? AND timeframe = ?
                      ORDER BY ts DESC
                      LIMIT 1 OFFSET ?
                  )
                """,
                (symbol, timeframe, symbol, timeframe, config.MAX_CANDLES_PER_SYMBOL - 1),
            )
            self._conn.commit()

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[dict]:
        """Return the last *limit* candles in chronological order.

        Each dict has keys: time (Unix seconds), open, high, low, close, volume.
        lightweight-charts requires time in seconds.
        """
        limit = max(1, min(limit, 2000))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT ts, open, high, low, close, volume
                FROM candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (symbol, timeframe, limit),
            ).fetchall()
        return [
            {
                "time": row["ts"] // 1000,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for row in reversed(rows)
        ]

    def get_available_symbols(self) -> list[dict]:
        """Return distinct (symbol, timeframe) pairs that have stored candles."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT symbol, timeframe FROM candles ORDER BY symbol"
            ).fetchall()
        return [{"symbol": r["symbol"], "timeframe": r["timeframe"]} for r in rows]

    # ── Trades ───────────────────────────────────────────────────────────────

    def append_trade(self, trade_dict: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO trades (symbol, side, price, quantity, fee, pnl, ts)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    trade_dict["symbol"],
                    trade_dict["side"],
                    trade_dict["price"],
                    trade_dict["quantity"],
                    trade_dict["fee"],
                    trade_dict.get("pnl"),
                    trade_dict["timestamp"],
                ),
            )
            # Purge oldest rows beyond MAX_STORED_TRADES
            self._conn.execute(
                """
                DELETE FROM trades WHERE id <= (
                    SELECT id FROM trades ORDER BY id DESC LIMIT 1 OFFSET ?
                )
                """,
                (config.MAX_STORED_TRADES - 1,),
            )
            self._conn.commit()

    def get_recent_trades(self, limit: int = 200) -> list[dict]:
        limit = max(1, min(limit, 1000))
        with self._lock:
            rows = self._conn.execute(
                "SELECT symbol, side, price, quantity, fee, pnl, ts"
                " FROM trades ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "symbol": r["symbol"],
                "side": r["side"],
                "price": r["price"],
                "quantity": r["quantity"],
                "fee": r["fee"],
                "pnl": r["pnl"],
                "timestamp": r["ts"],
            }
            for r in rows
        ]

    # ── Snapshots ─────────────────────────────────────────────────────────────

    def append_snapshot(self, snapshot: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots"
                " (ts, usdt_balance, portfolio_value, pnl, pnl_pct, positions_json, trade_count)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    snapshot["timestamp"],
                    snapshot["usdt_balance"],
                    snapshot["portfolio_value"],
                    snapshot["pnl"],
                    snapshot["pnl_pct"],
                    json.dumps(snapshot.get("positions", [])),
                    snapshot.get("trade_count", 0),
                ),
            )
            # Purge oldest rows beyond MAX_STORED_SNAPSHOTS
            self._conn.execute(
                """
                DELETE FROM snapshots WHERE id <= (
                    SELECT id FROM snapshots ORDER BY id DESC LIMIT 1 OFFSET ?
                )
                """,
                (config.MAX_STORED_SNAPSHOTS - 1,),
            )
            self._conn.commit()

    def get_recent_snapshots(self, limit: int = 1000) -> list[dict]:
        limit = max(1, min(limit, 5000))
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, usdt_balance, portfolio_value, pnl, pnl_pct, positions_json, trade_count"
                " FROM snapshots ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for r in reversed(rows):
            try:
                positions = json.loads(r["positions_json"])
            except (json.JSONDecodeError, TypeError):
                positions = []
            result.append({
                "timestamp": r["ts"],
                "usdt_balance": r["usdt_balance"],
                "portfolio_value": r["portfolio_value"],
                "pnl": r["pnl"],
                "pnl_pct": r["pnl_pct"],
                "positions": positions,
                "trade_count": r["trade_count"],
            })
        return result

    # ── Bot state ─────────────────────────────────────────────────────────────

    def save_state(self, saved_at: str, usdt_balance: float, open_entries: list[dict]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO state (id, saved_at, usdt_balance, open_entries_json)"
                " VALUES (1, ?, ?, ?)",
                (saved_at, usdt_balance, json.dumps(open_entries)),
            )
            self._conn.commit()

    def load_state(self) -> dict | None:
        """Return saved state dict or None if no state has been persisted yet."""
        with self._lock:
            row = self._conn.execute(
                "SELECT saved_at, usdt_balance, open_entries_json FROM state WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        try:
            open_entries = json.loads(row["open_entries_json"])
        except (json.JSONDecodeError, TypeError):
            open_entries = []
        return {
            "saved_at": row["saved_at"],
            "usdt_balance": row["usdt_balance"],
            "open_entries": open_entries,
        }
