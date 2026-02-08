"""Tests for plain English translation, goals, smart alerts, digest, and CLI commands."""
import pytest
import tempfile
import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
from dataclasses import dataclass


# ─── Plain English Tests ───

def test_explain_fear_greed_extreme_fear():
    from utils.plain_english import explain_fear_greed
    result = explain_fear_greed(7)
    assert "Extreme Fear" in result
    assert "panicking" in result


def test_explain_fear_greed_greed():
    from utils.plain_english import explain_fear_greed
    result = explain_fear_greed(80)
    assert "Extreme Greed" in result


def test_explain_fear_greed_neutral():
    from utils.plain_english import explain_fear_greed
    result = explain_fear_greed(50)
    assert "Neutral" in result


def test_explain_fear_greed_none():
    from utils.plain_english import explain_fear_greed
    result = explain_fear_greed(None)
    assert "unavailable" in result


def test_explain_mvrv_undervalued():
    from utils.plain_english import explain_mvrv
    result = explain_mvrv(0.7)
    assert "bargain" in result.lower() or "undervalued" in result.lower()


def test_explain_mvrv_fair():
    from utils.plain_english import explain_mvrv
    result = explain_mvrv(1.4)
    assert "fair" in result.lower() or "reasonable" in result.lower()


def test_explain_mvrv_overheated():
    from utils.plain_english import explain_mvrv
    result = explain_mvrv(4.0)
    assert "overheated" in result.lower()


def test_explain_mvrv_none():
    from utils.plain_english import explain_mvrv
    result = explain_mvrv(None)
    assert "unavailable" in result.lower()


def test_explain_drawdown_near_ath():
    from utils.plain_english import explain_drawdown
    result = explain_drawdown(3)
    assert "3%" in result
    assert "near" in result.lower() or "only" in result.lower()


def test_explain_drawdown_deep():
    from utils.plain_english import explain_drawdown
    result = explain_drawdown(50, ath=126000)
    assert "50%" in result
    assert "126,000" in result


def test_explain_hash_rate_growing():
    from utils.plain_english import explain_hash_rate
    result = explain_hash_rate(14.0)
    assert "surging" in result.lower() or "investing" in result.lower()


def test_explain_hash_rate_declining():
    from utils.plain_english import explain_hash_rate
    result = explain_hash_rate(-15.0)
    assert "declining" in result.lower() or "struggling" in result.lower()


def test_explain_cycle_phase():
    from utils.plain_english import explain_cycle_phase
    result = explain_cycle_phase("EARLY_BEAR", 659, 45)
    assert "659 days" in result
    assert "4-year cycle" in result
    assert "halves" in result.lower() or "halving" in result.lower()


def test_explain_dominance_high():
    from utils.plain_english import explain_dominance
    result = explain_dominance(62)
    assert "62" in result


def test_traffic_light_green():
    from utils.plain_english import get_traffic_light
    from models.enums import SignalStatus

    snapshot = MagicMock()
    snapshot.sentiment.fear_greed_value = 15
    snapshot.valuation.mvrv_ratio = 0.8

    signals = {
        "signals": [
            ("MVRV", SignalStatus.BULLISH, 0.8, ""),
            ("F&G", SignalStatus.BULLISH, 15, ""),
            ("Drawdown", SignalStatus.NEUTRAL, 50, ""),
        ]
    }
    result = get_traffic_light(snapshot, signals)
    assert result["color"] == "GREEN"


def test_traffic_light_red():
    from utils.plain_english import get_traffic_light
    from models.enums import SignalStatus

    snapshot = MagicMock()
    snapshot.sentiment.fear_greed_value = 85
    snapshot.valuation.mvrv_ratio = 3.5

    signals = {
        "signals": [
            ("MVRV", SignalStatus.BEARISH, 3.5, ""),
            ("F&G", SignalStatus.BEARISH, 85, ""),
            ("Drawdown", SignalStatus.BEARISH, 5, ""),
        ]
    }
    result = get_traffic_light(snapshot, signals)
    assert result["color"] == "RED"


def test_educational_topics():
    from utils.plain_english import EDUCATIONAL_TOPICS
    assert len(EDUCATIONAL_TOPICS) >= 7
    for t in EDUCATIONAL_TOPICS:
        assert "title" in t
        assert "content" in t
        assert len(t["content"]) > 50


def test_couple_framing():
    from utils.plain_english import get_couple_framing
    result = get_couple_framing("Test summary")
    assert "both" in result.lower()
    assert "Test summary" in result


# ─── Goal Tracker Tests ───

def _make_goal_db():
    """Create a test database with goals table."""
    from models.database import Database
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    db.connect()
    return db, db_path


def test_goal_create():
    from dca.goals import GoalTracker
    db, path = _make_goal_db()
    try:
        tracker = GoalTracker(db)
        gid = tracker.create_goal("Test Fund", target_btc=0.1, monthly_dca=200)
        assert gid > 0

        goal = tracker.get_goal(gid)
        assert goal is not None
        assert goal["name"] == "Test Fund"
        assert goal["target_btc"] == 0.1
    finally:
        db.close()
        os.unlink(path)


def test_goal_create_usd():
    from dca.goals import GoalTracker
    db, path = _make_goal_db()
    try:
        tracker = GoalTracker(db)
        gid = tracker.create_goal("USD Goal", target_usd=10000, monthly_dca=500)
        goal = tracker.get_goal(gid)
        assert goal["target_usd"] == 10000
    finally:
        db.close()
        os.unlink(path)


def test_goal_create_no_target():
    from dca.goals import GoalTracker
    db, path = _make_goal_db()
    try:
        tracker = GoalTracker(db)
        with pytest.raises(ValueError):
            tracker.create_goal("Bad Goal")
    finally:
        db.close()
        os.unlink(path)


def test_goal_progress():
    from dca.goals import GoalTracker
    db, path = _make_goal_db()
    try:
        tracker = GoalTracker(db)
        tracker.create_goal("Test", target_btc=1.0, monthly_dca=200)

        progress = tracker.get_progress(70000)
        assert progress is not None
        assert progress["pct_complete"] == 0  # No portfolio purchases yet
    finally:
        db.close()
        os.unlink(path)


def test_goal_milestones():
    from dca.goals import GoalTracker
    db, path = _make_goal_db()
    try:
        tracker = GoalTracker(db)
        tracker.create_goal("Test", target_btc=1.0, monthly_dca=200)
        milestones = tracker.get_milestone_status(70000)
        assert len(milestones) > 0
        # With no purchases, no BTC milestones should be hit
        btc_hits = [m for m in milestones if m["type"] == "btc" and m["hit"]]
        assert len(btc_hits) == 0
    finally:
        db.close()
        os.unlink(path)


def test_goal_list():
    from dca.goals import GoalTracker
    db, path = _make_goal_db()
    try:
        tracker = GoalTracker(db)
        tracker.create_goal("Goal 1", target_btc=0.1)
        tracker.create_goal("Goal 2", target_btc=0.5)
        goals = tracker.list_goals()
        assert len(goals) == 2
    finally:
        db.close()
        os.unlink(path)


# ─── Smart Alerts Tests ───

def test_smart_dca_reminder():
    from alerts.smart_alerts import SmartAlertEngine
    db = MagicMock()
    engine = SmartAlertEngine(db, {"smart_alerts": {"enabled": True, "dca_reminders": True}})

    snapshot = MagicMock()
    snapshot.price.price_usd = 70000

    portfolios = [{"amount": 200}]
    msg = engine.check_dca_reminder(snapshot, portfolios)
    assert msg is not None
    assert "200" in msg["message"]
    assert "sats" in msg["message"]


def test_smart_dip_opportunity():
    from alerts.smart_alerts import SmartAlertEngine
    db = MagicMock()
    engine = SmartAlertEngine(db, {"smart_alerts": {"enabled": True, "dip_alerts": True}})

    snapshot = MagicMock()
    snapshot.price.price_usd = 65000
    snapshot.price.change_24h_pct = -8.5

    msg = engine.check_dip_opportunity(snapshot)
    assert msg is not None
    assert "8.5%" in msg["message"]


def test_smart_dip_no_trigger():
    from alerts.smart_alerts import SmartAlertEngine
    db = MagicMock()
    engine = SmartAlertEngine(db, {"smart_alerts": {"enabled": True, "dip_alerts": True}})

    snapshot = MagicMock()
    snapshot.price.price_usd = 70000
    snapshot.price.change_24h_pct = 2.0

    msg = engine.check_dip_opportunity(snapshot)
    assert msg is None


def test_smart_milestone():
    from alerts.smart_alerts import SmartAlertEngine
    db = MagicMock()
    engine = SmartAlertEngine(db, {"smart_alerts": {"enabled": True, "milestone_alerts": True}})

    goal_progress = {"total_btc": 0.06, "pct_complete": 60, "current_price": 70000}
    msg = engine.check_milestone(goal_progress)
    assert msg is not None
    assert "0.05 BTC" in msg["title"]


def test_smart_disabled():
    from alerts.smart_alerts import SmartAlertEngine
    db = MagicMock()
    engine = SmartAlertEngine(db, {"smart_alerts": {"enabled": False}})
    snapshot = MagicMock()
    msgs = engine.check_all(snapshot)
    assert msgs == []


# ─── Weekly Digest Tests ───

def test_digest_format_terminal():
    from digest.weekly_digest import WeeklyDigest

    monitor = MagicMock()
    snapshot = MagicMock()
    snapshot.price.price_usd = 70000
    snapshot.price.change_24h_pct = 2.5
    snapshot.sentiment.fear_greed_value = 20
    snapshot.sentiment.btc_gold_ratio = 14.0
    snapshot.sentiment.btc_dominance_pct = 57.0
    snapshot.valuation.mvrv_ratio = 1.3
    snapshot.onchain.hash_rate_th = 1e18
    snapshot.onchain.difficulty_change_pct = 10.0
    monitor.get_current_status.return_value = snapshot

    db = MagicMock()
    db.get_price_history.return_value = [
        {"date": "2026-02-01", "price_usd": 68000},
        {"date": "2026-02-08", "price_usd": 70000},
    ]
    db.get_recent_alerts.return_value = []
    db.list_portfolios.return_value = []

    cycle = MagicMock()
    cycle.get_nadeau_signals.return_value = {
        "signals": [],
        "overall_bias": MagicMock(value="BULLISH"),
        "bullish_count": 2,
        "bearish_count": 0,
    }
    cycle.get_halving_info.return_value = {"days_since": 659, "cycle_pct_elapsed": 45.2}

    alert_engine = MagicMock()
    nadeau = MagicMock()

    wd = WeeklyDigest(monitor, cycle, alert_engine, nadeau, db)
    text = wd.format_terminal()
    assert "Weekly Bitcoin Digest" in text
    assert "70,000" in text


# ─── CLI Commands Tests ───

def test_cli_simple_help():
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(cli_module().cli, ["simple", "--help"])
    assert result.exit_code == 0
    assert "Plain English" in result.output


def test_cli_goal_help():
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(cli_module().cli, ["goal", "--help"])
    assert result.exit_code == 0
    assert "goal" in result.output.lower()


def test_cli_digest_help():
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(cli_module().cli, ["digest", "--help"])
    assert result.exit_code == 0
    assert "digest" in result.output.lower()


def test_cli_learn_help():
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(cli_module().cli, ["learn", "--help"])
    assert result.exit_code == 0
    assert "topic" in result.output.lower()


def test_cli_report_couples_help():
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(cli_module().cli, ["report", "--help"])
    assert result.exit_code == 0
    assert "couples" in result.output.lower()


def cli_module():
    """Import the CLI module."""
    import importlib
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    import main as m
    return m
