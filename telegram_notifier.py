from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, Dict
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

    def _api_get(self, method: str, params: Dict[str, str]) -> Dict:
        query = parse.urlencode(params)
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}?{query}"
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
        if not data.get("ok", False):
            logger.warning("Telegram API non-ok on %s: %s", method, data)
            return {}
        return data

    def _poll_updates(self, offset: int | None = None) -> tuple[list[dict], int | None]:
        params = {"timeout": "25", "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            params["offset"] = str(offset)
        try:
            payload = self._api_get("getUpdates", params)
            items = payload.get("result", []) if payload else []
            next_offset = offset
            for item in items:
                update_id = item.get("update_id")
                if isinstance(update_id, int):
                    next_offset = update_id + 1
            return items, next_offset
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Telegram polling failed: %s", exc)
            return [], offset

    def start_command_listener(self, handler: Callable[[str, list[str]], str]) -> None:
        if not self.enabled:
            return

        def loop() -> None:
            logger.info("Telegram command listener actif.")
            offset = None
            while True:
                updates, offset = self._poll_updates(offset)
                for update in updates:
                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    chat_id = str(chat.get("id", ""))
                    if chat_id != self.chat_id:
                        continue
                    text = (message.get("text") or "").strip()
                    if not text.startswith("/"):
                        continue

                    command_line = text[1:]
                    parts = command_line.split()
                    if not parts:
                        continue
                    command = parts[0]
                    args = parts[1:]
                    if "@" in command:
                        command = command.split("@", 1)[0]

                    try:
                        response = handler(command, args)
                    except Exception as exc:
                        logger.exception("Erreur handler Telegram: %s", exc)
                        response = "Erreur interne sur la commande."
                    self.send_message(response)

                time.sleep(max(1, config.TELEGRAM_POLL_INTERVAL_SECONDS))

        thread = threading.Thread(target=loop, name="telegram-cmd", daemon=True)
        thread.start()

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
