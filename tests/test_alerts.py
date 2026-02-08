"""Tests for alerts engine, rules manager, channels, and Nadeau signals."""
import pytest
import sys
import os
import tempfile
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from models.alerts import AlertRule, AlertRecord, CompositeSignal
from models.metrics import (
    PriceMetrics, OnchainMetrics, SentimentMetrics, ValuationMetrics, CombinedSnapshot,
)
from alerts.engine import AlertEngine
from alerts.rules_manager import RulesManager
from alerts.channels import ConsoleChannel, FileChannel
from alerts.nadeau_signals import NadeauSignalEvaluator


def _make_snapshot(price=67500, fear=18, mvrv=0.59, difficulty_change=-3.5,
                   dominance=56.7, btc_gold=22.5, hash_rate=9.13e17):
    """Create a test snapshot with configurable values."""
    return CombinedSnapshot(
        price=PriceMetrics(price_usd=price, market_cap=price * 19_800_000,
                          volume_24h=25e9, change_24h_pct=-2.3),
        onchain=OnchainMetrics(hash_rate_th=hash_rate, difficulty=1.1e14,
                              block_time_avg=605, difficulty_change_pct=difficulty_change,
                              supply_circulating=19_800_000),
        sentiment=SentimentMetrics(fear_greed_value=fear, fear_greed_label="Extreme Fear",
                                  btc_gold_ratio=btc_gold, btc_dominance_pct=dominance),
        valuation=ValuationMetrics(mvrv_ratio=mvrv, mvrv_z_score=-0.3),
        timestamp=datetime.now(timezone.utc),
    )


class MockRulesManager:
    """Minimal rules manager for testing."""
    def __init__(self, rules=None, composites=None):
        self._rules = rules or []
        self._composites = composites or []

    def get_enabled_rules(self):
        return [r for r in self._rules if r.enabled]

    def get_all_rules(self):
        return self._rules

    def get_composites(self):
        return self._composites


# ── Rule Evaluation ─────────────────────────────────────

def test_rule_triggers(temp_db):
    """Rule should fire when condition met."""
    rule = AlertRule(id="test", name="Price Low", metric="PRICE",
                     operator="<", threshold=60000, severity="WARNING")
    rm = MockRulesManager(rules=[rule])
    engine = AlertEngine(rm, temp_db)

    snapshot = _make_snapshot(price=55000)
    triggered = engine.evaluate_rules(snapshot, ignore_cooldowns=True)
    assert len(triggered) == 1
    assert triggered[0].rule_id == "test"


def test_rule_does_not_trigger(temp_db):
    """Rule should NOT fire when condition not met."""
    rule = AlertRule(id="test", name="Price Low", metric="PRICE",
                     operator="<", threshold=60000, severity="WARNING")
    rm = MockRulesManager(rules=[rule])
    engine = AlertEngine(rm, temp_db)

    snapshot = _make_snapshot(price=65000)
    triggered = engine.evaluate_rules(snapshot, ignore_cooldowns=True)
    assert len(triggered) == 0


def test_all_operators(temp_db):
    """Test each operator type."""
    ops = [("<", 100, 50, True), ("<", 100, 150, False),
           (">", 100, 150, True), (">", 100, 50, False),
           ("<=", 100, 100, True), (">=", 100, 100, True),
           ("==", 100, 100, True), ("!=", 100, 50, True)]

    for op, threshold, price, expected in ops:
        rule = AlertRule(id=f"t_{op}", name="test", metric="PRICE",
                         operator=op, threshold=threshold, severity="INFO")
        rm = MockRulesManager(rules=[rule])
        engine = AlertEngine(rm, temp_db)
        snapshot = _make_snapshot(price=price)
        triggered = engine.evaluate_rules(snapshot, ignore_cooldowns=True)
        assert (len(triggered) > 0) == expected, f"Failed for {op} {threshold} with price {price}"


def test_rule_none_value(temp_db):
    """Rule referencing missing metric should not fire."""
    rule = AlertRule(id="test", name="test", metric="nonexistent_metric",
                     operator="<", threshold=100, severity="INFO")
    rm = MockRulesManager(rules=[rule])
    engine = AlertEngine(rm, temp_db)
    snapshot = _make_snapshot()
    triggered = engine.evaluate_rules(snapshot, ignore_cooldowns=True)
    assert len(triggered) == 0


# ── Composite Signals ──────────────────────────────────

def test_composite_triggers(temp_db):
    """Composite should fire when all required rules fire."""
    rules = [
        AlertRule(id="r1", name="MVRV low", metric="mvrv_ratio", operator="<", threshold=1.0),
        AlertRule(id="r2", name="Fear extreme", metric="fear_greed_value", operator="<", threshold=25),
    ]
    composite = CompositeSignal(id="cap_zone", name="Capitulation",
                                required_rules=["r1", "r2"], severity="CRITICAL",
                                cooldown_seconds=0)
    rm = MockRulesManager(rules=rules, composites=[composite])
    engine = AlertEngine(rm, temp_db)

    snapshot = _make_snapshot(mvrv=0.5, fear=15)
    triggered = engine.evaluate_rules(snapshot, ignore_cooldowns=True)
    composites = engine.evaluate_composites(snapshot, triggered)
    assert len(composites) == 1
    assert composites[0].rule_id == "cap_zone"


def test_composite_does_not_trigger_partial(temp_db):
    """Composite should NOT fire when only some rules fire."""
    rules = [
        AlertRule(id="r1", name="MVRV low", metric="mvrv_ratio", operator="<", threshold=1.0),
        AlertRule(id="r2", name="Fear extreme", metric="fear_greed_value", operator="<", threshold=25),
    ]
    composite = CompositeSignal(id="cap_zone", name="Capitulation",
                                required_rules=["r1", "r2"], severity="CRITICAL",
                                cooldown_seconds=0)
    rm = MockRulesManager(rules=rules, composites=[composite])
    engine = AlertEngine(rm, temp_db)

    snapshot = _make_snapshot(mvrv=0.5, fear=50)  # Only r1 triggers
    triggered = engine.evaluate_rules(snapshot, ignore_cooldowns=True)
    composites = engine.evaluate_composites(snapshot, triggered)
    assert len(composites) == 0


# ── Cooldown ────────────────────────────────────────────

def test_cooldown_suppresses(temp_db):
    """Alert should be suppressed within cooldown window."""
    rule = AlertRule(id="test", name="test", metric="PRICE",
                     operator="<", threshold=70000, cooldown_seconds=9999)
    rm = MockRulesManager(rules=[rule])
    engine = AlertEngine(rm, temp_db)
    snapshot = _make_snapshot(price=60000)

    # First evaluation - should trigger and save
    t1 = engine.evaluate_rules(snapshot, ignore_cooldowns=False)
    assert len(t1) == 1

    # Second evaluation - should be suppressed by cooldown
    t2 = engine.evaluate_rules(snapshot, ignore_cooldowns=False)
    assert len(t2) == 0


# ── test_rules method ──────────────────────────────────

def test_test_rules(temp_db):
    """test_rules should show all rules regardless of cooldown."""
    rules = [
        AlertRule(id="r1", name="Low price", metric="PRICE", operator="<", threshold=70000),
        AlertRule(id="r2", name="High price", metric="PRICE", operator=">", threshold=100000),
    ]
    rm = MockRulesManager(rules=rules)
    engine = AlertEngine(rm, temp_db)
    snapshot = _make_snapshot(price=65000)

    results = engine.test_rules(snapshot)
    assert len(results) == 2
    r1 = next(r for r in results if r["rule_id"] == "r1")
    r2 = next(r for r in results if r["rule_id"] == "r2")
    assert r1["would_fire"] is True
    assert r2["would_fire"] is False


# ── File Channel ────────────────────────────────────────

def test_file_channel():
    """FileChannel should write JSONL."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
        path = f.name

    try:
        channel = FileChannel(log_path=path)
        record = AlertRecord(
            rule_id="test", rule_name="Test",
            metric_value=15.0, threshold=20.0,
            severity="WARNING", message="Test alert",
            triggered_at=datetime.now(timezone.utc),
        )
        channel.send(record)

        with open(path) as f:
            line = f.readline()
            data = json.loads(line)
            assert data["rule_id"] == "test"
            assert data["severity"] == "WARNING"
    finally:
        os.unlink(path)


# ── Format Alert Summary ───────────────────────────────

def test_format_alert_summary_empty(temp_db):
    rm = MockRulesManager()
    engine = AlertEngine(rm, temp_db)
    assert "All clear" in engine.format_alert_summary([])


def test_format_alert_summary_with_alerts(temp_db):
    rm = MockRulesManager()
    engine = AlertEngine(rm, temp_db)
    alerts = [
        AlertRecord(rule_id="r1", rule_name="Test", severity="CRITICAL",
                     message="Something critical"),
    ]
    summary = engine.format_alert_summary(alerts)
    assert "!!!" in summary
    assert "CRITICAL" in summary


# ── Rules Manager YAML loading ─────────────────────────

def test_rules_yaml_loading():
    """Default alerts_rules.yaml should load without errors."""
    rm = RulesManager("config/alerts_rules.yaml")
    rules = rm.get_all_rules()
    assert len(rules) > 0

    composites = rm.get_composites()
    assert len(composites) > 0

    for rule in rules:
        assert rule.id
        assert rule.operator in {"<", ">", "<=", ">=", "==", "!="}
        assert isinstance(rule.threshold, float)


def test_rules_enabled_filter():
    rm = RulesManager("config/alerts_rules.yaml")
    enabled = rm.get_enabled_rules()
    all_rules = rm.get_all_rules()
    assert len(enabled) <= len(all_rules)
    assert all(r.enabled for r in enabled)


# ── Nadeau Signal Evaluator ────────────────────────────

def test_nadeau_capitulation_zone(temp_db, sample_price_data):
    """MVRV<1 + Fear<25 + drawdown>50% → bullish LTH proxy."""
    temp_db.save_price_history(sample_price_data)
    evaluator = NadeauSignalEvaluator(temp_db)
    snapshot = _make_snapshot(mvrv=0.5, fear=10)

    lth = evaluator.evaluate_lth_proxy(snapshot)
    assert lth["signal"].value == "BULLISH"


def test_nadeau_distribution_zone(temp_db, sample_price_data):
    """MVRV>2.5 → bearish LTH proxy."""
    temp_db.save_price_history(sample_price_data)
    evaluator = NadeauSignalEvaluator(temp_db)
    snapshot = _make_snapshot(mvrv=3.5, fear=80)

    lth = evaluator.evaluate_lth_proxy(snapshot)
    assert lth["signal"].value == "BEARISH"


def test_nadeau_cycle_position(temp_db):
    evaluator = NadeauSignalEvaluator(temp_db)
    snapshot = _make_snapshot()
    result = evaluator.evaluate_cycle_position(snapshot)
    assert "days_since_halving" in result
    assert "years_into_cycle" in result
    assert "phase_description" in result


def test_nadeau_reflexivity(temp_db):
    evaluator = NadeauSignalEvaluator(temp_db)
    snapshot = _make_snapshot(fear=10)
    result = evaluator.evaluate_reflexivity_signals(snapshot)
    assert "state" in result
    assert "signal" in result


def test_nadeau_full_assessment(temp_db, sample_price_data):
    """Full assessment should return all components."""
    temp_db.save_price_history(sample_price_data)
    evaluator = NadeauSignalEvaluator(temp_db)
    snapshot = _make_snapshot(mvrv=0.5, fear=10)

    assessment = evaluator.get_full_assessment(snapshot)
    assert "lth_proxy" in assessment
    assert "cycle_position" in assessment
    assert "reflexivity" in assessment
    assert "overall_bias" in assessment
    assert "narrative" in assessment
    assert len(assessment["narrative"]) > 0
