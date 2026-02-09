"""Tests for email sender and email alert channel."""
import pytest
import time
from unittest.mock import patch, MagicMock, call
from notifications.email_sender import EmailSender
from alerts.channels import EmailChannel


class MockAlert:
    """Minimal alert object for testing."""
    def __init__(self, rule_name="test_rule", severity="CRITICAL", message="test"):
        self.rule_name = rule_name
        self.severity = severity
        self.message = message
        self.metric_value = 50
        self.threshold = 20
        from datetime import datetime, timezone
        self.triggered_at = datetime.now(timezone.utc)


class TestEmailSender:
    def test_not_configured_missing_fields(self):
        sender = EmailSender({"email": {}})
        assert sender.is_configured() is False

    def test_configured_with_all_fields(self):
        sender = EmailSender({"email": {
            "smtp_host": "smtp.test.com",
            "from_address": "test@test.com",
            "to_address": "recv@test.com",
            "smtp_username": "user",
            "smtp_password": "pass",
        }})
        assert sender.is_configured() is True

    def test_env_vars_override_config(self):
        with patch.dict("os.environ", {
            "BTC_MONITOR_SMTP_USER": "env_user",
            "BTC_MONITOR_SMTP_PASS": "env_pass",
        }):
            sender = EmailSender({"email": {
                "smtp_username": "config_user",
                "smtp_password": "config_pass",
            }})
            assert sender.username == "env_user"
            assert sender.password == "env_pass"

    def test_config_used_without_env_vars(self):
        with patch.dict("os.environ", {}, clear=True):
            # Remove the env vars if present
            import os
            os.environ.pop("BTC_MONITOR_SMTP_USER", None)
            os.environ.pop("BTC_MONITOR_SMTP_PASS", None)

            sender = EmailSender({"email": {
                "smtp_username": "config_user",
                "smtp_password": "config_pass",
            }})
            assert sender.username == "config_user"
            assert sender.password == "config_pass"

    def test_send_digest_returns_false_when_not_configured(self):
        sender = EmailSender({"email": {}})
        result = sender.send_digest("<h1>Test</h1>")
        assert result is False

    def test_send_alert_returns_false_when_not_configured(self):
        sender = EmailSender({"email": {}})
        result = sender.send_alert("test", "CRITICAL", "test msg")
        assert result is False

    @patch("notifications.email_sender.smtplib.SMTP")
    def test_send_digest_success(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        sender = EmailSender({"email": {
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
            "from_address": "test@test.com",
            "to_address": "recv@test.com",
            "smtp_username": "user",
            "smtp_password": "pass",
        }})

        result = sender.send_digest("<h1>Digest</h1>", subject="Test Digest")
        assert result is True
        mock_server.send_message.assert_called_once()

    @patch("notifications.email_sender.smtplib.SMTP")
    def test_send_digest_with_charts(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        sender = EmailSender({"email": {
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
            "from_address": "test@test.com",
            "to_address": "recv@test.com",
            "smtp_username": "user",
            "smtp_password": "pass",
        }})

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        chart_images = [("test_chart", fake_png)]
        result = sender.send_digest("<h1>Digest</h1>", chart_images=chart_images)
        assert result is True

        # Verify the message was sent with chart attachment
        sent_msg = mock_server.send_message.call_args[0][0]
        payloads = sent_msg.get_payload()
        # Should have multipart/alternative + image
        assert len(payloads) == 2  # alternative + image

    @patch("notifications.email_sender.smtplib.SMTP")
    def test_send_alert_success(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        sender = EmailSender({"email": {
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
            "from_address": "test@test.com",
            "to_address": "recv@test.com",
            "smtp_username": "user",
            "smtp_password": "pass",
        }})

        result = sender.send_alert("High MVRV", "CRITICAL", "MVRV above 3.5")
        assert result is True

    @patch("notifications.email_sender.smtplib.SMTP")
    def test_auth_failure_returns_false(self, mock_smtp_class):
        import smtplib
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        sender = EmailSender({"email": {
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
            "from_address": "test@test.com",
            "to_address": "recv@test.com",
            "smtp_username": "user",
            "smtp_password": "wrong",
        }})

        result = sender.send_digest("<h1>Test</h1>")
        assert result is False

    def test_test_connection_no_server(self):
        sender = EmailSender({"email": {
            "smtp_host": "nonexistent.invalid",
            "smtp_port": 587,
            "smtp_username": "user",
            "smtp_password": "pass",
        }})
        result = sender.test_connection()
        assert result["status"] == "error"

    def test_default_config_values(self):
        sender = EmailSender({})
        assert sender.smtp_host == "smtp.gmail.com"
        assert sender.smtp_port == 587
        assert sender.use_tls is True
        assert sender.from_name == "Bitcoin Monitor"


class TestEmailChannel:
    def test_only_sends_critical(self):
        config = {"email": {
            "smtp_host": "smtp.test.com",
            "from_address": "a@b.com",
            "to_address": "c@d.com",
            "smtp_username": "u",
            "smtp_password": "p",
            "critical_alerts_enabled": True,
        }}
        channel = EmailChannel(config)
        # WARNING should not send
        alert = MockAlert(severity="WARNING")
        result = channel.send(alert)
        assert result is False

    @patch("notifications.email_sender.smtplib.SMTP")
    def test_sends_critical(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        config = {"email": {
            "smtp_host": "smtp.test.com",
            "from_address": "a@b.com",
            "to_address": "c@d.com",
            "smtp_username": "u",
            "smtp_password": "p",
        }}
        channel = EmailChannel(config)
        alert = MockAlert(severity="CRITICAL")
        result = channel.send(alert)
        assert result is True

    @patch("notifications.email_sender.smtplib.SMTP")
    def test_rate_limiting(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        config = {"email": {
            "smtp_host": "smtp.test.com",
            "from_address": "a@b.com",
            "to_address": "c@d.com",
            "smtp_username": "u",
            "smtp_password": "p",
        }}
        channel = EmailChannel(config)

        # First send should work
        alert = MockAlert(severity="CRITICAL")
        assert channel.send(alert) is True

        # Second send within cooldown should be rate limited
        assert channel.send(alert) is False

    def test_disabled_returns_false(self):
        config = {"email": {"critical_alerts_enabled": False}}
        channel = EmailChannel(config)
        alert = MockAlert(severity="CRITICAL")
        result = channel.send(alert)
        assert result is False

    def test_not_configured_returns_false(self):
        config = {"email": {}}
        channel = EmailChannel(config)
        alert = MockAlert(severity="CRITICAL")
        result = channel.send(alert)
        assert result is False
