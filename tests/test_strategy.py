"""Tests unitaires de la stratégie RSI + MACD."""

import pandas as pd
import pytest

import config
import strategy
from strategy import compute_indicators, get_signal, get_signal_with_reason
from tests.conftest import (
    BUY_DELAYED,
    BUY_DIRECT,
    HOLD_NEUTRAL,
    SELL_DELAYED,
    SELL_DIRECT,
    make_indicator_df,
)

# DataFrame vide passé à get_signal_with_reason quand compute_indicators est mocké
_DUMMY_DF = pd.DataFrame()


# ===========================================================================
# Signaux BUY
# ===========================================================================

class TestSignalBuy:
    def test_buy_crossover_direct(self, patch_indicators):
        """BUY : RSI survendu + MACD croise à la hausse sur la dernière bougie."""
        patch_indicators(BUY_DIRECT)
        signal, reason = get_signal_with_reason(_DUMMY_DF)

        assert signal == "BUY"
        assert "BUY" in reason

    def test_buy_crossover_differe(self, patch_indicators):
        """BUY : crossover survenu il y a 1 bougie avec momentum confirmé."""
        patch_indicators(BUY_DELAYED)
        signal, reason = get_signal_with_reason(_DUMMY_DF)

        assert signal == "BUY"

    def test_buy_inclut_valeur_rsi(self, patch_indicators):
        """Le message de raison BUY mentionne la valeur RSI."""
        patch_indicators(BUY_DIRECT)
        _, reason = get_signal_with_reason(_DUMMY_DF)

        assert "RSI" in reason or "rsi" in reason.lower()


# ===========================================================================
# Signaux SELL
# ===========================================================================

class TestSignalSell:
    def test_sell_crossover_direct(self, patch_indicators):
        """SELL : RSI suracheté + MACD croise à la baisse sur la dernière bougie."""
        patch_indicators(SELL_DIRECT)
        signal, reason = get_signal_with_reason(_DUMMY_DF)

        assert signal == "SELL"
        assert "SELL" in reason

    def test_sell_crossover_differe(self, patch_indicators):
        """SELL : crossover survenu il y a 1 bougie avec momentum confirmé."""
        patch_indicators(SELL_DELAYED)
        signal, reason = get_signal_with_reason(_DUMMY_DF)

        assert signal == "SELL"


# ===========================================================================
# Signaux HOLD
# ===========================================================================

class TestSignalHold:
    def test_hold_neutre(self, patch_indicators):
        """HOLD quand RSI dans la zone neutre et pas de crossover."""
        patch_indicators(HOLD_NEUTRAL)
        signal, _ = get_signal_with_reason(_DUMMY_DF)

        assert signal == "HOLD"

    def test_hold_rsi_survendu_sans_crossover(self, patch_indicators):
        """HOLD si RSI survendu mais MACD ne croise pas à la hausse."""
        rows = [
            {"close": 100.0, "rsi": 35.0, "macd": -4.0, "macd_signal": -3.0, "macd_hist": -1.0},
            {"close": 101.0, "rsi": 34.0, "macd": -3.5, "macd_signal": -3.0, "macd_hist": -0.5},  # still below
            {"close": 102.0, "rsi": 33.0, "macd": -3.2, "macd_signal": -3.0, "macd_hist": -0.2},  # still below ✓
        ]
        patch_indicators(rows)
        signal, _ = get_signal_with_reason(_DUMMY_DF)

        assert signal == "HOLD"

    def test_hold_macd_crossover_sans_rsi(self, patch_indicators):
        """HOLD si MACD croise à la hausse mais RSI pas en zone de survente."""
        rows = [
            {"close": 100.0, "rsi": 55.0, "macd": -1.0, "macd_signal": 0.0, "macd_hist": -1.0},
            {"close": 101.0, "rsi": 56.0, "macd": -0.5, "macd_signal": 0.0, "macd_hist": -0.5},  # below signal
            {"close": 103.0, "rsi": 57.0, "macd":  0.5, "macd_signal": 0.0, "macd_hist":  0.5},  # above signal, RSI not oversold
        ]
        patch_indicators(rows)
        signal, _ = get_signal_with_reason(_DUMMY_DF)

        assert signal == "HOLD"

    def test_hold_sell_rsi_survendu_sans_crossover(self, patch_indicators):
        """HOLD si RSI suracheté mais MACD ne croise pas à la baisse."""
        rows = [
            {"close": 100.0, "rsi": 64.0, "macd": 3.5, "macd_signal": 3.0, "macd_hist": 0.5},
            {"close":  99.0, "rsi": 63.0, "macd": 3.2, "macd_signal": 3.0, "macd_hist": 0.2},  # still above signal
            {"close":  98.0, "rsi": 62.5, "macd": 3.1, "macd_signal": 3.0, "macd_hist": 0.1},  # still above signal ✓
        ]
        patch_indicators(rows)
        signal, _ = get_signal_with_reason(_DUMMY_DF)

        assert signal == "HOLD"

    def test_hold_crossover_differe_sans_momentum(self, patch_indicators):
        """HOLD si crossover différé mais momentum faiblissant (hist en baisse)."""
        rows = [
            {"close": 100.0, "rsi": 35.0, "macd": -5.0, "macd_signal": -3.0, "macd_hist": -2.0},  # prev2 below
            {"close": 102.0, "rsi": 34.0, "macd": -2.0, "macd_signal": -3.0, "macd_hist":  1.0},  # prev crossed
            {"close": 103.0, "rsi": 33.0, "macd": -2.5, "macd_signal": -3.0, "macd_hist":  0.5},  # hist 0.5 < 1.0 ↓
        ]
        patch_indicators(rows)
        signal, _ = get_signal_with_reason(_DUMMY_DF)

        assert signal == "HOLD"


# ===========================================================================
# Cas limites
# ===========================================================================

class TestCasLimites:
    def test_données_insuffisantes_une_bougie(self, patch_indicators):
        """HOLD si une seule bougie disponible après dropna."""
        rows = [
            {"close": 100.0, "rsi": 35.0, "macd": -2.0, "macd_signal": -3.0, "macd_hist": 1.0},
        ]
        patch_indicators(rows)
        signal, reason = get_signal_with_reason(_DUMMY_DF)

        assert signal == "HOLD"
        assert "bougies" in reason

    def test_exactement_deux_bougies_sans_prev2(self, patch_indicators):
        """Avec 2 bougies, le crossover différé n'est pas vérifié (pas de prev2)."""
        rows = [
            {"close": 100.0, "rsi": 35.0, "macd": -4.0, "macd_signal": -3.0, "macd_hist": -1.0},  # prev (below)
            {"close": 102.0, "rsi": 34.0, "macd": -2.0, "macd_signal": -3.0, "macd_hist":  1.0},  # last (above ✓)
        ]
        patch_indicators(rows)
        # Le crossover direct prev→last est présent ET RSI < oversold → BUY quand même
        signal, _ = get_signal_with_reason(_DUMMY_DF)

        assert signal == "BUY"

    def test_get_signal_wrapper_coherent(self, patch_indicators):
        """get_signal retourne le même signal que get_signal_with_reason."""
        patch_indicators(BUY_DIRECT)

        signal_direct = get_signal(_DUMMY_DF)
        signal_full, _ = get_signal_with_reason(_DUMMY_DF)

        assert signal_direct == signal_full


# ===========================================================================
# compute_indicators — appel réel (pas mocké)
# ===========================================================================

class TestComputeIndicators:
    def _make_ohlcv(self, n: int = 100, trend: float = 0.1) -> pd.DataFrame:
        """Construit un DataFrame OHLCV synthétique avec n bougies."""
        dates = pd.date_range("2024-01-01", periods=n, freq="30min", tz="UTC")
        prices = [100.0 + i * trend for i in range(n)]
        return pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.5 for p in prices],
                "low": [p - 0.5 for p in prices],
                "close": prices,
                "volume": [1000.0] * n,
            },
            index=dates,
        )

    def test_colonnes_indicateurs_presentes(self):
        """compute_indicators ajoute rsi, macd, macd_signal, macd_hist."""
        df = self._make_ohlcv()
        result = compute_indicators(df)

        for col in ("rsi", "macd", "macd_signal", "macd_hist"):
            assert col in result.columns, f"Colonne manquante : {col}"

    def test_colonnes_originales_preservees(self):
        """compute_indicators ne supprime pas les colonnes OHLCV."""
        df = self._make_ohlcv()
        result = compute_indicators(df)

        for col in ("open", "high", "low", "close", "volume"):
            assert col in result.columns

    def test_rsi_dans_plage_valide(self):
        """RSI est dans [0, 100] sur les lignes non-NaN."""
        df = self._make_ohlcv(n=100)
        result = compute_indicators(df).dropna()

        assert (result["rsi"] >= 0).all()
        assert (result["rsi"] <= 100).all()

    def test_config_symbole_appliquee(self):
        """compute_indicators utilise les paramètres RSI/MACD du symbole fourni."""
        df = self._make_ohlcv(n=100)
        result_default = compute_indicators(df, symbol=None)
        result_btc = compute_indicators(df, symbol="BTC/USDT")

        # Les deux doivent avoir les colonnes indicateurs
        assert "rsi" in result_default.columns
        assert "rsi" in result_btc.columns

    def test_ne_modifie_pas_df_original(self):
        """compute_indicators travaille sur une copie, ne modifie pas l'entrée."""
        df = self._make_ohlcv()
        cols_before = list(df.columns)

        compute_indicators(df)

        assert list(df.columns) == cols_before
