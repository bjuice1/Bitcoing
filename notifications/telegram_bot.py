"""Telegram Bot API client for Bitcoin Cycle Monitor.

Uses raw HTTP POST via requests — no extra dependency needed.
"""
import logging
import requests

logger = logging.getLogger("btcmonitor.telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramBot:
    """Thin wrapper around Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.base_url = TELEGRAM_API.format(token=bot_token)

    # ── core API ─────────────────────────────────────

    def send_message(self, text: str, chat_id: str = None,
                     parse_mode: str = "Markdown") -> dict:
        """Send a text message. Returns Telegram API response dict."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id or self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Telegram API error: %s", data.get("description"))
            return data
        except requests.RequestException as e:
            logger.error("Telegram send failed: %s", e)
            raise

    def verify_token(self) -> dict:
        """Verify bot token via getMe endpoint."""
        url = f"{self.base_url}/getMe"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── high-level sends ─────────────────────────────

    def send_weekly_digest(self, digest_data: dict) -> dict:
        """Format and send weekly digest."""
        text = self._format_digest(digest_data)
        return self.send_message(text)

    def send_action(self, action_rec) -> dict:
        """Send an ActionRecommendation."""
        from utils.action_engine import ActionEngine
        engine = ActionEngine.__new__(ActionEngine)
        text = engine.format_markdown(action_rec)
        return self.send_message(text)

    def send_alert(self, alert_text: str) -> dict:
        """Send a pre-formatted alert message."""
        return self.send_message(alert_text)

    # ── formatters ───────────────────────────────────

    def _format_digest(self, d: dict) -> str:
        """Format digest dict into Telegram Markdown."""
        sig = d.get("signal", {})
        price = d.get("price", {})
        port = d.get("portfolio", {})
        edu = d.get("education", {})

        lines = [
            "*Weekly Bitcoin Digest*",
            f"_{d.get('period', '')}_",
            "",
            f"Signal: *{sig.get('color', '?')}* — {sig.get('label', '')}",
            sig.get("action", ""),
            "",
            f"Price: ${price.get('current', 0):,.0f} "
            f"({price.get('change_pct', 0):+.1f}% this week)",
            f"Mood: {d.get('mood', {}).get('fear_greed', '?')}/100",
        ]

        if port.get("total_invested", 0) > 0:
            sats = int(port.get("total_btc", 0) * 1e8)
            lines += [
                "",
                f"Your Stack: {sats:,} sats (${port.get('current_value', 0):,.0f})",
                f"P&L: {port.get('roi_pct', 0):+.1f}%",
            ]

        if edu:
            lines += [
                "",
                f"_{edu.get('title', '')}_",
                (edu.get("content", "") or "").split("\n\n")[0][:200],
            ]

        return "\n".join(lines)
