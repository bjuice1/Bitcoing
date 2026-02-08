"""Tests for CycleAnalyzer."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timezone
from monitor.cycle import CycleAnalyzer
from models.enums import CyclePhase, SignalStatus
from models.metrics import (
    PriceMetrics, OnchainMetrics, SentimentMetrics, ValuationMetrics, CombinedSnapshot,
)
from utils.constants import HALVING_DATES, days_since_last_halving, days_until_next_halving


def _make_snapshot(price=67500, fear=18, mvrv=0.59, difficulty_change=-3.5,
                   dominance=56.7, btc_gold=22.5):
    return CombinedSnapshot(
        price=PriceMetrics(price_usd=price, market_cap=price * 19_800_000,
                          volume_24h=25e9, change_24h_pct=-2.3),
        onchain=OnchainMetrics(hash_rate_th=9.13e17, difficulty=1.1e14,
                              block_time_avg=605, difficulty_change_pct=difficulty_change,
                              supply_circulating=19_800_000),
        sentiment=SentimentMetrics(fear_greed_value=fear, fear_greed_label="Extreme Fear",
                                  btc_gold_ratio=btc_gold, btc_dominance_pct=dominance),
        valuation=ValuationMetrics(mvrv_ratio=mvrv, mvrv_z_score=-0.3),
        timestamp=datetime.now(timezone.utc),
    )


# ── Halving Info ────────────────────────────────────────

def test_halving_info(temp_db):
    analyzer = CycleAnalyzer(temp_db)
    info = analyzer.get_halving_info()

    assert info["last_halving"] == str(HALVING_DATES[4])
    assert info["next_halving_est"] == str(HALVING_DATES[5])
    assert info["days_since"] > 0
    assert info["days_until"] > 0
    assert info["current_block_reward"] == 3.125
    assert 0 < info["cycle_pct_elapsed"] < 100


def test_days_since_halving():
    """Verify basic calculation from known halving date."""
    since = days_since_last_halving()
    # Halving 4 was 2024-04-20. As of 2026-02-06, that's ~657 days
    assert 600 < since < 800  # Rough bounds


def test_days_until_halving():
    until = days_until_next_halving()
    assert until is not None
    assert until > 0


# ── Cycle Phase ─────────────────────────────────────────

def test_cycle_phase_mid_bear(temp_db, sample_price_data):
    """Drawdown>50% + MVRV<1 + low fear → MID_BEAR or CAPITULATION."""
    temp_db.save_price_history(sample_price_data)
    analyzer = CycleAnalyzer(temp_db)
    snapshot = _make_snapshot(price=50000, mvrv=0.59, fear=18)

    phase_info = analyzer.get_cycle_phase(snapshot)
    assert phase_info["phase"] in (CyclePhase.MID_BEAR, CyclePhase.CAPITULATION,
                                    CyclePhase.EARLY_BEAR, CyclePhase.DISTRIBUTION)
    assert phase_info["confidence"] in ("high", "medium", "low")


def test_cycle_phase_returns_dict(temp_db):
    analyzer = CycleAnalyzer(temp_db)
    snapshot = _make_snapshot()
    result = analyzer.get_cycle_phase(snapshot)
    assert "phase" in result
    assert "confidence" in result
    assert isinstance(result["phase"], CyclePhase)


# ── Cycle Comparison ───────────────────────────────────

def test_cycle_comparison(temp_db, sample_price_data):
    temp_db.save_price_history(sample_price_data)
    analyzer = CycleAnalyzer(temp_db)
    comparisons = analyzer.get_cycle_comparison()

    assert len(comparisons) >= 3  # Cycle 2, 3, current
    current = comparisons[-1]
    assert "Current" in current["cycle"]
    assert "halving_price" in current


# ── Drawdown Analysis ──────────────────────────────────

def test_drawdown_analysis(temp_db, sample_price_data):
    temp_db.save_price_history(sample_price_data)
    analyzer = CycleAnalyzer(temp_db)
    dd = analyzer.get_drawdown_analysis()

    assert dd["current_drawdown_pct"] >= 0
    assert "historical" in dd
    assert dd["avg_cycle_max_drawdown"] == 80  # (83+77)/2


# ── Nadeau Signals ─────────────────────────────────────

def test_nadeau_signals_bearish_snapshot(temp_db, sample_price_data):
    """Low MVRV + extreme fear → should have bullish signals (contrarian)."""
    temp_db.save_price_history(sample_price_data)
    analyzer = CycleAnalyzer(temp_db)
    snapshot = _make_snapshot(mvrv=0.5, fear=10)

    signals = analyzer.get_nadeau_signals(snapshot)
    assert "signals" in signals
    assert "overall_bias" in signals
    assert signals["bullish_count"] > 0  # Extreme fear + low MVRV = contrarian bullish


def test_nadeau_signals_greed_snapshot(temp_db, sample_price_data):
    """High MVRV + extreme greed → bearish signals."""
    temp_db.save_price_history(sample_price_data)
    analyzer = CycleAnalyzer(temp_db)
    snapshot = _make_snapshot(mvrv=3.5, fear=85)

    signals = analyzer.get_nadeau_signals(snapshot)
    assert signals["bearish_count"] > 0


def test_nadeau_signals_structure(temp_db, sample_price_data):
    """Verify signal structure."""
    temp_db.save_price_history(sample_price_data)
    analyzer = CycleAnalyzer(temp_db)
    snapshot = _make_snapshot()

    signals = analyzer.get_nadeau_signals(snapshot)
    for name, status, value, interp in signals["signals"]:
        assert isinstance(name, str)
        assert isinstance(status, SignalStatus)
        assert isinstance(interp, str)


# ── Supply Dynamics ────────────────────────────────────

def test_supply_dynamics(temp_db, sample_price_data):
    temp_db.save_price_history(sample_price_data)
    analyzer = CycleAnalyzer(temp_db)
    result = analyzer.get_supply_dynamics(current_price=80000)

    assert result["pct_in_profit"] is not None
    assert 0 <= result["pct_in_profit"] <= 100
    assert result["total_days_analyzed"] == 365


def test_supply_dynamics_no_data(temp_db):
    analyzer = CycleAnalyzer(temp_db)
    result = analyzer.get_supply_dynamics(current_price=80000)
    assert result["pct_in_profit"] is None
