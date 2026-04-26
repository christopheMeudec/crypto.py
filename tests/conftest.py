"""Fixtures partagées pour la suite de tests."""

import pandas as pd
import pytest

import config
import strategy
from paper_trader import PaperTrader

BTC = "BTC/USDT"
ADA = "ADA/USDT"
BTC_PRICE = 50_000.0
ADA_PRICE = 1.0
CAPITAL = 1_000.0


@pytest.fixture
def trader():
    """PaperTrader sans persistance, stops activés (valeurs par défaut des groupes)."""
    return PaperTrader(initial_capital=CAPITAL, persist=False)


@pytest.fixture
def trader_no_stops(monkeypatch):
    """PaperTrader sans persistance, stops désactivés."""
    monkeypatch.setattr(config, "ENABLE_STOPS", False)
    return PaperTrader(initial_capital=CAPITAL, persist=False)


def make_indicator_df(rows: list[dict]) -> pd.DataFrame:
    """Construit un DataFrame avec des colonnes indicateurs contrôlées."""
    dates = pd.date_range("2024-01-01", periods=len(rows), freq="30min", tz="UTC")
    return pd.DataFrame(rows, index=dates)


@pytest.fixture
def patch_indicators(monkeypatch):
    """
    Fixture usine : retourne une fonction qui remplace compute_indicators
    par un DataFrame à colonnes indicateurs connues.
    """
    def _patch(rows: list[dict]) -> None:
        df = make_indicator_df(rows)
        monkeypatch.setattr(strategy, "compute_indicators", lambda _df, symbol=None: df)
    return _patch


# ---------------------------------------------------------------------------
# Scénarios d'indicateurs réutilisables
# ---------------------------------------------------------------------------

# BUY direct : RSI < 38, MACD croise à la hausse sur la dernière bougie
BUY_DIRECT = [
    {"close": 100.0, "rsi": 35.0, "macd": -5.0, "macd_signal": -3.0, "macd_hist": -2.0},  # prev2
    {"close": 101.0, "rsi": 34.0, "macd": -4.0, "macd_signal": -3.0, "macd_hist": -1.0},  # prev  (MACD < signal)
    {"close": 103.0, "rsi": 36.0, "macd": -2.0, "macd_signal": -3.0, "macd_hist":  1.0},  # last  (MACD > signal ✓)
]

# BUY différé : crossover survenu il y a 1 bougie, momentum confirmé
BUY_DELAYED = [
    {"close": 100.0, "rsi": 35.0, "macd": -5.0, "macd_signal": -3.0, "macd_hist": -2.0},  # prev2 (MACD < signal)
    {"close": 102.0, "rsi": 34.0, "macd": -2.0, "macd_signal": -3.0, "macd_hist":  1.0},  # prev  (crossover ici)
    {"close": 104.0, "rsi": 33.0, "macd": -1.0, "macd_signal": -3.0, "macd_hist":  2.0},  # last  (momentum ↑ ✓)
]

# SELL direct : RSI > 62, MACD croise à la baisse sur la dernière bougie
SELL_DIRECT = [
    {"close": 100.0, "rsi": 65.0, "macd":  5.0, "macd_signal":  3.0, "macd_hist":  2.0},
    {"close":  99.0, "rsi": 64.0, "macd":  4.0, "macd_signal":  3.0, "macd_hist":  1.0},  # prev  (MACD > signal)
    {"close":  97.0, "rsi": 63.0, "macd":  2.0, "macd_signal":  3.0, "macd_hist": -1.0},  # last  (MACD < signal ✓)
]

# SELL différé
SELL_DELAYED = [
    {"close": 100.0, "rsi": 65.0, "macd":  5.0, "macd_signal":  3.0, "macd_hist":  2.0},  # prev2 (MACD > signal)
    {"close":  98.0, "rsi": 64.0, "macd":  2.0, "macd_signal":  3.0, "macd_hist": -1.0},  # prev  (crossover ici)
    {"close":  96.0, "rsi": 63.0, "macd":  1.0, "macd_signal":  3.0, "macd_hist": -2.0},  # last  (momentum ↓ ✓)
]

# HOLD neutre
HOLD_NEUTRAL = [
    {"close": 100.0, "rsi": 50.0, "macd":  0.0, "macd_signal":  0.5, "macd_hist": -0.5},
    {"close": 100.0, "rsi": 50.0, "macd":  0.1, "macd_signal":  0.5, "macd_hist": -0.4},
    {"close": 100.0, "rsi": 50.0, "macd":  0.2, "macd_signal":  0.5, "macd_hist": -0.3},
]
