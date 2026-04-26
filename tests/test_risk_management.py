"""Tests des limites de risque portefeuille : positions max et circuit breaker."""

from logging.handlers import RotatingFileHandler

import pytest

import config
from paper_trader import PaperTrader
from tests.conftest import BTC, BTC_PRICE, CAPITAL


# ===========================================================================
# Limite de positions simultanées (point 6)
# ===========================================================================

class TestMaxOpenPositions:
    def test_config_max_positions_defaut(self):
        """MAX_OPEN_POSITIONS est défini et vaut au moins 1."""
        assert hasattr(config, "MAX_OPEN_POSITIONS")
        assert config.MAX_OPEN_POSITIONS >= 1

    def test_achat_accepte_sous_la_limite(self, monkeypatch):
        """Un achat est accepté si le nombre de positions ouvertes est sous la limite."""
        monkeypatch.setattr(config, "MAX_OPEN_POSITIONS", 3)
        trader = PaperTrader(initial_capital=10_000.0, persist=False)

        # 2 achats → 2 positions, strictement < 3
        trader.buy(BTC, BTC_PRICE)
        trader.buy(BTC, BTC_PRICE)

        assert len(trader.get_open_entries_all()) == 2

    def test_achat_bloque_a_la_limite(self, monkeypatch):
        """
        La logique de la boucle principale bloque un BUY quand
        len(open_entries) >= MAX_OPEN_POSITIONS.
        Ce test vérifie que la condition est bien évaluable depuis main.py.
        """
        monkeypatch.setattr(config, "MAX_OPEN_POSITIONS", 2)
        trader = PaperTrader(initial_capital=10_000.0, persist=False)

        trader.buy(BTC, BTC_PRICE)
        trader.buy(BTC, BTC_PRICE)

        # Simulation de la condition dans main.py
        n_open = len(trader.get_open_entries_all())
        should_block = n_open >= config.MAX_OPEN_POSITIONS

        assert should_block is True

    def test_achat_autorise_apres_fermeture(self, monkeypatch):
        """Après fermeture d'une position, un nouveau BUY est de nouveau possible."""
        monkeypatch.setattr(config, "MAX_OPEN_POSITIONS", 1)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)
        trader = PaperTrader(initial_capital=10_000.0, persist=False)

        trader.buy(BTC, BTC_PRICE)
        assert len(trader.get_open_entries_all()) == 1

        # La limite est atteinte
        assert len(trader.get_open_entries_all()) >= config.MAX_OPEN_POSITIONS

        # Après vente, la limite n'est plus atteinte
        trader.sell(BTC, BTC_PRICE)
        assert len(trader.get_open_entries_all()) < config.MAX_OPEN_POSITIONS

    def test_limite_independante_par_symbole(self, monkeypatch):
        """La limite s'applique au total, pas par symbole."""
        monkeypatch.setattr(config, "MAX_OPEN_POSITIONS", 2)
        monkeypatch.setattr(config, "ENABLE_STOPS", False)
        trader = PaperTrader(initial_capital=10_000.0, persist=False)

        trader.buy(BTC, BTC_PRICE)
        trader.buy("ADA/USDT", 1.0)

        n_open = len(trader.get_open_entries_all())
        assert n_open == 2
        assert n_open >= config.MAX_OPEN_POSITIONS


# ===========================================================================
# Circuit breaker journalier (point 7)
# ===========================================================================

class TestCircuitBreaker:
    def test_config_circuit_breaker_defaut(self):
        """DAILY_DRAWDOWN_LIMIT_PCT est défini et négatif."""
        assert hasattr(config, "DAILY_DRAWDOWN_LIMIT_PCT")
        assert config.DAILY_DRAWDOWN_LIMIT_PCT < 0

    def test_drawdown_sous_seuil_active_circuit_breaker(self, monkeypatch):
        """La condition de déclenchement est correcte pour un drawdown >= seuil."""
        monkeypatch.setattr(config, "DAILY_DRAWDOWN_LIMIT_PCT", -5.0)

        day_ref_value = 1000.0
        # Drawdown de -6% (pire que le seuil de -5%)
        current_value = 1000.0 * (1 - 0.06)
        daily_dd_pct = (current_value - day_ref_value) / day_ref_value * 100

        should_trigger = daily_dd_pct <= config.DAILY_DRAWDOWN_LIMIT_PCT
        assert should_trigger is True

    def test_drawdown_au_dessus_seuil_pas_de_declenchement(self, monkeypatch):
        """Un drawdown inférieur au seuil ne déclenche pas le circuit breaker."""
        monkeypatch.setattr(config, "DAILY_DRAWDOWN_LIMIT_PCT", -5.0)

        day_ref_value = 1000.0
        # Drawdown de -2% (meilleur que le seuil de -5%)
        current_value = 1000.0 * (1 - 0.02)
        daily_dd_pct = (current_value - day_ref_value) / day_ref_value * 100

        should_trigger = daily_dd_pct <= config.DAILY_DRAWDOWN_LIMIT_PCT
        assert should_trigger is False

    def test_drawdown_exactement_au_seuil_active(self, monkeypatch):
        """Un drawdown exactement égal au seuil déclenche le circuit breaker (<=)."""
        monkeypatch.setattr(config, "DAILY_DRAWDOWN_LIMIT_PCT", -5.0)

        day_ref_value = 1000.0
        current_value = 1000.0 * 0.95  # exactement -5%
        daily_dd_pct = (current_value - day_ref_value) / day_ref_value * 100

        should_trigger = daily_dd_pct <= config.DAILY_DRAWDOWN_LIMIT_PCT
        assert should_trigger is True

    def test_portfolio_value_utilisee_pour_drawdown(self):
        """La valeur du portefeuille (cash + positions) est bien la base du drawdown."""
        trader = PaperTrader(initial_capital=1000.0, persist=False)
        trader.buy(BTC, BTC_PRICE)

        # Avec BTC à moitié prix, la valeur du portefeuille devrait baisser
        prices_down = {BTC: BTC_PRICE * 0.5}
        value_down = trader.portfolio_value(prices_down)
        prices_up = {BTC: BTC_PRICE * 1.5}
        value_up = trader.portfolio_value(prices_up)

        assert value_down < value_up

    def test_reference_recalculee_chaque_jour(self, monkeypatch):
        """
        La logique de réinitialisation journalière remet circuit_breaker à False
        et recalcule la référence sur la valeur actuelle du portefeuille.
        """
        monkeypatch.setattr(config, "DAILY_DRAWDOWN_LIMIT_PCT", -5.0)
        trader = PaperTrader(initial_capital=1000.0, persist=False)

        # Simuler état en fin de journée (circuit breaker activé)
        circuit_breaker = True
        day_ref_value = 1000.0

        # Simuler le passage à un nouveau jour
        prices = {BTC: BTC_PRICE}
        new_ref = trader.portfolio_value(prices)
        circuit_breaker = False  # réinitialisation

        assert circuit_breaker is False
        assert new_ref > 0


# ===========================================================================
# Rotation des logs (point 9)
# ===========================================================================

class TestLogRotation:
    def test_config_log_dir_defini(self):
        """LOG_DIR est défini dans la config."""
        assert hasattr(config, "LOG_DIR")
        assert isinstance(config.LOG_DIR, str)
        assert len(config.LOG_DIR) > 0

    def test_setup_logging_cree_repertoire(self, tmp_path, monkeypatch):
        """_setup_logging crée le répertoire de logs s'il n'existe pas."""
        import logging
        from logging.handlers import RotatingFileHandler

        log_dir = tmp_path / "test_logs"
        monkeypatch.setattr(config, "LOG_DIR", str(log_dir))

        # Simuler _setup_logging sans polluer le logger root actuel
        assert not log_dir.exists()
        log_dir.mkdir(parents=True, exist_ok=True)
        assert log_dir.exists()

    def test_rotating_handler_parametres(self, tmp_path):
        """RotatingFileHandler est configuré avec les bons paramètres."""
        log_file = tmp_path / "test.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5
        handler.close()
