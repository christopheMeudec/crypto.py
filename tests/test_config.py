"""Tests unitaires de la configuration et des helpers config."""

import pytest

import config


# ===========================================================================
# get_symbol_config — fusion des paramètres de groupe
# ===========================================================================

class TestGetSymbolConfig:
    def test_majors_btc(self):
        """BTC/USDT hérite des paramètres du groupe 'majors'."""
        cfg = config.get_symbol_config("BTC/USDT")

        assert cfg["group"] == "majors"
        assert float(cfg["trade_allocation"]) == pytest.approx(0.16)
        assert float(cfg["stop_loss_pct"]) == pytest.approx(-3.8)
        assert float(cfg["take_profit_pct"]) == pytest.approx(7.5)
        assert str(cfg["timeframe"]) == "30m"

    def test_majors_eth(self):
        """ETH/USDT est dans le groupe 'majors'."""
        cfg = config.get_symbol_config("ETH/USDT")
        assert cfg["group"] == "majors"

    def test_alts_ada(self):
        """ADA/USDT hérite des paramètres du groupe 'alts'."""
        cfg = config.get_symbol_config("ADA/USDT")

        assert cfg["group"] == "alts"
        assert float(cfg["trade_allocation"]) == pytest.approx(0.08)
        assert float(cfg["stop_loss_pct"]) == pytest.approx(-2.3)
        assert float(cfg["take_profit_pct"]) == pytest.approx(4.8)

    def test_alts_xrp(self):
        """XRP/USDT est dans le groupe 'alts'."""
        cfg = config.get_symbol_config("XRP/USDT")
        assert cfg["group"] == "alts"

    def test_symbole_inconnu_utilise_defauts(self):
        """Un symbole hors groupe reçoit la config par défaut."""
        cfg = config.get_symbol_config("UNKNOWN/USDT")

        assert cfg["group"] == "default"
        assert float(cfg["trade_allocation"]) == pytest.approx(config.TRADE_ALLOCATION)
        assert float(cfg["stop_loss_pct"]) == pytest.approx(config.STOP_LOSS_PCT)
        assert float(cfg["take_profit_pct"]) == pytest.approx(config.TAKE_PROFIT_PCT)

    def test_config_contient_rsi_et_macd(self):
        """La config d'un symbole contient tous les paramètres RSI + MACD."""
        cfg = config.get_symbol_config("BTC/USDT")

        for key in ("rsi_period", "rsi_oversold", "rsi_overbought",
                    "macd_fast", "macd_slow", "macd_signal"):
            assert key in cfg, f"Clé manquante : {key}"

    def test_config_est_une_copie(self):
        """Modifier le dict retourné ne modifie pas la config globale."""
        cfg1 = config.get_symbol_config("BTC/USDT")
        cfg1["trade_allocation"] = 999.0

        cfg2 = config.get_symbol_config("BTC/USDT")
        assert float(cfg2["trade_allocation"]) != 999.0


# ===========================================================================
# get_symbol_group
# ===========================================================================

class TestGetSymbolGroup:
    def test_groupe_majors(self):
        assert config.get_symbol_group("BTC/USDT") == "majors"
        assert config.get_symbol_group("ETH/USDT") == "majors"
        assert config.get_symbol_group("BNB/USDT") == "majors"
        assert config.get_symbol_group("SOL/USDT") == "majors"

    def test_groupe_alts(self):
        assert config.get_symbol_group("ADA/USDT") == "alts"
        assert config.get_symbol_group("XRP/USDT") == "alts"
        assert config.get_symbol_group("DOGE/USDT") == "alts"

    def test_symbole_inconnu_retourne_none(self):
        assert config.get_symbol_group("UNKNOWN/USDT") is None
        assert config.get_symbol_group("") is None


# ===========================================================================
# timeframe_to_seconds
# ===========================================================================

class TestTimeframeToSeconds:
    @pytest.mark.parametrize("tf,expected", [
        ("1m",    60),
        ("5m",   300),
        ("15m",  900),
        ("30m", 1800),
        ("1h",  3600),
        ("2h",  7200),
        ("4h", 14400),
        ("1d", 86400),
    ])
    def test_conversion(self, tf, expected):
        assert config.timeframe_to_seconds(tf) == expected

    def test_timeframe_inconnu_leve_keyerror(self):
        with pytest.raises(KeyError):
            config.timeframe_to_seconds("999x")


# ===========================================================================
# Intégrité de la configuration globale
# ===========================================================================

class TestIntegriteConfig:
    def test_chaque_groupe_a_des_symboles(self):
        """Chaque groupe de stratégie définit au moins un symbole."""
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            symbols = group_cfg.get("symbols", [])
            assert len(symbols) > 0, f"Groupe '{group_name}' sans symboles"

    def test_aucun_symbole_en_double(self):
        """Aucun symbole n'appartient à plusieurs groupes."""
        seen: set[str] = set()
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            for sym in group_cfg.get("symbols", []):
                assert sym not in seen, (
                    f"Symbole '{sym}' en double (trouvé dans '{group_name}')"
                )
                seen.add(sym)

    def test_symbols_derive_des_groupes(self):
        """config.SYMBOLS correspond à la liste aplatie des groupes."""
        expected = []
        for group_cfg in config.STRATEGY_GROUPS.values():
            expected.extend(group_cfg.get("symbols", []))

        assert config.SYMBOLS == expected

    def test_tous_les_timeframes_supportes(self):
        """Les timeframes des groupes sont tous dans SUPPORTED_TIMEFRAMES_SECONDS."""
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            tf = str(group_cfg.get("timeframe", ""))
            assert tf in config.SUPPORTED_TIMEFRAMES_SECONDS, (
                f"Timeframe '{tf}' du groupe '{group_name}' non supporté"
            )

    def test_allocations_valides(self):
        """Toutes les allocations sont dans ]0, 1]."""
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            alloc = float(group_cfg.get("trade_allocation", 0))
            assert 0 < alloc <= 1.0, (
                f"Allocation invalide {alloc} dans le groupe '{group_name}'"
            )

    def test_stop_loss_negatif(self):
        """Les stop-loss sont négatifs (baisse de prix)."""
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            sl = float(group_cfg.get("stop_loss_pct", 0))
            assert sl < 0, f"stop_loss_pct devrait être négatif dans '{group_name}'"

    def test_take_profit_positif(self):
        """Les take-profit sont positifs (hausse de prix)."""
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            tp = float(group_cfg.get("take_profit_pct", 0))
            assert tp > 0, f"take_profit_pct devrait être positif dans '{group_name}'"

    def test_ratio_risque_rendement_positif(self):
        """Le ratio TP/|SL| est supérieur à 1 pour chaque groupe."""
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            sl = abs(float(group_cfg.get("stop_loss_pct", 1)))
            tp = float(group_cfg.get("take_profit_pct", 0))
            assert tp / sl > 1.0, (
                f"Ratio TP/SL insuffisant dans '{group_name}' : {tp / sl:.2f}"
            )

    def test_rsi_oversold_inferieur_a_overbought(self):
        """RSI oversold < RSI overbought pour chaque groupe."""
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            oversold = float(group_cfg.get("rsi_oversold", 50))
            overbought = float(group_cfg.get("rsi_overbought", 50))
            assert oversold < overbought, (
                f"rsi_oversold >= rsi_overbought dans '{group_name}'"
            )

    def test_macd_fast_inferieur_a_slow(self):
        """MACD fast period < slow period pour chaque groupe."""
        for group_name, group_cfg in config.STRATEGY_GROUPS.items():
            fast = int(group_cfg.get("macd_fast", 12))
            slow = int(group_cfg.get("macd_slow", 26))
            assert fast < slow, (
                f"macd_fast >= macd_slow dans '{group_name}'"
            )
