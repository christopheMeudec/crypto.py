#!/usr/bin/env python3
"""
Test script pour valider l'implémentation Stop-Loss/Take-Profit et Frais/Slippage.
"""

import logging
from paper_trader import PaperTrader
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def test_basic_buy_sell_with_fees():
    """Test 1: Achat/Vente simple avec frais déduits"""
    logger.info("=" * 70)
    logger.info("TEST 1: Buy/Sell avec frais")
    logger.info("=" * 70)
    
    trader = PaperTrader(initial_capital=100.0)
    logger.info("Capital initial: $%.2f", trader.usdt_balance)
    
    # BUY @ 50000
    logger.info("Achat @ $50000")
    entry1 = trader.buy("BTC/USDT", 50000.0)
    logger.info("Entry: %s", entry1)
    logger.info("USDT balance après buy: $%.2f", trader.usdt_balance)
    
    # Vérifier que les frais sont déduits
    # Spend = 100 * 0.25 = 25 USDT
    # Fee = 25 * 0.001 = 0.025 USDT
    # Effective price = 50000 * (1 + 0.001) = 50050
    # Quantity = (25 * (1 - 0.0005)) / 50050 ≈ 0.000499...
    expected_balance = 100.0 - 25.0 - 0.025  # spend + fee
    assert abs(trader.usdt_balance - expected_balance) < 0.01, f"Expected ~{expected_balance}, got {trader.usdt_balance}"
    logger.info("✓ Frais correctement déduits du solde")
    
    # SELL @ 51000 (profit)
    logger.info("\nVente @ $51000")
    entry1_closed = trader.sell("BTC/USDT", 51000.0)
    logger.info("Closed Entry: %s", entry1_closed)
    logger.info("Realized PnL: %+.2f USDT (%+.2f%%)", entry1_closed.realized_pnl, entry1_closed.realized_pnl_pct)
    logger.info("USDT balance après sell: $%.2f", trader.usdt_balance)
    
    # PnL devrait être positif mais réduit par les frais
    assert entry1_closed.realized_pnl is not None and entry1_closed.realized_pnl > 0, "Expected positive PnL"
    logger.info("✓ PnL réalisé calculé correctement")
    
    logger.info("")


def test_stop_loss_hit():
    """Test 2: Stop-Loss hit automatiquement"""
    logger.info("=" * 70)
    logger.info("TEST 2: Stop-Loss Auto-Close")
    logger.info("=" * 70)
    
    # Activer les stops
    config.ENABLE_STOPS = True
    config.STOP_LOSS_PCT = -2.0  # -2%
    config.TAKE_PROFIT_PCT = 5.0  # +5%
    
    trader = PaperTrader(initial_capital=100.0)
    
    # BUY @ 50000
    logger.info("Achat @ $50000")
    entry1 = trader.buy("BTC/USDT", 50000.0)
    logger.info("Entry: %s", entry1)
    logger.info("SL Price: $%.2f", entry1.stop_loss_price or 0)
    logger.info("TP Price: $%.2f", entry1.take_profit_price or 0)
    
    # Vérifier que SL/TP ont été calculés
    assert entry1.stop_loss_price is not None, "SL price should be set"
    assert entry1.take_profit_price is not None, "TP price should be set"
    expected_sl = 50000.0 * (1 - 0.02)  # 49000
    expected_tp = 50000.0 * (1 + 0.05)  # 52500
    assert abs(entry1.stop_loss_price - expected_sl) < 1, f"Expected SL ~{expected_sl}, got {entry1.stop_loss_price}"
    assert abs(entry1.take_profit_price - expected_tp) < 1, f"Expected TP ~{expected_tp}, got {entry1.take_profit_price}"
    logger.info("✓ SL/TP prices calculés correctement")
    
    # Auto-close SL @ 48900 (< SL price)
    logger.info("\nAuto-close SL @ $48900 (< $%.2f)", entry1.stop_loss_price)
    closed = trader._auto_close_entries("BTC/USDT", 48900.0)
    assert len(closed) == 1, "Should close 1 entry"
    assert closed[0].status == "SL_HIT", "Status should be SL_HIT"
    logger.info("Closed Entry: %s", closed[0])
    logger.info("✓ Stop-Loss auto-closed correctement")
    
    logger.info("")


def test_take_profit_hit():
    """Test 3: Take-Profit hit automatiquement"""
    logger.info("=" * 70)
    logger.info("TEST 3: Take-Profit Auto-Close")
    logger.info("=" * 70)
    
    config.ENABLE_STOPS = True
    config.STOP_LOSS_PCT = -2.0
    config.TAKE_PROFIT_PCT = 5.0
    
    trader = PaperTrader(initial_capital=100.0)
    
    # BUY @ 50000
    logger.info("Achat @ $50000")
    entry1 = trader.buy("BTC/USDT", 50000.0)
    
    # Auto-close TP @ 52700 (> TP price)
    logger.info("\nAuto-close TP @ $52700 (> $%.2f)", entry1.take_profit_price)
    closed = trader._auto_close_entries("BTC/USDT", 52700.0)
    assert len(closed) == 1, "Should close 1 entry"
    assert closed[0].status == "TP_HIT", "Status should be TP_HIT"
    logger.info("Closed Entry: %s", closed[0])
    logger.info("PnL: %+.2f USDT (%+.2f%%)", closed[0].realized_pnl, closed[0].realized_pnl_pct)
    logger.info("✓ Take-Profit auto-closed correctement")
    
    logger.info("")


def test_multiple_entries():
    """Test 4: Multiple entries et fermeture FIFO"""
    logger.info("=" * 70)
    logger.info("TEST 4: Multiple Entries & FIFO Close")
    logger.info("=" * 70)
    
    config.ENABLE_STOPS = True
    config.STOP_LOSS_PCT = -2.0
    config.TAKE_PROFIT_PCT = 5.0
    
    trader = PaperTrader(initial_capital=100.0)
    
    # BUY 1 @ 50000
    logger.info("Entry 1: Achat @ $50000")
    entry1 = trader.buy("BTC/USDT", 50000.0)
    logger.info("Entry 1: %s", entry1)
    initial_balance = trader.usdt_balance
    
    # BUY 2 @ 50500
    logger.info("\nEntry 2: Achat @ $50500")
    entry2 = trader.buy("BTC/USDT", 50500.0)
    logger.info("Entry 2: %s", entry2)
    
    # Vérifier qu'on a 2 entries ouvertes
    open_entries = trader.get_open_entries("BTC/USDT")
    assert len(open_entries) == 2, f"Should have 2 open entries, got {len(open_entries)}"
    logger.info("✓ 2 entries ouvertes")
    
    # SELL une fois (devrait fermer la plus ancienne = entry1)
    logger.info("\nVente (FIFO)")
    closed = trader.sell("BTC/USDT", 51000.0)
    assert closed.entry_id == entry1.entry_id, "Should close the oldest entry (FIFO)"
    logger.info("Closed: %s", closed)
    logger.info("✓ Fermeture FIFO correcte")
    
    # Vérifier qu'il reste 1 entry ouverte
    open_entries = trader.get_open_entries("BTC/USDT")
    assert len(open_entries) == 1, f"Should have 1 open entry left, got {len(open_entries)}"
    assert open_entries[0].entry_id == entry2.entry_id, "Should be entry2"
    logger.info("✓ 1 entry reste ouverte")
    
    logger.info("")


def test_pnl_metrics():
    """Test 5: PnL metrics (realized + unrealized)"""
    logger.info("=" * 70)
    logger.info("TEST 5: PnL Metrics (Realized + Unrealized)")
    logger.info("=" * 70)
    
    config.ENABLE_STOPS = False  # Disable for this test
    
    trader = PaperTrader(initial_capital=100.0)
    
    # BUY 1 @ 50000
    logger.info("Entry 1: Achat @ $50000")
    entry1 = trader.buy("BTC/USDT", 50000.0)
    
    # BUY 2 @ 51000
    logger.info("Entry 2: Achat @ $51000")
    entry2 = trader.buy("BTC/USDT", 51000.0)
    
    # SELL 1 @ 51500 (realized gain)
    logger.info("\nVente 1 @ $51500")
    trader.sell("BTC/USDT", 51500.0)
    
    # Vérifier PnL metrics avec unrealized
    # Entry2 toujours ouverte à prix 52000 (profit)
    prices = {"BTC/USDT": 52000.0}
    total_value, pnl, pnl_pct = trader.pnl_metrics(prices)
    logger.info("Portfolio value: $%.2f", total_value)
    logger.info("PnL: %+.2f USDT (%+.2f%%)", pnl, pnl_pct)
    logger.info("✓ PnL metrics calculés")
    
    logger.info("")


if __name__ == "__main__":
    logger.info("\n" + "=" * 70)
    logger.info("TESTS: Stop-Loss, Take-Profit, Frais & Slippage")
    logger.info("=" * 70 + "\n")
    
    try:
        test_basic_buy_sell_with_fees()
        test_stop_loss_hit()
        test_take_profit_hit()
        test_multiple_entries()
        test_pnl_metrics()
        
        logger.info("=" * 70)
        logger.info("✓ TOUS LES TESTS RÉUSSIS")
        logger.info("=" * 70)
    except Exception as exc:
        logger.error("✗ TEST ÉCHOUÉ: %s", exc, exc_info=True)
        exit(1)
