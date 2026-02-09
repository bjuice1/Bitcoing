"""Tests for the action engine."""
import pytest
from unittest.mock import MagicMock
from models.metrics import (
    CombinedSnapshot, PriceMetrics, OnchainMetrics,
    SentimentMetrics, ValuationMetrics,
)
from models.enums import SignalStatus


def _snapshot(price=70000, fear=50, mvrv=1.5, change=-2.0, difficulty=5.0, dominance=55.0):
    """Build a snapshot with given values."""
    return CombinedSnapshot(
        price=PriceMetrics(price_usd=price, change_24h_pct=change),
        onchain=OnchainMetrics(difficulty_change_pct=difficulty),
        sentiment=SentimentMetrics(
            fear_greed_value=fear, fear_greed_label="Test",
            btc_dominance_pct=dominance,
        ),
        valuation=ValuationMetrics(mvrv_ratio=mvrv),
    )


def _signals(bias="NEUTRAL", bullish=1, bearish=1):
    """Build a nadeau signals dict.

    Uses the 'overall_bias' path (no 'signals' key) so that
    get_traffic_light reads our bullish/bearish intent correctly.
    """
    bias_enum = {
        "BULLISH": SignalStatus.BULLISH,
        "BEARISH": SignalStatus.BEARISH,
        "NEUTRAL": SignalStatus.NEUTRAL,
    }[bias]
    return {
        "overall_bias": bias_enum,
        "bullish_count": bullish,
        "bearish_count": bearish,
    }


def _make_engine(prices=None):
    """Build an ActionEngine with mocked dependencies."""
    from utils.action_engine import ActionEngine

    db = MagicMock()
    if prices is None:
        # Default: ATH at 126000, current at 70000 → ~44% drawdown
        prices = [
            {"price_usd": 126000, "date": "2025-01-01"},
            {"price_usd": 70000, "date": "2026-02-01"},
        ]
    db.get_price_history.return_value = prices

    cycle = MagicMock()
    cycle.db = db
    monitor = MagicMock()

    return ActionEngine(cycle, monitor)


# ── decision matrix tests ────────────────────────────

def test_stack_hard():
    """GREEN + BULLISH + fear<15 + drawdown>40% → STACK_HARD."""
    engine = _make_engine()
    snap = _snapshot(fear=7, mvrv=0.8)
    signals = _signals("BULLISH", bullish=3, bearish=0)
    rec = engine.get_action(snap, signals)
    assert rec.action == "STACK_HARD"
    assert rec.confidence == "high"


def test_buy_green_bullish():
    """GREEN + BULLISH → BUY."""
    engine = _make_engine()
    snap = _snapshot(fear=30, mvrv=1.0)
    signals = _signals("BULLISH", bullish=3, bearish=0)
    rec = engine.get_action(snap, signals)
    assert rec.action == "BUY"


def test_buy_green_neutral_leaning():
    """GREEN (bullish > bearish) + engine sees NEUTRAL bias → BUY."""
    engine = _make_engine()
    snap = _snapshot(fear=35, mvrv=1.2)
    # Slightly bullish so traffic light goes GREEN (bullish > bearish needed)
    signals = _signals("BULLISH", bullish=2, bearish=1)
    rec = engine.get_action(snap, signals)
    assert rec.action == "BUY"


def test_hold_yellow():
    """YELLOW → HOLD."""
    # YELLOW: fear between 40-75, bias NEUTRAL, moderate MVRV
    engine = _make_engine([
        {"price_usd": 100000, "date": "2025-01-01"},
        {"price_usd": 85000, "date": "2026-02-01"},  # 15% drawdown
    ])
    snap = _snapshot(price=85000, fear=50, mvrv=2.0)
    signals = _signals("NEUTRAL")
    rec = engine.get_action(snap, signals)
    assert rec.action == "HOLD"


def test_take_profit():
    """RED + BEARISH + MVRV>3.5 → TAKE_PROFIT."""
    engine = _make_engine([
        {"price_usd": 130000, "date": "2025-01-01"},
        {"price_usd": 125000, "date": "2026-02-01"},
    ])
    snap = _snapshot(price=125000, fear=85, mvrv=3.8)
    signals = _signals("BEARISH", bullish=0, bearish=3)
    rec = engine.get_action(snap, signals)
    assert rec.action == "TAKE_PROFIT"
    assert rec.confidence == "high"


def test_reduce_red_bearish():
    """RED + BEARISH (MVRV<=3.5) → REDUCE."""
    engine = _make_engine([
        {"price_usd": 130000, "date": "2025-01-01"},
        {"price_usd": 125000, "date": "2026-02-01"},
    ])
    snap = _snapshot(price=125000, fear=80, mvrv=2.8)
    signals = _signals("BEARISH", bullish=0, bearish=3)
    rec = engine.get_action(snap, signals)
    assert rec.action == "REDUCE"


def test_hold_red_neutral():
    """RED + NEUTRAL → HOLD."""
    engine = _make_engine([
        {"price_usd": 130000, "date": "2025-01-01"},
        {"price_usd": 125000, "date": "2026-02-01"},
    ])
    snap = _snapshot(price=125000, fear=80, mvrv=3.2)
    signals = _signals("NEUTRAL")
    rec = engine.get_action(snap, signals)
    assert rec.action == "HOLD"


# ── formatter tests ──────────────────────────────────

def test_format_terminal_has_emoji():
    engine = _make_engine()
    snap = _snapshot(fear=7, mvrv=0.8)
    signals = _signals("BULLISH", bullish=3, bearish=0)
    rec = engine.get_action(snap, signals)
    output = engine.format_terminal(rec)
    assert rec.emoji in output
    assert "STACK_HARD" in output


def test_format_plain_no_rich():
    engine = _make_engine()
    snap = _snapshot(fear=50, mvrv=1.5)
    signals = _signals("NEUTRAL")
    rec = engine.get_action(snap, signals)
    output = engine.format_plain(rec)
    assert "[" not in output  # No Rich markup
    assert rec.action in output


def test_format_markdown():
    engine = _make_engine()
    snap = _snapshot(fear=50, mvrv=1.5)
    signals = _signals("NEUTRAL")
    rec = engine.get_action(snap, signals)
    output = engine.format_markdown(rec)
    assert "*" in output  # Has Markdown bold
    assert rec.action in output


def test_to_dict():
    engine = _make_engine()
    snap = _snapshot(fear=7, mvrv=0.8)
    signals = _signals("BULLISH", bullish=3, bearish=0)
    rec = engine.get_action(snap, signals)
    d = rec.to_dict()
    assert d["action"] == "STACK_HARD"
    assert isinstance(d["fear_greed"], int)
    assert isinstance(d["drawdown_pct"], float)


def test_no_price_history():
    """Empty price history → 0% drawdown → still works."""
    engine = _make_engine(prices=[])
    snap = _snapshot(fear=50, mvrv=1.5)
    signals = _signals("NEUTRAL")
    rec = engine.get_action(snap, signals)
    assert rec.action in ("BUY", "HOLD")


def test_cli_action_help():
    from click.testing import CliRunner
    import main as m
    runner = CliRunner()
    result = runner.invoke(m.cli, ["action", "--help"])
    assert result.exit_code == 0
    assert "action" in result.output.lower() or "signal" in result.output.lower()
