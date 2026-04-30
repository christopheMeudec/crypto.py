"""Tests unitaires pour BotDatabase (SQLite in-memory)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from db import BotDatabase


@pytest.fixture
def db(tmp_path):
    """BotDatabase sur fichier temporaire."""
    d = BotDatabase(tmp_path / "test_bot.db")
    yield d
    d.close()


def _make_df(n: int = 5) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="30min", tz="UTC")
    return pd.DataFrame(
        {
            "open":   [100.0 + i for i in range(n)],
            "high":   [102.0 + i for i in range(n)],
            "low":    [99.0  + i for i in range(n)],
            "close":  [101.0 + i for i in range(n)],
            "volume": [10.0  + i for i in range(n)],
        },
        index=dates,
    )


class TestCandles:
    def test_upsert_and_get(self, db):
        df = _make_df(5)
        db.upsert_candles("BTC/USDT", "30m", df)
        candles = db.get_candles("BTC/USDT", "30m", limit=10)
        assert len(candles) == 5
        assert candles[0]["open"] == 100.0
        assert candles[-1]["open"] == 104.0
        assert all("time" in c for c in candles)

    def test_upsert_idempotent(self, db):
        df = _make_df(5)
        db.upsert_candles("BTC/USDT", "30m", df)
        db.upsert_candles("BTC/USDT", "30m", df)
        candles = db.get_candles("BTC/USDT", "30m", limit=100)
        assert len(candles) == 5

    def test_limit_respected(self, db):
        df = _make_df(10)
        db.upsert_candles("ETH/USDT", "30m", df)
        candles = db.get_candles("ETH/USDT", "30m", limit=3)
        assert len(candles) == 3
        # Should return the 3 most recent candles
        assert candles[-1]["open"] == 109.0

    def test_returns_chronological_order(self, db):
        df = _make_df(5)
        db.upsert_candles("BTC/USDT", "30m", df)
        candles = db.get_candles("BTC/USDT", "30m")
        times = [c["time"] for c in candles]
        assert times == sorted(times)

    def test_time_in_seconds(self, db):
        df = _make_df(1)
        db.upsert_candles("BTC/USDT", "30m", df)
        candles = db.get_candles("BTC/USDT", "30m")
        # Unix seconds for 2024-01-01 00:00:00 UTC is 1704067200
        assert candles[0]["time"] == pytest.approx(1704067200, abs=60)

    def test_no_candles_returns_empty(self, db):
        assert db.get_candles("UNKNOWN/USDT", "30m") == []

    def test_available_symbols(self, db):
        db.upsert_candles("BTC/USDT", "30m", _make_df(3))
        db.upsert_candles("ETH/USDT", "1h", _make_df(3))
        syms = db.get_available_symbols()
        symbols = {s["symbol"] for s in syms}
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols


class TestTrades:
    def _trade(self, symbol="BTC/USDT", side="BUY", pnl=None):
        return {
            "symbol": symbol,
            "side": side,
            "price": 50000.0,
            "quantity": 0.001,
            "fee": 0.05,
            "pnl": pnl,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def test_append_and_get(self, db):
        db.append_trade(self._trade("BTC/USDT", "BUY"))
        db.append_trade(self._trade("ETH/USDT", "SELL", pnl=12.5))
        trades = db.get_recent_trades(limit=10)
        assert len(trades) == 2
        # Most recent first
        assert trades[0]["symbol"] == "ETH/USDT"
        assert trades[0]["pnl"] == pytest.approx(12.5)

    def test_pnl_none_for_buy(self, db):
        db.append_trade(self._trade("BTC/USDT", "BUY", pnl=None))
        trades = db.get_recent_trades()
        assert trades[0]["pnl"] is None

    def test_limit(self, db):
        for _ in range(10):
            db.append_trade(self._trade())
        trades = db.get_recent_trades(limit=5)
        assert len(trades) == 5


class TestSnapshots:
    def _snapshot(self, portfolio_value=100.0):
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "usdt_balance": 90.0,
            "portfolio_value": portfolio_value,
            "pnl": portfolio_value - 100.0,
            "pnl_pct": (portfolio_value - 100.0),
            "positions": [{"symbol": "BTC/USDT", "value": 10.0}],
            "trade_count": 2,
        }

    def test_append_and_get(self, db):
        db.append_snapshot(self._snapshot(105.0))
        db.append_snapshot(self._snapshot(110.0))
        snaps = db.get_recent_snapshots(limit=10)
        assert len(snaps) == 2
        assert snaps[-1]["portfolio_value"] == pytest.approx(110.0)

    def test_positions_json_roundtrip(self, db):
        db.append_snapshot(self._snapshot())
        snaps = db.get_recent_snapshots()
        assert isinstance(snaps[0]["positions"], list)
        assert snaps[0]["positions"][0]["symbol"] == "BTC/USDT"

    def test_chronological_order(self, db):
        for i in range(3):
            db.append_snapshot(self._snapshot(100.0 + i))
        snaps = db.get_recent_snapshots()
        values = [s["portfolio_value"] for s in snaps]
        assert values == sorted(values)


class TestState:
    def test_save_and_load(self, db):
        entries = [{"entry_id": "BTC_abc123", "symbol": "BTC/USDT", "status": "OPEN"}]
        db.save_state("2024-01-01T00:00:00+00:00", 95.0, entries)
        state = db.load_state()
        assert state is not None
        assert state["usdt_balance"] == pytest.approx(95.0)
        assert len(state["open_entries"]) == 1
        assert state["open_entries"][0]["symbol"] == "BTC/USDT"

    def test_load_empty_returns_none(self, db):
        assert db.load_state() is None

    def test_overwrite(self, db):
        db.save_state("2024-01-01T00:00:00+00:00", 100.0, [])
        db.save_state("2024-01-02T00:00:00+00:00", 80.0, [{"entry_id": "x"}])
        state = db.load_state()
        assert state["usdt_balance"] == pytest.approx(80.0)
        assert len(state["open_entries"]) == 1
