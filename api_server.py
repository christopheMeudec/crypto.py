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
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Crypto Bot</h1>
    <p class=\"sub\">Dashboard mobile - mise a jour automatique toutes les 10s</p>

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
