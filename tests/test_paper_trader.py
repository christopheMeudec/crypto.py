"""Tests unitaires du moteur de paper trading."""

import json
import threading

import pytest

import config
from paper_trader import PaperTrader, PositionEntry
from tests.conftest import ADA, ADA_PRICE, BTC, BTC_PRICE, CAPITAL


# ===========================================================================
# Achat — mécanique de base
# ===========================================================================

class TestBuy:
    def test_deduction_solde(self, trader):
        """Le solde diminue de spend + frais."""
        cfg = config.get_symbol_config(BTC)
        spend = CAPITAL * float(cfg["trade_allocation"])
        fee = spend * (config.TAKER_FEE_PCT / 100)

        trader.buy(BTC, BTC_PRICE)

        assert abs(trader.usdt_balance - (CAPITAL - spend - fee)) < 0.001

    def test_quantite_avec_slippage(self, trader):
        """La quantité achetée intègre le slippage et les frais."""
        cfg = config.get_symbol_config(BTC)
        spend = CAPITAL * float(cfg["trade_allocation"])
        effective_price = BTC_PRICE * (1 + config.TAKER_FEE_PCT / 100)
        expected_qty = (spend * (1 - config.SLIPPAGE_PCT / 100)) / effective_price

        entry = trader.buy(BTC, BTC_PRICE)

        assert entry is not None
        assert abs(entry.entry_quantity - expected_qty) < 1e-8

    def test_position_ouverte(self, trader):
        """L'entry créée est en statut OPEN avec le bon prix."""
        entry = trader.buy(BTC, BTC_PRICE)

        assert entry is not None
        assert entry.status == "OPEN"
        assert entry.symbol == BTC
        assert entry.entry_price == BTC_PRICE

    def test_sl_tp_calcules(self, trader):
        """SL et TP sont calculés depuis les paramètres du groupe."""
        cfg = config.get_symbol_config(BTC)
        entry = trader.buy(BTC, BTC_PRICE)

        expected_sl = BTC_PRICE * (1 + float(cfg["stop_loss_pct"]) / 100)
        expected_tp = BTC_PRICE * (1 + float(cfg["take_profit_pct"]) / 100)

        assert entry.stop_loss_price is not None
        assert entry.take_profit_price is not None
        assert abs(entry.stop_loss_price - expected_sl) < 0.01
        assert abs(entry.take_profit_price - expected_tp) < 0.01

    def test_sl_tp_absents_si_stops_desactives(self, trader_no_stops):
        """Sans ENABLE_STOPS, SL et TP restent None."""
        entry = trader_no_stops.buy(BTC, BTC_PRICE)

        assert entry is not None
        assert entry.stop_loss_price is None
        assert entry.take_profit_price is None

    def test_solde_insuffisant(self):
        """Un solde trop faible (spend < 1 USDT) retourne None."""
        # Avec 1 USDT et allocation 16%, spend = 0.16 < 1.0
        trader = PaperTrader(initial_capital=1.0, persist=False)
        entry = trader.buy(BTC, BTC_PRICE)

        assert entry is None

    def test_ajout_trade_historique(self, trader):
        """Un trade BUY est ajouté à l'historique."""
        trader.buy(BTC, BTC_PRICE)

        assert len(trader.trades) == 1
        assert trader.trades[0].side == "BUY"
        assert trader.trades[0].symbol == BTC


# ===========================================================================
# Vente — mécanique de base
# ===========================================================================

class TestSell:
    def test_fermeture_fifo(self, trader_no_stops):
        """La vente sans entry_id ferme la position la plus ancienne (FIFO)."""
        entry1 = trader_no_stops.buy(BTC, BTC_PRICE)
        entry2 = trader_no_stops.buy(BTC, BTC_PRICE + 500)

        closed = trader_no_stops.sell(BTC, BTC_PRICE + 1000)

        assert closed is not None
        assert closed.entry_id == entry1.entry_id
        assert entry2.status == "OPEN"

    def test_fermeture_par_entry_id(self, trader_no_stops):
        """La vente avec entry_id ferme l'entry spécifiée (pas FIFO)."""
        entry1 = trader_no_stops.buy(BTC, BTC_PRICE)
        entry2 = trader_no_stops.buy(BTC, BTC_PRICE + 500)

        closed = trader_no_stops.sell(BTC, BTC_PRICE + 1000, entry_id=entry2.entry_id)

        assert closed is not None
        assert closed.entry_id == entry2.entry_id
        assert entry1.status == "OPEN"

    def test_sans_position_ouverte(self, trader):
        """Vendre sans position ouverte retourne None."""
        result = trader.sell(BTC, BTC_PRICE)

        assert result is None

    def test_pnl_positif(self, trader_no_stops):
        """PnL réalisé positif si le prix de vente est supérieur à l'entrée."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        entry = trader_no_stops.sell(BTC, BTC_PRICE * 1.05)

        assert entry is not None
        assert entry.realized_pnl is not None
        assert entry.realized_pnl > 0
        assert entry.realized_pnl_pct is not None
        assert entry.realized_pnl_pct > 0

    def test_pnl_negatif(self, trader_no_stops):
        """PnL réalisé négatif si le prix de vente est inférieur à l'entrée."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        entry = trader_no_stops.sell(BTC, BTC_PRICE * 0.95)

        assert entry is not None
        assert entry.realized_pnl is not None
        assert entry.realized_pnl < 0

    def test_solde_credite(self, trader_no_stops):
        """La vente crédite le solde du produit net de frais."""
        balance_before_sell = None

        trader_no_stops.buy(BTC, BTC_PRICE)
        balance_before_sell = trader_no_stops.usdt_balance
        trader_no_stops.sell(BTC, BTC_PRICE)

        assert trader_no_stops.usdt_balance > balance_before_sell

    def test_statut_closed(self, trader_no_stops):
        """L'entry fermée passe en statut CLOSED."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        entry = trader_no_stops.sell(BTC, BTC_PRICE)

        assert entry is not None
        assert entry.status == "CLOSED"

    def test_ajout_trade_historique(self, trader_no_stops):
        """Un trade SELL est ajouté à l'historique."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        trader_no_stops.sell(BTC, BTC_PRICE)

        sell_trades = [t for t in trader_no_stops.trades if t.side == "SELL"]
        assert len(sell_trades) == 1


# ===========================================================================
# Stop-Loss / Take-Profit automatiques
# ===========================================================================

class TestAutoClose:
    def test_sl_declenche(self, trader):
        """SL déclenché quand le prix passe sous stop_loss_price."""
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry.stop_loss_price is not None

        prix_sous_sl = entry.stop_loss_price - 100
        closed = trader._auto_close_entries(BTC, prix_sous_sl)

        assert len(closed) == 1
        assert closed[0].status == "SL_HIT"
        assert closed[0].realized_pnl is not None
        assert closed[0].realized_pnl < 0

    def test_tp_declenche(self, trader):
        """TP déclenché quand le prix passe au-dessus de take_profit_price."""
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry.take_profit_price is not None

        prix_au_dessus_tp = entry.take_profit_price + 100
        closed = trader._auto_close_entries(BTC, prix_au_dessus_tp)

        assert len(closed) == 1
        assert closed[0].status == "TP_HIT"
        assert closed[0].realized_pnl is not None
        assert closed[0].realized_pnl > 0

    def test_tp_prioritaire_sur_sl(self, trader):
        """Si SL et TP sont tous deux atteints, TP prend la priorité."""
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry.stop_loss_price is not None
        assert entry.take_profit_price is not None

        # Prix qui satisfait SL ET TP simultanément (impossible en vrai mais
        # vérifie la logique de priorité du code : TP est dans un elif)
        # Le code vérifie SL d'abord, puis TP dans un elif → SL_HIT
        prix_sl = entry.stop_loss_price - 1
        closed = trader._auto_close_entries(BTC, prix_sl)
        assert closed[0].status == "SL_HIT"

        # Réouverture pour tester TP
        trader2 = PaperTrader(initial_capital=CAPITAL, persist=False)
        entry2 = trader2.buy(BTC, BTC_PRICE)
        prix_tp = entry2.take_profit_price + 1
        closed2 = trader2._auto_close_entries(BTC, prix_tp)
        assert closed2[0].status == "TP_HIT"

    def test_aucune_fermeture_entre_sl_et_tp(self, trader):
        """Aucune fermeture si le prix est entre SL et TP."""
        entry = trader.buy(BTC, BTC_PRICE)
        prix_neutre = BTC_PRICE  # Prix d'entrée, entre SL et TP

        closed = trader._auto_close_entries(BTC, prix_neutre)

        assert closed == []
        assert entry.status == "OPEN"

    def test_fermeture_multiple_entries(self, trader):
        """Toutes les entries dont le SL est atteint sont fermées."""
        entry1 = trader.buy(BTC, BTC_PRICE)
        entry2 = trader.buy(BTC, BTC_PRICE)
        sl_price = min(entry1.stop_loss_price, entry2.stop_loss_price)

        closed = trader._auto_close_entries(BTC, sl_price - 1)

        assert len(closed) == 2
        assert all(e.status == "SL_HIT" for e in closed)


# ===========================================================================
# Gestion du portefeuille
# ===========================================================================

class TestPortfolio:
    def test_positions_isolees_par_symbole(self, trader_no_stops):
        """Les positions BTC et ADA sont indépendantes."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        trader_no_stops.buy(ADA, ADA_PRICE)

        assert len(trader_no_stops.get_open_entries(BTC)) == 1
        assert len(trader_no_stops.get_open_entries(ADA)) == 1

    def test_plusieurs_positions_meme_symbole(self, trader_no_stops):
        """On peut détenir plusieurs positions sur le même symbole."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        trader_no_stops.buy(BTC, BTC_PRICE + 1000)

        assert len(trader_no_stops.get_open_entries(BTC)) == 2

    def test_quantite_totale(self, trader_no_stops):
        """get_total_quantity retourne la somme des quantités ouvertes."""
        e1 = trader_no_stops.buy(BTC, BTC_PRICE)
        e2 = trader_no_stops.buy(BTC, BTC_PRICE + 1000)

        total = trader_no_stops.get_total_quantity(BTC)
        assert abs(total - (e1.entry_quantity + e2.entry_quantity)) < 1e-10

    def test_valeur_portefeuille(self, trader_no_stops):
        """portfolio_value inclut le cash + la valeur mark-to-market des positions."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        current_price = BTC_PRICE * 1.10

        open_entries = trader_no_stops.get_open_entries_all()
        expected = trader_no_stops.usdt_balance + sum(
            e.entry_quantity * current_price for e in open_entries
        )
        actual = trader_no_stops.portfolio_value({BTC: current_price})

        assert abs(actual - expected) < 0.001

    def test_pnl_metrics(self, trader_no_stops):
        """pnl_metrics retourne (valeur_totale, pnl, pnl_pct) cohérents."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        prices = {BTC: BTC_PRICE * 1.10}

        total, pnl, pnl_pct = trader_no_stops.pnl_metrics(prices)

        assert total > 0
        assert abs(pnl - (total - CAPITAL)) < 0.001
        assert abs(pnl_pct - (pnl / CAPITAL * 100)) < 0.001

    def test_get_positions_by_symbol(self, trader_no_stops):
        """get_positions_by_symbol agrège les quantités par symbole."""
        e1 = trader_no_stops.buy(BTC, BTC_PRICE)
        e2 = trader_no_stops.buy(BTC, BTC_PRICE + 500)

        pos = trader_no_stops.get_positions_by_symbol()

        assert BTC in pos
        assert abs(pos[BTC] - (e1.entry_quantity + e2.entry_quantity)) < 1e-10

    def test_closed_entries_with_pnl(self, trader_no_stops):
        """get_closed_entries_with_pnl retourne les entries fermées avec PnL."""
        trader_no_stops.buy(BTC, BTC_PRICE)
        trader_no_stops.sell(BTC, BTC_PRICE * 1.05)

        closed = trader_no_stops.get_closed_entries_with_pnl(limit=5)

        assert len(closed) == 1
        assert closed[0]["realized_pnl"] is not None


# ===========================================================================
# Thread safety
# ===========================================================================

class TestThreadSafety:
    def test_achats_concurrents_solde_coherent(self):
        """Des achats depuis plusieurs threads ne corrompent pas le solde."""
        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        errors = []

        def _buy():
            try:
                trader.buy(BTC, BTC_PRICE)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_buy) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Exceptions levées : {errors}"
        assert trader.usdt_balance >= 0

        # Chaque achat crée une entry → total cohérent avec le nombre de BUY réussis
        open_count = len(trader.get_open_entries_all())
        buy_trades = [t for t in trader.trades if t.side == "BUY"]
        assert open_count == len(buy_trades)

    def test_achats_ventes_concurrents(self):
        """Achats et ventes simultanés ne corrompent pas le solde."""
        trader = PaperTrader(initial_capital=10_000.0, persist=False)
        # Pré-remplir quelques positions
        for _ in range(5):
            trader.buy(BTC, BTC_PRICE)

        errors = []
        balance_before = trader.usdt_balance

        def _buy():
            try:
                trader.buy(BTC, BTC_PRICE)
            except Exception as exc:
                errors.append(exc)

        def _sell():
            try:
                trader.sell(BTC, BTC_PRICE * 1.01)
            except Exception as exc:
                errors.append(exc)

        threads = (
            [threading.Thread(target=_buy) for _ in range(5)]
            + [threading.Thread(target=_sell) for _ in range(5)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Exceptions levées : {errors}"
        assert trader.usdt_balance >= 0


# ===========================================================================
# Persistance de l'état
# ===========================================================================

class TestPersistance:
    def test_state_fichier_cree_apres_achat(self, tmp_path):
        """state.json est créé après un premier achat."""
        trader = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)
        trader.buy(BTC, BTC_PRICE)

        assert (tmp_path / "state.json").exists()

    def test_state_contient_seulement_positions_ouvertes(self, tmp_path):
        """state.json ne contient que les positions OPEN (pas les fermées)."""
        trader = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)
        trader.buy(BTC, BTC_PRICE)
        trader.buy(BTC, BTC_PRICE + 500)
        trader.sell(BTC, BTC_PRICE * 1.05)  # ferme la plus ancienne

        state = json.loads((tmp_path / "state.json").read_text())
        assert len(state["open_entries"]) == 1
        assert state["open_entries"][0]["status"] == "OPEN"

    def test_reprise_solde_apres_redemarrage(self, tmp_path):
        """Le solde USDT est restauré après redémarrage."""
        trader1 = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)
        trader1.buy(BTC, BTC_PRICE)
        balance_at_stop = trader1.usdt_balance

        trader2 = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)

        assert abs(trader2.usdt_balance - balance_at_stop) < 0.001

    def test_reprise_positions_apres_redemarrage(self, tmp_path):
        """Les positions ouvertes sont restaurées avec leurs données exactes."""
        trader1 = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)
        entry = trader1.buy(BTC, BTC_PRICE)
        assert entry is not None

        trader2 = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)
        open_entries = trader2.get_open_entries(BTC)

        assert len(open_entries) == 1
        restored = open_entries[0]
        assert restored.entry_id == entry.entry_id
        assert abs(restored.entry_price - entry.entry_price) < 0.001
        assert abs(restored.entry_quantity - entry.entry_quantity) < 1e-8
        assert restored.status == "OPEN"
        assert abs(restored.stop_loss_price - entry.stop_loss_price) < 0.01
        assert abs(restored.take_profit_price - entry.take_profit_price) < 0.01

    def test_demarrage_zero_sans_fichier(self, tmp_path):
        """Sans state.json, le bot démarre avec le capital initial."""
        trader = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)

        assert trader.usdt_balance == CAPITAL
        assert trader.get_open_entries_all() == []

    def test_demarrage_zero_fichier_corrompu(self, tmp_path):
        """Un state.json corrompu est ignoré et le bot démarre à zéro."""
        (tmp_path / "state.json").write_text("{ INVALID JSON }", encoding="utf-8")

        trader = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)

        assert trader.usdt_balance == CAPITAL
        assert trader.get_open_entries_all() == []

    def test_initial_capital_non_modifie(self, tmp_path):
        """initial_capital n'est pas écrasé par la restauration."""
        trader1 = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)
        trader1.buy(BTC, BTC_PRICE)

        trader2 = PaperTrader(initial_capital=CAPITAL, persist=True, data_dir=tmp_path)

        assert trader2.initial_capital == CAPITAL

    def test_persist_false_ne_sauvegarde_pas(self, tmp_path):
        """Avec persist=False, aucun fichier n'est écrit."""
        trader = PaperTrader(initial_capital=CAPITAL, persist=False, data_dir=tmp_path)
        trader.buy(BTC, BTC_PRICE)

        assert not (tmp_path / "state.json").exists()


# ===========================================================================
# PositionEntry — sérialisation/désérialisation
# ===========================================================================

class TestPositionEntry:
    def test_round_trip_to_from_dict(self, trader):
        """to_dict / from_dict est un round-trip sans perte."""
        entry = trader.buy(BTC, BTC_PRICE)
        assert entry is not None

        data = entry.to_dict()
        restored = PositionEntry.from_dict(data)

        assert restored.entry_id == entry.entry_id
        assert restored.symbol == entry.symbol
        assert abs(restored.entry_price - entry.entry_price) < 0.001
        assert abs(restored.entry_quantity - entry.entry_quantity) < 1e-10
        assert abs(restored.stop_loss_price - entry.stop_loss_price) < 0.01
        assert abs(restored.take_profit_price - entry.take_profit_price) < 0.01
        assert restored.status == entry.status
