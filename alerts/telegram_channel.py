"""Telegram alert channel — implements AlertChannel protocol."""
import logging

logger = logging.getLogger("btcmonitor.alerts.telegram")

_SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}
_SEVERITY_EMOJI = {
    "CRITICAL": "\u2757\u2757",
    "WARNING": "\u26a0\ufe0f",
    "INFO": "\u2139\ufe0f",
}


class TelegramChannel:
    """Send alert notifications via Telegram.

    Implements the AlertChannel protocol: send(self, alert) -> None.
    """

    def __init__(self, bot, min_severity="WARNING"):
        self.bot = bot
        self.min_severity = min_severity

    def send(self, alert) -> None:
        """Send alert via Telegram if severity meets threshold."""
        sev = _SEVERITY_ORDER.get(alert.severity, 0)
        threshold = _SEVERITY_ORDER.get(self.min_severity, 1)
        if sev < threshold:
            return

        emoji = _SEVERITY_EMOJI.get(alert.severity, "")
        text = (
            f"{emoji} *BTC Alert [{alert.severity}]*\n"
            f"{alert.rule_name}: {alert.message}"
        )

        try:
            self.bot.send_message(text)
        except Exception as e:
            logger.warning("Telegram alert failed: %s", e)
