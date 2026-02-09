"""Tests for Telegram bot and channel."""
import pytest
from unittest.mock import patch, MagicMock


# ── TelegramBot tests ────────────────────────────────

def test_send_message():
    """send_message makes correct HTTP POST."""
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"ok": True, "result": {}}),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        from notifications.telegram_bot import TelegramBot
        bot = TelegramBot("fake_token", "123456")
        result = bot.send_message("hello")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["chat_id"] == "123456"
        assert payload["text"] == "hello"
        assert payload["parse_mode"] == "Markdown"


def test_send_message_custom_chat_id():
    """send_message with explicit chat_id overrides default."""
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"ok": True}),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        from notifications.telegram_bot import TelegramBot
        bot = TelegramBot("token", "default_id")
        bot.send_message("test", chat_id="other_id")

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["chat_id"] == "other_id"


def test_verify_token():
    """verify_token calls getMe."""
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"ok": True, "result": {"username": "testbot"}}),
        )
        mock_get.return_value.raise_for_status = MagicMock()

        from notifications.telegram_bot import TelegramBot
        bot = TelegramBot("fake_token", "123")
        result = bot.verify_token()
        assert result["ok"]
        assert "getMe" in mock_get.call_args[0][0]


def test_format_digest():
    """_format_digest produces readable Markdown."""
    from notifications.telegram_bot import TelegramBot
    bot = TelegramBot("token", "123")

    digest = {
        "period": "Feb 1 to Feb 8, 2026",
        "signal": {"color": "GREEN", "label": "Favorable", "action": "Keep buying."},
        "price": {"current": 71000, "change_pct": 2.4},
        "mood": {"fear_greed": 7},
        "portfolio": {"total_invested": 5000, "total_btc": 0.05, "current_value": 3550, "roi_pct": -29.0},
        "education": {"title": "What is DCA?", "content": "Dollar cost averaging means..."},
    }
    text = bot._format_digest(digest)
    assert "GREEN" in text
    assert "71,000" in text
    assert "sats" in text.lower() or "Stack" in text


def test_send_weekly_digest():
    """send_weekly_digest calls send_message with formatted text."""
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"ok": True}),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        from notifications.telegram_bot import TelegramBot
        bot = TelegramBot("token", "123")
        bot.send_weekly_digest({
            "period": "test",
            "signal": {"color": "GREEN", "label": "Good", "action": "Buy."},
            "price": {"current": 70000, "change_pct": 1.0},
            "mood": {"fear_greed": 25},
            "portfolio": {"total_invested": 0, "total_btc": 0, "current_value": 0, "roi_pct": 0},
            "education": {"title": "Test", "content": "Content here"},
        })
        mock_post.assert_called_once()


# ── TelegramChannel tests ────────────────────────────

def test_channel_filters_info():
    """INFO alerts filtered when min_severity=WARNING."""
    from alerts.telegram_channel import TelegramChannel
    bot = MagicMock()
    channel = TelegramChannel(bot, min_severity="WARNING")

    alert = MagicMock()
    alert.severity = "INFO"
    alert.rule_name = "Test"
    alert.message = "Test msg"

    channel.send(alert)
    bot.send_message.assert_not_called()


def test_channel_passes_warning():
    """WARNING alerts go through when min_severity=WARNING."""
    from alerts.telegram_channel import TelegramChannel
    bot = MagicMock()
    channel = TelegramChannel(bot, min_severity="WARNING")

    alert = MagicMock()
    alert.severity = "WARNING"
    alert.rule_name = "Extreme Fear"
    alert.message = "F&G below 20"

    channel.send(alert)
    bot.send_message.assert_called_once()
    text = bot.send_message.call_args[0][0]
    assert "WARNING" in text
    assert "Extreme Fear" in text


def test_channel_passes_critical():
    """CRITICAL alerts always go through."""
    from alerts.telegram_channel import TelegramChannel
    bot = MagicMock()
    channel = TelegramChannel(bot, min_severity="CRITICAL")

    alert = MagicMock()
    alert.severity = "CRITICAL"
    alert.rule_name = "Crash"
    alert.message = "BTC down 20%"

    channel.send(alert)
    bot.send_message.assert_called_once()


def test_channel_handles_send_failure():
    """TelegramChannel logs warning on send failure, doesn't raise."""
    from alerts.telegram_channel import TelegramChannel
    bot = MagicMock()
    bot.send_message.side_effect = Exception("Network error")
    channel = TelegramChannel(bot, min_severity="WARNING")

    alert = MagicMock()
    alert.severity = "CRITICAL"
    alert.rule_name = "Test"
    alert.message = "msg"

    # Should not raise
    channel.send(alert)


# ── CLI help tests ───────────────────────────────────

def test_cli_telegram_help():
    from click.testing import CliRunner
    import main as m
    runner = CliRunner()
    result = runner.invoke(m.cli, ["telegram", "--help"])
    assert result.exit_code == 0
    assert "setup" in result.output
    assert "test" in result.output
    assert "send-digest" in result.output
    assert "send-action" in result.output
