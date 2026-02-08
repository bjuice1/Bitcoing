"""Alert notification channels."""
import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

logger = logging.getLogger("btcmonitor.alerts.channels")


@runtime_checkable
class AlertChannel(Protocol):
    def send(self, alert) -> None: ...


class ConsoleChannel:
    """Print alerts to terminal with rich formatting."""

    def send(self, alert):
        from rich.console import Console
        console = Console()

        severity_styles = {
            "CRITICAL": "bold white on red",
            "WARNING": "bold yellow",
            "INFO": "bold blue",
        }
        style = severity_styles.get(alert.severity, "")
        console.print(f"[{style}] [{alert.severity}] {alert.rule_name}: {alert.message}[/]")


class FileChannel:
    """Append alerts to a JSON lines log file."""

    def __init__(self, log_path="data/alerts.jsonl"):
        self.log_path = log_path

    def send(self, alert):
        entry = {
            "timestamp": alert.triggered_at.isoformat(),
            "rule_id": alert.rule_id,
            "rule_name": alert.rule_name,
            "severity": alert.severity,
            "metric_value": alert.metric_value,
            "threshold": alert.threshold,
            "message": alert.message,
        }
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write alert to file: {e}")


class DesktopChannel:
    """macOS desktop notifications via osascript."""

    def __init__(self, min_severity="WARNING", max_per_5min=1):
        self.min_severity = min_severity
        self.max_per_5min = max_per_5min
        self._recent_notifications = []
        self._severity_order = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}

    def send(self, alert):
        sev_level = self._severity_order.get(alert.severity, 0)
        min_level = self._severity_order.get(self.min_severity, 1)
        if sev_level < min_level:
            return

        # Rate limiting
        now = time.time()
        self._recent_notifications = [t for t in self._recent_notifications if now - t < 300]
        if len(self._recent_notifications) >= self.max_per_5min:
            return

        title = f"BTC Alert [{alert.severity}]"
        message = f"{alert.rule_name}: {alert.message}"
        # Escape single quotes for osascript
        message = message.replace("'", "'\"'\"'")
        title = title.replace("'", "'\"'\"'")

        try:
            os.system(f"osascript -e 'display notification \"{message}\" with title \"{title}\"'")
            self._recent_notifications.append(now)
        except Exception as e:
            logger.warning(f"Desktop notification failed: {e}")

    def send_sound(self):
        """Play alert sound for critical alerts."""
        try:
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
        except Exception:
            pass
