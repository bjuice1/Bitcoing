"""Alert notification channels."""
import json
import subprocess
import sys
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
        sev = alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity)
        style = severity_styles.get(sev, "")
        console.print(f"[{style}] [{sev}] {alert.rule_name}: {alert.message}[/]")


class FileChannel:
    """Append alerts to a JSON lines log file."""

    def __init__(self, log_path="data/alerts.jsonl"):
        self.log_path = log_path

    def send(self, alert):
        sev = alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity)
        entry = {
            "timestamp": alert.triggered_at.isoformat() if hasattr(alert.triggered_at, 'isoformat') else str(alert.triggered_at),
            "rule_id": getattr(alert, 'rule_id', ''),
            "rule_name": getattr(alert, 'rule_name', ''),
            "severity": sev,
            "metric_value": getattr(alert, 'metric_value', None),
            "threshold": getattr(alert, 'threshold', None),
            "message": getattr(alert, 'message', ''),
        }
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write alert to file: {e}")


class DesktopChannel:
    """macOS native notifications via osascript (hardened).

    Uses subprocess.run() with argument list (no shell) to prevent injection.
    Severity-based behavior: sound for CRITICAL, silent banners for others.
    Per-severity rate limiting.
    Silently degrades on non-macOS platforms.
    """

    def __init__(self, config=None):
        self.config = config or {}
        notif_cfg = self.config.get("notifications", {})

        self._sound = notif_cfg.get("sound", "Purr")
        self._is_macos = sys.platform == "darwin"

        # Per-severity rate limits
        crit_mins = notif_cfg.get("critical_rate_limit_minutes", 15)
        warn_mins = notif_cfg.get("warning_rate_limit_minutes", 30)
        info_per_hr = notif_cfg.get("info_rate_limit_per_hour", 3)

        self._rate_limits = {
            "CRITICAL": {"max": 1, "window": crit_mins * 60},
            "WARNING":  {"max": 1, "window": warn_mins * 60},
            "INFO":     {"max": info_per_hr, "window": 3600},
        }
        self._send_history: dict[str, list[float]] = {
            "CRITICAL": [], "WARNING": [], "INFO": [],
        }

    def _sanitize_text(self, text: str) -> str:
        """Remove characters that could break AppleScript string literals.

        Strips backslashes, double quotes, newlines. Truncates to 200 chars.
        """
        sanitized = str(text).replace("\\", "").replace('"', "'").replace("\n", " ")
        return sanitized[:200]

    def _is_rate_limited(self, severity: str) -> bool:
        """Check if we've exceeded the rate limit for this severity."""
        now = time.time()
        limit = self._rate_limits.get(severity, self._rate_limits["INFO"])
        history = self._send_history.get(severity, [])

        # Prune entries outside window
        cutoff = now - limit["window"]
        history = [t for t in history if t > cutoff]
        self._send_history[severity] = history

        return len(history) >= limit["max"]

    def send(self, alert) -> bool:
        """Send a macOS notification for the given alert.

        Returns True if sent, False if skipped (rate limit, non-macOS, error).
        """
        if not self._is_macos:
            return False

        severity = alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity)

        if self._is_rate_limited(severity):
            logger.debug(f"DesktopChannel: rate limited for {severity}")
            return False

        title = self._sanitize_text(f"BTC Monitor: {alert.rule_name}")
        message = self._sanitize_text(getattr(alert, 'message', str(alert)))
        subtitle = f"{severity} Alert"

        script = f'display notification "{message}" with title "{title}" subtitle "{subtitle}"'
        if severity == "CRITICAL":
            script += f' sound name "{self._sound}"'

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.warning(f"osascript failed: {result.stderr.strip()}")
                return False

            self._send_history.setdefault(severity, []).append(time.time())
            logger.debug(f"Notification sent: [{severity}] {title}")
            return True

        except subprocess.TimeoutExpired:
            logger.warning("osascript timed out after 5s")
            return False
        except FileNotFoundError:
            logger.warning("osascript not found — not on macOS?")
            self._is_macos = False
            return False
        except Exception as e:
            logger.warning(f"Notification error: {e}")
            return False


class EmailChannel:
    """Email alert channel — sends CRITICAL alerts as individual emails.

    Only sends for CRITICAL severity to avoid inbox flooding.
    Rate limited: max 1 email per 30 minutes.
    """

    def __init__(self, config: dict):
        from notifications.email_sender import EmailSender
        self.sender = EmailSender(config)
        self.enabled = config.get("email", {}).get("critical_alerts_enabled", True)
        self._last_sent = 0
        self._cooldown = 1800  # 30 minutes

    def send(self, alert) -> bool:
        if not self.enabled or not self.sender.is_configured():
            return False

        severity = alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity)
        if severity != "CRITICAL":
            return False

        now = time.time()
        if now - self._last_sent < self._cooldown:
            logger.debug("EmailChannel: rate limited")
            return False

        result = self.sender.send_alert(
            rule_name=alert.rule_name,
            severity=severity,
            message=alert.message,
            metric_value=getattr(alert, 'metric_value', None),
        )

        if result:
            self._last_sent = now
        return result
