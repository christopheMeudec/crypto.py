"""Tests pour ATR stops dynamiques, trailing stop et walk-forward."""

import pandas as pd
import pytest

import config
import strategy
from backtest import WalkForwardResult, run_walk_forward
from paper_trader import PaperTrader
from tests.conftest import BTC, BTC_PRICE, CAPITAL


# ===========================================================================
# Helpers
# ===========================================================================

def _make_ohlcv(n: int = 50, base: float = 50_000.0) -> pd.DataFrame:
    """DataFrame OHLCV minimal avec variation de prix réaliste pour ATR."""
    dates = pd.date_range("2024-01-01", periods=n, freq="30min", tz="UTC")
    import numpy as np
    rng = np.random.default_rng(42)
    closes = base + rng.normal(0, 100, n).cumsum()
    highs = closes + rng.uniform(50, 200, n)
    lows = closes - rng.uniform(50, 200, n)
    opens = closes + rng.normal(0, 50, n)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": 1.0},
        index=dates,
    )


# ===========================================================================
# Point 1 — compute_atr
# ===========================================================================

class TestComputeAtr:
    def test_retourne_float_positif(self):
        """compute_atr retourne un float > 0 sur données suffisantes."""
        df = _make_ohlcv(50)
        val = strategy.compute_atr(df, period=14)
        assert val is not None
        assert val > 0.0

    def test_retourne_none_si_pas_assez_de_bougies(self):
        """compute_atr retourne None si df < period + 1."""
        df = _make_ohlcv(10)
        assert strategy.compute_atr(df, period=14) is None

    def test_utilise_atr_period_par_defaut(self, monkeypatch):
        """Sans argument period, utilise config.ATR_PERIOD."""
        monkeypatch.setattr(config, "ATR_PERIOD", 5)
        df = _make_ohlcv(20)
        val = strategy.compute_atr(df)
        assert val is not None

    def test_atr_croissant_avec_volatilite(self):
        """ATR est plus élevé sur un marché plus volatile."""
        import numpy as np
        rng = np.random.default_rng(0)
        n = 50

        def _df(vol):
            closes = 50_000 + rng.normal(0, vol, n).cumsum()
            highs = closes + rng.uniform(vol * 0.5, vol, n)
            lows = closes - rng.uniform(vol * 0.5, vol, n)
            opens = closes.copy()
            dates = pd.date_range("2024-01-01", periods=n, freq="30min", tz="UTC")
            return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": 1.0}, index=dates)

        atr_low = strategy.compute_atr(_df(10), period=14)
        atr_high = strategy.compute_atr(_df(500), period=14)
        assert atr_high > atr_low


# ===========================================================================
# Point 1 — SL/TP basés sur l'ATR
# ===========================================================================

class TestAtrStops:
    def test_sl_tp_calcules_depuis_atr(self, monkeypatch):
        """Quand USE_ATR_STOPS et atr fourni, SL/TP = price ± mult * atr."""
        monkeypatch.setattr(config, "ENABLE_STOPS", True)
        monkeypatch.setattr(config, "USE_ATR_STOPS", True)
        monkeypatch.setattr(config, "ATR_MULTIPLIER_SL", 2.0)
        monkeypatch.setattr(config, "ATR_MULTIPLIER_TP", 3.0)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        atr = 500.0
        entry = trader.buy(BTC, BTC_PRICE, atr=atr)

        assert entry is not None
        assert entry.stop_loss_price == pytest.approx(BTC_PRICE - 2.0 * atr)
        assert entry.take_profit_price == pytest.approx(BTC_PRICE + 3.0 * atr)

    def test_sl_tp_pct_si_atr_none(self, monkeypatch):
        """Sans atr, on revient aux pourcentages fixes même si USE_ATR_STOPS."""
        monkeypatch.setattr(config, "ENABLE_STOPS", True)
        monkeypatch.setattr(config, "USE_ATR_STOPS", True)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE, atr=None)

        assert entry is not None
        # SL/TP non None → calcul % effectué
        assert entry.stop_loss_price is not None
        assert entry.take_profit_price is not None
        # Doit être < prix (SL) et > prix (TP)
        assert entry.stop_loss_price < BTC_PRICE
        assert entry.take_profit_price > BTC_PRICE

    def test_sl_tp_pct_si_use_atr_stops_false(self, monkeypatch):
        """USE_ATR_STOPS=False → calcul % même si atr fourni."""
        monkeypatch.setattr(config, "ENABLE_STOPS", True)
        monkeypatch.setattr(config, "USE_ATR_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE, atr=500.0)

        assert entry is not None
        # On NE doit PAS avoir SL = price - 2 * 500
        assert entry.stop_loss_price != pytest.approx(BTC_PRICE - 1_000.0)

    def test_atr_stops_independants_des_valeurs_cfg_pct(self, monkeypatch):
        """Les niveaux ATR ne dépendent pas des stop_loss_pct du groupe."""
        monkeypatch.setattr(config, "ENABLE_STOPS", True)
        monkeypatch.setattr(config, "USE_ATR_STOPS", True)
        monkeypatch.setattr(config, "ATR_MULTIPLIER_SL", 1.5)
        monkeypatch.setattr(config, "ATR_MULTIPLIER_TP", 2.5)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        atr = 300.0
        entry = trader.buy(BTC, BTC_PRICE, atr=atr)

        assert entry is not None
        assert entry.stop_loss_price == pytest.approx(BTC_PRICE - 1.5 * atr)
        assert entry.take_profit_price == pytest.approx(BTC_PRICE + 2.5 * atr)


# ===========================================================================
# Point 2 — Trailing stop
# ===========================================================================

class TestTrailingStop:
    def test_peak_price_initialisee_au_prix_entree(self, monkeypatch):
        """À l'achat, peak_price = prix d'entrée si ENABLE_TRAILING_STOP."""
        monkeypatch.setattr(config, "ENABLE_TRAILING_STOP", True)
        monkeypatch.setattr(config, "TRAILING_STOP_PCT", -2.0)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE)

        assert entry is not None
        assert entry.peak_price == pytest.approx(BTC_PRICE)
        assert entry.trailing_stop_pct == pytest.approx(-2.0)

    def test_peak_price_absente_si_trailing_stop_desactive(self, monkeypatch):
        """Sans trailing stop, peak_price reste None."""
        monkeypatch.setattr(config, "ENABLE_TRAILING_STOP", False)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE)

        assert entry is not None
        assert entry.peak_price is None
        assert entry.trailing_stop_pct is None

    def test_peak_price_mise_a_jour_quand_prix_monte(self, monkeypatch):
        """_auto_close_entries met à jour peak_price quand le prix monte."""
        monkeypatch.setattr(config, "ENABLE_TRAILING_STOP", True)
        monkeypatch.setattr(config, "TRAILING_STOP_PCT", -5.0)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry is not None

        higher_price = BTC_PRICE * 1.10  # +10%
        trader._auto_close_entries(BTC, higher_price)

        assert entry.peak_price == pytest.approx(higher_price)

    def test_trailing_stop_declenche_quand_recul_depasse_seuil(self, monkeypatch):
        """TS_HIT quand price <= peak * (1 + trailing_stop_pct/100)."""
        monkeypatch.setattr(config, "ENABLE_TRAILING_STOP", True)
        monkeypatch.setattr(config, "TRAILING_STOP_PCT", -5.0)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry is not None

        # Monte à +10%
        peak = BTC_PRICE * 1.10
        trader._auto_close_entries(BTC, peak)

        # Retombe de -6% depuis le pic (> seuil de -5%)
        trigger_price = peak * (1 - 0.06)
        closed = trader._auto_close_entries(BTC, trigger_price)

        assert len(closed) == 1
        assert closed[0].status == "TS_HIT"

    def test_trailing_stop_non_declenche_si_recul_sous_seuil(self, monkeypatch):
        """Pas de TS_HIT si le recul est inférieur au seuil."""
        monkeypatch.setattr(config, "ENABLE_TRAILING_STOP", True)
        monkeypatch.setattr(config, "TRAILING_STOP_PCT", -5.0)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry is not None

        # Monte à +10%, redescend de -3% (< seuil -5%)
        peak = BTC_PRICE * 1.10
        trader._auto_close_entries(BTC, peak)
        safe_price = peak * (1 - 0.03)
        closed = trader._auto_close_entries(BTC, safe_price)

        assert len(closed) == 0
        assert entry.status == "OPEN"

    def test_trailing_stop_pct_serialise_dans_to_dict(self, monkeypatch):
        """trailing_stop_pct et peak_price sont présents dans to_dict."""
        monkeypatch.setattr(config, "ENABLE_TRAILING_STOP", True)
        monkeypatch.setattr(config, "TRAILING_STOP_PCT", -3.0)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry is not None

        d = entry.to_dict()
        assert "trailing_stop_pct" in d
        assert "peak_price" in d
        assert d["trailing_stop_pct"] == pytest.approx(-3.0)
        assert d["peak_price"] == pytest.approx(BTC_PRICE)

    def test_trailing_stop_restaure_depuis_dict(self, monkeypatch):
        """from_dict restaure correctement trailing_stop_pct et peak_price."""
        monkeypatch.setattr(config, "ENABLE_TRAILING_STOP", True)
        monkeypatch.setattr(config, "TRAILING_STOP_PCT", -3.0)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry is not None

        from paper_trader import PositionEntry
        restored = PositionEntry.from_dict(entry.to_dict())
        assert restored.trailing_stop_pct == pytest.approx(-3.0)
        assert restored.peak_price == pytest.approx(BTC_PRICE)

    def test_ts_hit_enregistre_dans_statut_ferme(self, monkeypatch):
        """Une entrée fermée par trailing stop a le statut TS_HIT."""
        monkeypatch.setattr(config, "ENABLE_TRAILING_STOP", True)
        monkeypatch.setattr(config, "TRAILING_STOP_PCT", -2.0)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)

        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        trader.buy(BTC, BTC_PRICE)

        peak = BTC_PRICE * 1.05
        trader._auto_close_entries(BTC, peak)
        trigger = peak * (1 - 0.03)  # -3% > seuil -2%
        trader._auto_close_entries(BTC, trigger)

        closed = trader.get_closed_entries()
        assert len(closed) == 1
        assert closed[0].status == "TS_HIT"


# ===========================================================================
# Point 5 — Walk-forward (structure & résultats)
# ===========================================================================

class TestWalkForwardResult:
    def _make_result(self, n: int = 3) -> WalkForwardResult:
        """Construit un WalkForwardResult minimal avec des métriques simulées."""
        from backtest import BacktestMetrics, WalkForwardWindow
        import numpy as np

        windows = []
        for i in range(n):
            m = BacktestMetrics(
                symbol=BTC, timeframe="30m",
                start_date="2024-01-01", end_date="2024-03-31",
                initial_capital=100.0, final_value=105.0,
                realized_pnl=5.0, realized_pnl_pct=5.0,
                total_trades=10, buy_trades=5, sell_trades=5,
                winning_trades=3, losing_trades=2,
                win_rate_pct=60.0, profit_factor=1.5,
                avg_win=2.0, avg_loss=1.0, avg_trade_pnl=0.5,
                largest_win=5.0, largest_loss=-2.0,
                consecutive_wins=2, consecutive_losses=1,
                total_return_pct=5.0, max_drawdown_pct=3.0,
                max_drawdown_amount=3.0, sharpe_ratio=1.2,
                sortino_ratio=1.5, calmar_ratio=1.7,
                daily_returns_std=0.5,
            )
            windows.append(WalkForwardWindow(
                window_idx=i + 1,
                start_date="2024-01-01",
                end_date="2024-03-31",
                n_candles=500,
                metrics=m,
            ))

        result = WalkForwardResult(symbol=BTC, timeframe="30m", n_windows=n)
        result.windows = windows
        return result

    def test_avg_return_pct(self):
        r = self._make_result(3)
        assert r.avg_return_pct == pytest.approx(5.0)

    def test_avg_win_rate(self):
        r = self._make_result(3)
        assert r.avg_win_rate == pytest.approx(60.0)

    def test_avg_sharpe(self):
        r = self._make_result(3)
        assert r.avg_sharpe == pytest.approx(1.2)

    def test_avg_max_drawdown(self):
        r = self._make_result(3)
        assert r.avg_max_drawdown == pytest.approx(3.0)

    def test_total_trades(self):
        r = self._make_result(4)
        assert r.total_trades == 40  # 4 fenêtres × 10 trades

    def test_empty_result(self):
        r = WalkForwardResult(symbol=BTC, timeframe="30m", n_windows=0)
        assert r.avg_return_pct == 0.0
        assert r.total_trades == 0

    def test_n_windows_coherent(self):
        r = self._make_result(5)
        assert len(r.windows) == 5


class TestWalkForwardDataSplit:
    """Vérifie le découpage des données sans appel réseau."""

    def _build_df(self, n_candles: int) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=n_candles, freq="30min", tz="UTC")
        import numpy as np
        rng = np.random.default_rng(1)
        closes = 50_000 + rng.normal(0, 100, n_candles).cumsum()
        highs = closes + 200
        lows = closes - 200
        opens = closes.copy()
        return pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": 1.0},
            index=dates,
        )

    def test_nombre_de_fenetres_respecte(self, monkeypatch):
        """run_walk_forward produit au plus n_windows fenêtres."""
        from backtest import BacktestRunner, WalkForwardResult, fetch_ohlcv_long

        df = self._build_df(600)
        from strategy import compute_indicators
        df_ind = compute_indicators(df, symbol=BTC)
        df_ind.dropna(inplace=True)

        monkeypatch.setattr("backtest.fetch_ohlcv_long", lambda *a, **kw: df)

        result = run_walk_forward(
            symbol=BTC,
            timeframe="30m",
            days_back=30,
            n_windows=3,
            warmup_candles=20,
            initial_capital=1_000.0,
        )
        assert len(result.windows) <= 3

    def test_chaque_fenetre_a_des_dates_distinctes(self, monkeypatch):
        """Les fenêtres walk-forward couvrent des périodes non identiques."""
        df = self._build_df(600)
        monkeypatch.setattr("backtest.fetch_ohlcv_long", lambda *a, **kw: df)

        result = run_walk_forward(
            symbol=BTC,
            timeframe="30m",
            days_back=30,
            n_windows=3,
            warmup_candles=20,
            initial_capital=1_000.0,
        )
        if len(result.windows) >= 2:
            dates = [w.start_date for w in result.windows]
            assert len(set(dates)) == len(dates), "Certaines fenêtres ont la même date de début"
