"""Tests for hardened macOS desktop notifications."""
import time
import pytest
from unittest.mock import patch, MagicMock
from alerts.channels import DesktopChannel, ConsoleChannel, FileChannel


class MockAlert:
    """Minimal alert object for testing."""
    def __init__(self, rule_name="test_rule", severity="WARNING", message="test message",
                 rule_id="r1", metric_value=50, threshold=20, triggered_at=None):
        self.rule_name = rule_name
        self.severity = severity
        self.message = message
        self.rule_id = rule_id
        self.metric_value = metric_value
        self.threshold = threshold
        if triggered_at is None:
            from datetime import datetime, timezone
            self.triggered_at = datetime.now(timezone.utc)
        else:
            self.triggered_at = triggered_at


class TestDesktopChannel:
    def test_sanitize_strips_quotes(self):
        channel = DesktopChannel()
        result = channel._sanitize_text('He said "hello" and \\n escaped')
        assert '"' not in result
        assert '\\' not in result
        assert '\n' not in result

    def test_sanitize_truncates(self):
        channel = DesktopChannel()
        long_text = "x" * 300
        result = channel._sanitize_text(long_text)
        assert len(result) == 200

    def test_non_macos_returns_false(self):
        channel = DesktopChannel()
        channel._is_macos = False
        alert = MockAlert()
        result = channel.send(alert)
        assert result is False

    def test_rate_limiting_critical(self):
        channel = DesktopChannel(config={
            "notifications": {"critical_rate_limit_minutes": 15}
        })
        # Simulate a recent send
        channel._send_history["CRITICAL"] = [time.time()]
        assert channel._is_rate_limited("CRITICAL") is True

    def test_rate_limiting_not_exceeded(self):
        channel = DesktopChannel()
        # No recent sends
        channel._send_history["CRITICAL"] = []
        assert channel._is_rate_limited("CRITICAL") is False

    def test_rate_limiting_expired_entries_pruned(self):
        channel = DesktopChannel(config={
            "notifications": {"warning_rate_limit_minutes": 30}
        })
        # Entry from 31 minutes ago should be pruned
        old_time = time.time() - (31 * 60)
        channel._send_history["WARNING"] = [old_time]
        assert channel._is_rate_limited("WARNING") is False

    def test_info_allows_multiple(self):
        channel = DesktopChannel(config={
            "notifications": {"info_rate_limit_per_hour": 3}
        })
        now = time.time()
        channel._send_history["INFO"] = [now - 100, now - 50]
        assert channel._is_rate_limited("INFO") is False  # 2 < 3

        channel._send_history["INFO"] = [now - 100, now - 50, now - 10]
        assert channel._is_rate_limited("INFO") is True  # 3 >= 3

    @patch("alerts.channels.subprocess.run")
    def test_send_calls_subprocess(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        channel = DesktopChannel()
        channel._is_macos = True

        alert = MockAlert(severity="WARNING", message="Test alert")
        result = channel.send(alert)

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0][0] == "osascript"
        assert args[0][0][1] == "-e"

    @patch("alerts.channels.subprocess.run")
    def test_critical_includes_sound(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        channel = DesktopChannel(config={"notifications": {"sound": "Glass"}})
        channel._is_macos = True

        alert = MockAlert(severity="CRITICAL", message="Critical test")
        channel.send(alert)

        script_arg = mock_run.call_args[0][0][2]
        assert 'sound name "Glass"' in script_arg

    @patch("alerts.channels.subprocess.run")
    def test_warning_no_sound(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        channel = DesktopChannel()
        channel._is_macos = True

        alert = MockAlert(severity="WARNING", message="Warning test")
        channel.send(alert)

        script_arg = mock_run.call_args[0][0][2]
        assert "sound name" not in script_arg

    @patch("alerts.channels.subprocess.run")
    def test_injection_attempt_sanitized(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        channel = DesktopChannel()
        channel._is_macos = True

        alert = MockAlert(
            severity="WARNING",
            message='Test" ; echo "INJECTED" ; osascript -e "',
        )
        channel.send(alert)

        # The script should not contain the original double quotes
        script_arg = mock_run.call_args[0][0][2]
        assert "INJECTED" in script_arg  # text is there but as literal
        assert '" ;' not in script_arg   # injection attempt was sanitized

    @patch("alerts.channels.subprocess.run")
    def test_subprocess_timeout_handled(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=5)
        channel = DesktopChannel()
        channel._is_macos = True

        alert = MockAlert()
        result = channel.send(alert)
        assert result is False


class TestConsoleChannel:
    def test_send_no_crash(self):
        """ConsoleChannel should handle string severity."""
        channel = ConsoleChannel()
        alert = MockAlert(severity="INFO", message="test")
        # Should not raise
        channel.send(alert)


class TestFileChannel:
    def test_send_writes_json(self, tmp_path):
        log_file = tmp_path / "alerts.jsonl"
        channel = FileChannel(log_path=str(log_file))
        alert = MockAlert()
        channel.send(alert)

        content = log_file.read_text()
        assert "test_rule" in content
        assert "WARNING" in content
