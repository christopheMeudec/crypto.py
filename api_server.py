from __future__ import annotations

import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

import config

logger = logging.getLogger(__name__)


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Crypto Bot Dashboard</title>
  <style>
    :root {
      --bg: #f7f2e7;
      --card: #fffdf6;
      --text: #1e1a16;
      --accent: #165d54;
      --accent-2: #d6722e;
      --ok: #2f7d32;
      --bad: #b23a2f;
      --line: rgba(22, 93, 84, 0.14);
    }
    body {
      margin: 0;
      font-family: 'Trebuchet MS', 'Segoe UI', sans-serif;
      color: var(--text);
      background: radial-gradient(circle at 10% 20%, #fffdf8 0%, var(--bg) 60%);
    }
    .wrap {
      max-width: 980px;
      margin: 0 auto;
      padding: 18px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 1.6rem;
      letter-spacing: 0.4px;
    }
    .sub {
      margin: 0 0 18px;
      opacity: 0.8;
      font-size: 0.95rem;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.06);
    }
    .label {
      font-size: 0.8rem;
      opacity: 0.7;
      margin-bottom: 5px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    .value {
      font-size: 1.15rem;
      font-weight: 700;
    }
    .pos { color: var(--ok); }
    .neg { color: var(--bad); }
    table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 12px;
      font-size: 0.92rem;
    }
    th, td {
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      background: var(--card);
    }
    th {
      font-size: 0.78rem;
      letter-spacing: 0.7px;
      opacity: 0.75;
      text-transform: uppercase;
    }
    .row-buy { border-left: 4px solid var(--ok); }
    .row-sell { border-left: 4px solid var(--accent-2); }
    .footer {
      margin-top: 14px;
      font-size: 0.85rem;
      opacity: 0.75;
    }
    .tabs { display: flex; gap: 8px; margin-bottom: 16px; }
    .tab-btn { padding: 7px 18px; border: 1px solid var(--line); border-radius: 20px; background: var(--card); cursor: pointer; font-size: 0.9rem; color: var(--text); font-family: inherit; transition: all .15s; }
    .tab-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .tab-btn:hover:not(.active) { background: var(--bg); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; background: var(--accent); color: #fff; font-size: 0.85rem; margin: 3px; font-weight: 600; }
    .cfg-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-top: 8px; }
    .cfg-item { background: var(--bg); border-radius: 8px; padding: 8px 12px; }
    .cfg-item .label { margin-bottom: 3px; }
    .cfg-item .value { font-size: 0.95rem; font-weight: 600; }
    .cfg-title { font-size: 0.78rem; opacity: 0.75; text-transform: uppercase; letter-spacing: 0.7px; margin: 12px 0 4px; }
    .badge-majors { background: #1e5a7a; color: #fff; padding: 2px 10px; border-radius: 10px; font-size: 0.8rem; font-weight: 600; }
    .badge-alts { background: #b8641a; color: #fff; padding: 2px 10px; border-radius: 10px; font-size: 0.8rem; font-weight: 600; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Crypto Bot</h1>
    <p class=\"sub\">Dashboard mobile - mise a jour automatique toutes les 10s</p>

    <div class=\"tabs\">
      <button class=\"tab-btn active\" data-tab=\"dashboard\">Dashboard</button>
      <button class=\"tab-btn\" data-tab=\"config\">Configuration</button>
    </div>

    <div id=\"tab-dashboard\" class=\"tab-panel active\">
    <div class=\"grid\">
      <div class=\"card\"><div class=\"label\">Portefeuille</div><div id=\"portfolio\" class=\"value\">-</div></div>
      <div class=\"card\"><div class=\"label\">PnL</div><div id=\"pnl\" class=\"value\">-</div></div>
      <div class=\"card\"><div class=\"label\">USDT</div><div id=\"usdt\" class=\"value\">-</div></div>
      <div class=\"card\"><div class=\"label\">Trades</div><div id=\"tradesCount\" class=\"value\">-</div></div>
    </div>

    <div class=\"card\" style=\"margin-bottom: 12px;\">
      <div class=\"label\">Positions</div>
      <div id=\"positions\">Aucune position ouverte</div>
    </div>

    <div class=\"card\">
      <div class=\"label\">Derniers trades</div>
      <table>
        <thead>
          <tr><th>Date</th><th>Pair</th><th>Side</th><th>Prix</th><th>Quantite</th></tr>
        </thead>
        <tbody id=\"tradesBody\"></tbody>
      </table>
    </div>

    <div id=\"updated\" class=\"footer\">Derniere mise a jour: -</div>
    </div>

    <div id=\"tab-config\" class=\"tab-panel\">
      <div id=\"config-content\"><p style=\"opacity:0.7;padding:8px 0\">Chargement...</p></div>
    </div>
  </div>

  <script>
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token') || '';
    const headers = token ? { 'X-API-Token': token } : {};

    const fmtUsd = (v) => new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'USD' }).format(v || 0);

    function updateStats(stats) {
      document.getElementById('portfolio').textContent = fmtUsd(stats.portfolio_value);
      document.getElementById('usdt').textContent = fmtUsd(stats.usdt_balance);
      document.getElementById('tradesCount').textContent = stats.trade_count ?? 0;
      const pnlEl = document.getElementById('pnl');
      const pnlTxt = `${fmtUsd(stats.pnl)} (${(stats.pnl_pct || 0).toFixed(2)}%)`;
      pnlEl.textContent = pnlTxt;
      pnlEl.className = 'value ' + ((stats.pnl || 0) >= 0 ? 'pos' : 'neg');

      const pos = stats.positions || [];
      const posText = pos.length
        ? pos.map(p => `${p.symbol}: ${p.quantity.toFixed(6)} (~${fmtUsd(p.value)})`).join('<br/>')
        : 'Aucune position ouverte';
      document.getElementById('positions').innerHTML = posText;
    }

    function updateTrades(trades) {
      const body = document.getElementById('tradesBody');
      body.innerHTML = '';
      for (const t of trades) {
        const tr = document.createElement('tr');
        tr.className = t.side === 'BUY' ? 'row-buy' : 'row-sell';
        tr.innerHTML = `
          <td>${new Date(t.timestamp).toLocaleString('fr-FR')}</td>
          <td>${t.symbol}</td>
          <td>${t.side}</td>
          <td>${fmtUsd(t.price)}</td>
          <td>${Number(t.quantity).toFixed(6)}</td>
        `;
        body.appendChild(tr);
      }
    }

    async function load() {
      try {
        const [statsRes, tradesRes] = await Promise.all([
          fetch('/api/stats', { headers }),
          fetch('/api/trades?limit=20', { headers }),
        ]);
        if (!statsRes.ok || !tradesRes.ok) {
          throw new Error('Erreur API');
        }
        const stats = await statsRes.json();
        const trades = await tradesRes.json();
        updateStats(stats);
        updateTrades(trades.items || []);
        document.getElementById('updated').textContent = `Derniere mise a jour: ${new Date().toLocaleTimeString('fr-FR')}`;
      } catch (err) {
        document.getElementById('updated').textContent = 'Erreur de connexion API';
      }
    }

    load();
    setInterval(load, 10000);

    // --- Tab switching ---
    let configLoaded = false;
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const panel = document.getElementById('tab-' + btn.dataset.tab);
        if (panel) panel.classList.add('active');
        if (btn.dataset.tab === 'config' && !configLoaded) loadConfig();
      });
    });

    async function loadConfig() {
      try {
        const res = await fetch('/api/config', { headers });
        if (!res.ok) throw new Error('err');
        const c = await res.json();
        configLoaded = true;
        renderConfig(c);
      } catch(e) {
        document.getElementById('config-content').textContent = 'Erreur de chargement.';
      }
    }

    function renderConfig(c) {
      const symbols = c.symbols;
      const sym = symbols.map(s => `<span class=\"badge\">${s}</span>`).join(' ');
      const stopsLbl = c.stops.enabled
        ? '<span class=\"pos\">Actif</span>'
        : '<span class=\"neg\">Inactif</span>';

      const strategyGroups = c.strategy_groups;
      const groupCards = Object.entries(strategyGroups).map(([groupName, g]) => {
        const groupSymbols = g.symbols.map(s => `<span class=\"badge\">${s}</span>`).join(' ');
        return `
          <div class=\"card\" style=\"margin-bottom:12px\">
            <div class=\"label\">Groupe ${groupName}</div>
            <div style=\"margin-top:8px\">${groupSymbols}</div>
            <div class=\"cfg-grid\" style=\"margin-top:10px\">
              <div class=\"cfg-item\"><div class=\"label\">Timeframe</div><div class=\"value\">${g.timeframe}</div></div>
              <div class=\"cfg-item\"><div class=\"label\">Allocation</div><div class=\"value\">${(Number(g.trade_allocation) * 100).toFixed(0)}%</div></div>
              <div class=\"cfg-item\"><div class=\"label\">RSI</div><div class=\"value\">${g.rsi_period} / ${g.rsi_oversold}-${g.rsi_overbought}</div></div>
              <div class=\"cfg-item\"><div class=\"label\">MACD</div><div class=\"value\">${g.macd_fast} / ${g.macd_slow} / ${g.macd_signal}</div></div>
              <div class=\"cfg-item\"><div class=\"label\">Stop-Loss</div><div class=\"value neg\">${g.stop_loss_pct}%</div></div>
              <div class=\"cfg-item\"><div class=\"label\">Take-Profit</div><div class=\"value pos\">+${g.take_profit_pct}%</div></div>
            </div>
          </div>`;
      }).join('');

      const symbolProfiles = c.symbol_profiles;
      const symbolRows = Object.entries(symbolProfiles).map(([symbol, p]) => {
        const badgeClass = p.group === 'majors' ? 'badge-majors' : 'badge-alts';
        return `
        <tr>
          <td>${symbol}</td>
          <td><span class="${badgeClass}">${p.group}</span></td>
          <td>${p.timeframe}</td>
          <td>${(Number(p.trade_allocation) * 100).toFixed(0)}%</td>
          <td>${p.stop_loss_pct}%</td>
          <td>+${p.take_profit_pct}%</td>
        </tr>
      `;
      }).join('');

      document.getElementById('config-content').innerHTML = `
        <div class=\"card\" style=\"margin-bottom:12px\">
          <div class=\"label\">Symboles trades</div>
          <div style=\"margin-top:8px\">${sym}</div>
          <div class=\"cfg-grid\" style=\"margin-top:10px\">
            <div class=\"cfg-item\"><div class=\"label\">Timeframe global fallback</div><div class=\"value\">${c.timeframe}</div></div>
            <div class=\"cfg-item\"><div class=\"label\">Bougies</div><div class=\"value\">${c.ohlcv_limit}</div></div>
            <div class=\"cfg-item\"><div class=\"label\">Intervalle fallback</div><div class=\"value\">${c.loop_interval_seconds}s</div></div>
          </div>
        </div>

        ${groupCards}

        <div class=\"card\" style=\"margin-bottom:12px\">
          <div class=\"label\">Mapping symboles -> groupe</div>
          <table style=\"margin-top:8px\">
            <thead>
              <tr><th>Symbole</th><th>Groupe</th><th>Timeframe</th><th>Alloc</th><th>SL</th><th>TP</th></tr>
            </thead>
            <tbody>
              ${symbolRows}
            </tbody>
          </table>
        </div>

        <div class=\"card\" style=\"margin-bottom:12px\">
          <div class=\"label\">Paper Trading (fallback global)</div>
          <div class=\"cfg-grid\">
            <div class=\"cfg-item\"><div class=\"label\">Capital initial</div><div class=\"value\">${fmtUsd(c.initial_capital)}</div></div>
            <div class=\"cfg-item\"><div class=\"label\">Allocation/trade fallback</div><div class=\"value\">${(c.trade_allocation * 100).toFixed(0)}%</div></div>
          </div>
        </div>

        <div class=\"card\" style=\"margin-bottom:12px\">
          <div class=\"label\">Gestion du risque fallback ${stopsLbl}</div>
          <div class=\"cfg-grid\">
            <div class=\"cfg-item\"><div class=\"label\">Stop-Loss</div><div class=\"value neg\">${c.stops.stop_loss_pct}%</div></div>
            <div class=\"cfg-item\"><div class=\"label\">Take-Profit</div><div class=\"value pos\">+${c.stops.take_profit_pct}%</div></div>
          </div>
        </div>

        <div class=\"card\">
          <div class=\"label\">Frais &amp; Slippage</div>
          <div class=\"cfg-grid\">
            <div class=\"cfg-item\"><div class=\"label\">Frais taker</div><div class=\"value\">${c.fees.taker_fee_pct}%</div></div>
            <div class=\"cfg-item\"><div class=\"label\">Slippage</div><div class=\"value\">${c.fees.slippage_pct}%</div></div>
          </div>
        </div>`;
    }
  </script>
</body>
</html>
"""


class MobileAPIServer:
    def __init__(self, state_provider: Callable[[], dict]) -> None:
        self._state_provider = state_provider

    def create_handler(self):
        state_provider = self._state_provider

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, payload: dict | list, status: int = HTTPStatus.OK) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _send_html(self, html: str) -> None:
                raw = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _is_authorized(self, query: dict[str, list[str]]) -> bool:
                if not config.API_TOKEN:
                    return True
                header_token = self.headers.get("X-API-Token", "")
                query_token = (query.get("token") or [""])[0]
                return header_token == config.API_TOKEN or query_token == config.API_TOKEN

            def _deny(self) -> None:
                self._send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)

                if parsed.path == "/health":
                    self._send_json({"status": "ok"})
                    return

                if not self._is_authorized(query):
                    self._deny()
                    return

                if parsed.path == "/":
                    self._send_html(_dashboard_html())
                    return

                state = state_provider()
                if parsed.path == "/api/stats":
                    self._send_json(state.get("stats", {}))
                    return
                if parsed.path == "/api/positions":
                    self._send_json({"items": state.get("positions", [])})
                    return
                if parsed.path == "/api/trades":
                    limit = 20
                    try:
                        limit = int((query.get("limit") or ["20"])[0])
                    except ValueError:
                        pass
                    trades = state.get("trades", [])[: max(1, min(limit, 200))]
                    self._send_json({"items": trades})
                    return
                if parsed.path == "/api/history":
                    limit = 120
                    try:
                        limit = int((query.get("limit") or ["120"])[0])
                    except ValueError:
                        pass
                    history = state.get("history", [])[-max(1, min(limit, 1000)) :]
                    self._send_json({"items": history})
                    return
                if parsed.path == "/api/config":
                    symbol_profiles = {
                        symbol: config.get_symbol_config(symbol)
                        for symbol in config.SYMBOLS
                    }
                    self._send_json({
                        "symbols": config.SYMBOLS,
                        "timeframe": config.TIMEFRAME,
                        "strategy_groups": config.STRATEGY_GROUPS,
                        "symbol_profiles": symbol_profiles,
                        "ohlcv_limit": config.OHLCV_LIMIT,
                        "initial_capital": config.INITIAL_CAPITAL_USDT,
                        "trade_allocation": config.TRADE_ALLOCATION,
                        "rsi": {
                            "period": config.RSI_PERIOD,
                            "oversold": config.RSI_OVERSOLD,
                            "overbought": config.RSI_OVERBOUGHT,
                        },
                        "macd": {
                            "fast": config.MACD_FAST,
                            "slow": config.MACD_SLOW,
                            "signal": config.MACD_SIGNAL,
                        },
                        "stops": {
                            "enabled": config.ENABLE_STOPS,
                            "stop_loss_pct": config.STOP_LOSS_PCT,
                            "take_profit_pct": config.TAKE_PROFIT_PCT,
                        },
                        "fees": {
                            "taker_fee_pct": config.TAKER_FEE_PCT,
                            "slippage_pct": config.SLIPPAGE_PCT,
                        },
                        "loop_interval_seconds": config.LOOP_INTERVAL_SECONDS,
                    })
                    return

                self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

            def log_message(self, fmt: str, *args):  # type: ignore[override]
                logger.debug("API %s - %s", self.client_address, fmt % args)

        return Handler


def start_server_in_thread(state_provider: Callable[[], dict]) -> threading.Thread:
    server = MobileAPIServer(state_provider)
    httpd = ThreadingHTTPServer((config.API_HOST, config.API_PORT), server.create_handler())

    def run_server() -> None:
        logger.info("API mobile disponible sur http://%s:%s", config.API_HOST, config.API_PORT)
        if config.API_TOKEN:
            logger.info("API token active (header X-API-Token ou ?token=...).")
        httpd.serve_forever()

    thread = threading.Thread(target=run_server, name="mobile-api", daemon=True)
    thread.start()
    return thread
