from __future__ import annotations

import json
import logging
from typing import Dict
from urllib import error, parse, request

import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)

    @classmethod
    def from_config(cls) -> "TelegramNotifier":
        return cls(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)

    def send_message(self, text: str) -> None:
        if not self.enabled:
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = parse.urlencode({"chat_id": self.chat_id, "text": text}).encode("utf-8")

        try:
            req = request.Request(url, data=payload, method="POST")
            with request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                if not data.get("ok", False):
                    logger.warning("Telegram API returned non-ok response: %s", body)
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Telegram notification failed: %s", exc)

    def send_trade(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        total_value: float,
        pnl: float,
        pnl_pct: float,
        usdt_balance: float,
    ) -> None:
        text = (
            "Trade execute\n"
            f"Pair: {symbol}\n"
            f"Side: {side}\n"
            f"Price: ${price:,.2f}\n"
            f"Quantity: {quantity:.6f}\n"
            f"USDT balance: ${usdt_balance:,.2f}\n"
            f"Portfolio: ${total_value:,.2f}\n"
            f"PnL: {pnl:+,.2f} USDT ({pnl_pct:+.2f}%)"
        )
        self.send_message(text)

    def send_loop_summary(
        self,
        prices: Dict[str, float],
        total_value: float,
        pnl: float,
        pnl_pct: float,
        usdt_balance: float,
        positions: Dict[str, float],
    ) -> None:
        if not self.enabled:
            return

        lines = [
            "Portfolio summary",
            f"USDT: ${usdt_balance:,.2f}",
            f"Portfolio: ${total_value:,.2f}",
            f"PnL: {pnl:+,.2f} USDT ({pnl_pct:+.2f}%)",
            "Prices:",
        ]

        for symbol, price in prices.items():
            lines.append(f"- {symbol}: ${price:,.2f}")

        if positions:
            lines.append("Positions:")
            for symbol, qty in positions.items():
                if qty > 0:
                    lines.append(f"- {symbol}: {qty:.6f}")

        self.send_message("\n".join(lines))
