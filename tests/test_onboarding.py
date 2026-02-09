"""Tests for onboarding wizard."""
import pytest
import yaml
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from config.onboarding import OnboardingWizard, PRESETS, RISK_TUNING


# ── preset tests ─────────────────────────────────────

def test_beginner_has_plain_english():
    assert PRESETS["beginner"]["plain_english"] is True


def test_beginner_disables_dip_alerts():
    assert PRESETS["beginner"]["smart_alerts"]["dip_alerts"] is False


def test_intermediate_enables_dip_alerts():
    assert PRESETS["intermediate"]["smart_alerts"]["dip_alerts"] is True


def test_advanced_disables_plain_english():
    assert PRESETS["advanced"]["plain_english"] is False


def test_conservative_disables_dip():
    assert RISK_TUNING["conservative"]["smart_alerts"]["dip_alerts"] is False


def test_aggressive_enables_dip():
    assert RISK_TUNING["aggressive"]["smart_alerts"]["dip_alerts"] is True


# ── config generation tests ──────────────────────────

def test_build_config_beginner_conservative():
    """Beginner + conservative = plain_english, no dips."""
    db = MagicMock()
    monitor = MagicMock()
    goal = MagicMock()
    portfolio = MagicMock()

    wizard = OnboardingWizard(db, monitor, goal, portfolio, {})
    wizard.answers = {
        "experience": "beginner",
        "risk": "conservative",
        "monthly_dca": 150,
        "couples_mode": True,
        "notifications": 2,
    }
    cfg = wizard._build_config()

    assert cfg["plain_english"] is True
    assert cfg["couples_mode"] is True
    assert cfg["default_monthly_dca"] == 150
    assert cfg["smart_alerts"]["dip_alerts"] is False
    assert "telegram" not in cfg  # notifications=2, not 3


def test_build_config_advanced_aggressive_telegram():
    """Advanced + aggressive + telegram = no plain_english, dips on, telegram section."""
    wizard = OnboardingWizard(MagicMock(), MagicMock(), MagicMock(), MagicMock(), {})
    wizard.answers = {
        "experience": "advanced",
        "risk": "aggressive",
        "monthly_dca": 500,
        "couples_mode": False,
        "notifications": 3,
    }
    cfg = wizard._build_config()

    assert cfg["plain_english"] is False
    assert cfg["couples_mode"] is False
    assert cfg["default_monthly_dca"] == 500
    assert cfg["smart_alerts"]["dip_alerts"] is True
    assert cfg["telegram"]["enabled"] is True


def test_build_config_terminal_only():
    """Notifications=1 disables desktop."""
    wizard = OnboardingWizard(MagicMock(), MagicMock(), MagicMock(), MagicMock(), {})
    wizard.answers = {
        "experience": "intermediate",
        "risk": "moderate",
        "monthly_dca": 200,
        "couples_mode": False,
        "notifications": 1,
    }
    cfg = wizard._build_config()
    assert cfg["alerts"]["desktop_notifications"] is False


# ── save/load tests ──────────────────────────────────

def test_save_config_writes_yaml():
    """_save_config writes valid YAML to file."""
    wizard = OnboardingWizard(MagicMock(), MagicMock(), MagicMock(), MagicMock(), {})
    wizard.answers = {
        "experience": "beginner",
        "risk": "moderate",
        "monthly_dca": 200,
        "couples_mode": False,
        "notifications": 2,
    }
    cfg = wizard._build_config()

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
        tmppath = f.name

    # Patch the constant so it writes to temp file
    with patch("config.onboarding.USER_CONFIG_PATH", Path(tmppath)):
        wizard._save_config(cfg)

    with open(tmppath) as f:
        loaded = yaml.safe_load(f)

    assert loaded["default_monthly_dca"] == 200
    assert "smart_alerts" in loaded

    Path(tmppath).unlink()


# ── goal/portfolio creation tests ────────────────────

def test_create_goal_btc():
    """Creates goal with BTC target."""
    goal_tracker = MagicMock()
    wizard = OnboardingWizard(MagicMock(), MagicMock(), goal_tracker, MagicMock(), {})
    wizard.answers = {
        "target_btc": 0.1,
        "goal_name": "Stack Sats",
        "monthly_dca": 200,
    }
    wizard._create_goal()
    goal_tracker.create_goal.assert_called_once_with(
        "Stack Sats", target_btc=0.1, target_usd=None, monthly_dca=200,
    )


def test_create_goal_usd():
    """Creates goal with USD target."""
    goal_tracker = MagicMock()
    wizard = OnboardingWizard(MagicMock(), MagicMock(), goal_tracker, MagicMock(), {})
    wizard.answers = {
        "target_usd": 10000,
        "goal_name": "Fund",
        "monthly_dca": 300,
    }
    wizard._create_goal()
    goal_tracker.create_goal.assert_called_once()
    call_kwargs = goal_tracker.create_goal.call_args
    assert call_kwargs.kwargs.get("target_usd") == 10000 or call_kwargs[1].get("target_usd") == 10000


def test_create_portfolio():
    """Creates portfolio with weekly amount = monthly/4."""
    portfolio = MagicMock()
    wizard = OnboardingWizard(MagicMock(), MagicMock(), MagicMock(), portfolio, {})
    wizard.answers = {"monthly_dca": 400}
    wizard._create_portfolio()
    portfolio.create_portfolio.assert_called_once_with("Main DCA", frequency="weekly", amount=100.0)


# ── CLI help test ────────────────────────────────────

def test_cli_onboard_help():
    from click.testing import CliRunner
    import main as m
    runner = CliRunner()
    result = runner.invoke(m.cli, ["onboard", "--help"])
    assert result.exit_code == 0
    assert "wizard" in result.output.lower() or "setup" in result.output.lower()
