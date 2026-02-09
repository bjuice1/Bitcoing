"""Tests for interactive Plotly charts and chart data preparation."""
import pytest
from datetime import date, timedelta
import plotly.graph_objects as go
from web.charts import scenario_fan, cycle_overlay, goal_timeline, price_levels, THEME
from web.chart_data import (
    prepare_scenario_fan_data,
    prepare_cycle_overlay_data,
    prepare_goal_timeline_data,
    prepare_price_levels_data,
)


# ─── Fixture helpers ────────────────────────────────────────────

def _mock_projections():
    """Mimics DCAProjector.compare_projections() output."""
    return {
        "bear_60k": {"target_price": 60000, "months": 12, "monthly_dca": 200, "roi_pct": -5},
        "bear_45k": {"target_price": 45000, "months": 18, "monthly_dca": 200, "roi_pct": -15},
        "flat": {"target_price": 85000, "months": 24, "monthly_dca": 200, "roi_pct": 10},
        "bull_100k": {"target_price": 100000, "months": 12, "monthly_dca": 200, "roi_pct": 40},
        "bull_150k": {"target_price": 150000, "months": 24, "monthly_dca": 200, "roi_pct": 80},
        "full_cycle": {
            "at_bottom": {"target_price": 50000, "months": 12},
            "at_top": {"target_price": 200000, "months": 18},
            "total_months": 30,
        },
    }


def _mock_price_history(days=365, start_price=60000, end_price=85000):
    """Generate mock price history."""
    today = date.today()
    step = (end_price - start_price) / max(days - 1, 1)
    return [
        {
            "date": (today - timedelta(days=days - i)).isoformat(),
            "price_usd": start_price + step * i,
        }
        for i in range(days)
    ]


def _mock_goal_projections():
    """Mimics GoalTracker.project_completion() output."""
    return {
        "status": "in_progress",
        "remaining_btc": 0.09,
        "current_btc": 0.01,
        "target_btc": 0.1,
        "monthly_dca": 200,
        "scenarios": {
            "bear": {
                "label": "Bear",
                "price": 51000,
                "months": 8,
                "monthly_btc_path": [0.01 + 0.004 * m for m in range(73)],
            },
            "flat": {
                "label": "Flat",
                "price": 85000,
                "months": 14,
                "monthly_btc_path": [0.01 + 0.0024 * m for m in range(73)],
            },
            "bull": {
                "label": "Bull",
                "price": 170000,
                "months": 28,
                "monthly_btc_path": [0.01 + 0.0012 * m for m in range(73)],
            },
        },
    }


# ─── Chart Data Preparation Tests ───────────────────────────────

class TestPrepareScenarioFan:
    def test_returns_required_keys(self):
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        assert "scenarios" in data
        assert "current_price" in data
        assert "key_levels" in data
        assert "next_halving" in data
        assert "monthly_dca" in data

    def test_scenario_count(self):
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        # 5 named scenarios + full cycle = 6
        assert len(data["scenarios"]) == 6

    def test_scenario_has_dates_and_prices(self):
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        for s in data["scenarios"]:
            assert len(s["dates"]) > 0
            assert len(s["prices"]) > 0
            assert len(s["dates"]) == len(s["prices"])
            assert "name" in s
            assert "color" in s

    def test_key_levels_have_type(self):
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        for kl in data["key_levels"]:
            assert kl["type"] in ("support", "resistance")
            assert "price" in kl

    def test_next_halving_is_future(self):
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        assert data["next_halving"] > date.today()

    def test_custom_config_levels(self):
        config = {"reference_levels": {"support": [50000], "resistance": [120000]}}
        data = prepare_scenario_fan_data(_mock_projections(), 85000, config=config)
        assert len(data["key_levels"]) == 2


class TestPrepareCycleOverlay:
    def test_returns_required_keys(self):
        data = prepare_cycle_overlay_data(_mock_price_history(), 85000)
        assert "cycles" in data
        assert "current_cycle_day" in data
        assert "current_indexed_value" in data

    def test_includes_historical_cycles(self):
        data = prepare_cycle_overlay_data([], 85000)
        # Should always have at least cycles 2 and 3
        names = [c["name"] for c in data["cycles"]]
        assert any("Cycle 2" in n for n in names)
        assert any("Cycle 3" in n for n in names)

    def test_current_cycle_from_price_history(self):
        # Generate price history after halving date (2024-04-20)
        halving = date(2024, 4, 20)
        history = [
            {"date": (halving + timedelta(days=d)).isoformat(), "price_usd": 64000 + d * 50}
            for d in range(100)
        ]
        data = prepare_cycle_overlay_data(history, 85000)
        names = [c["name"] for c in data["cycles"]]
        assert any("Cycle 4" in n for n in names)

    def test_indexed_value_positive(self):
        data = prepare_cycle_overlay_data([], 85000)
        assert data["current_indexed_value"] > 0


class TestPrepareGoalTimeline:
    def test_returns_required_keys(self):
        data = prepare_goal_timeline_data(_mock_goal_projections())
        assert data is not None
        assert "scenarios" in data
        assert "goal_btc" in data
        assert "current_btc" in data
        assert "milestones" in data
        assert "monthly_dca" in data

    def test_scenario_count(self):
        data = prepare_goal_timeline_data(_mock_goal_projections())
        assert len(data["scenarios"]) == 3  # bear, flat, bull

    def test_returns_none_for_complete_goal(self):
        data = prepare_goal_timeline_data({"status": "complete"})
        assert data is None

    def test_returns_none_for_empty(self):
        data = prepare_goal_timeline_data(None)
        assert data is None

    def test_milestones_between_current_and_goal(self):
        data = prepare_goal_timeline_data(_mock_goal_projections())
        for ms in data["milestones"]:
            assert ms["btc"] > data["current_btc"]
            assert ms["btc"] < data["goal_btc"]


class TestPreparePriceLevels:
    def test_returns_required_keys(self):
        data = prepare_price_levels_data(_mock_price_history(), 85000)
        assert "dates" in data
        assert "prices" in data
        assert "key_levels" in data
        assert "cost_bases" in data
        assert "ath_price" in data
        assert "ath_date" in data
        assert "current_price" in data

    def test_ath_is_max(self):
        data = prepare_price_levels_data(_mock_price_history(), 85000)
        assert data["ath_price"] == max(data["prices"])

    def test_returns_none_for_empty_history(self):
        data = prepare_price_levels_data([], 85000)
        assert data is None

    def test_date_conversion(self):
        data = prepare_price_levels_data(_mock_price_history(), 85000)
        assert isinstance(data["dates"][0], date)


# ─── Plotly Chart Generation Tests ──────────────────────────────

class TestScenarioFanChart:
    def test_returns_figure(self):
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        fig = scenario_fan(**data)
        assert isinstance(fig, go.Figure)

    def test_trace_count(self):
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        fig = scenario_fan(**data)
        # 6 scenario traces + 1 today marker = 7
        assert len(fig.data) == 7

    def test_layout_has_title(self):
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        fig = scenario_fan(**data)
        assert "Scenarios" in fig.layout.title.text

    def test_serializable_to_json(self):
        import plotly.io as pio
        data = prepare_scenario_fan_data(_mock_projections(), 85000)
        fig = scenario_fan(**data)
        json_str = pio.to_json(fig)
        assert len(json_str) > 0
        assert '"data"' in json_str


class TestCycleOverlayChart:
    def test_returns_figure(self):
        data = prepare_cycle_overlay_data([], 85000)
        fig = cycle_overlay(**data)
        assert isinstance(fig, go.Figure)

    def test_has_cycle_traces(self):
        data = prepare_cycle_overlay_data([], 85000)
        fig = cycle_overlay(**data)
        # At least cycles 2, 3 + today marker = 3
        assert len(fig.data) >= 3

    def test_log_scale_yaxis(self):
        data = prepare_cycle_overlay_data([], 85000)
        fig = cycle_overlay(**data)
        assert fig.layout.yaxis.type == "log"


class TestGoalTimelineChart:
    def test_returns_figure(self):
        data = prepare_goal_timeline_data(_mock_goal_projections())
        fig = goal_timeline(**data)
        assert isinstance(fig, go.Figure)

    def test_trace_count(self):
        data = prepare_goal_timeline_data(_mock_goal_projections())
        fig = goal_timeline(**data)
        # 3 scenario traces + 1 current BTC marker = 4
        assert len(fig.data) == 4

    def test_has_goal_annotation(self):
        data = prepare_goal_timeline_data(_mock_goal_projections())
        fig = goal_timeline(**data)
        # Check for the bear market annotation
        annotations = [a for a in fig.layout.annotations if "cheaper sats" in (a.text or "")]
        assert len(annotations) == 1


class TestPriceLevelsChart:
    def test_returns_figure(self):
        data = prepare_price_levels_data(_mock_price_history(), 85000)
        fig = price_levels(**data)
        assert isinstance(fig, go.Figure)

    def test_has_price_trace(self):
        data = prepare_price_levels_data(_mock_price_history(), 85000)
        fig = price_levels(**data)
        # At least: price line + ATH marker + current price marker = 3
        assert len(fig.data) >= 3

    def test_has_range_slider(self):
        data = prepare_price_levels_data(_mock_price_history(), 85000)
        fig = price_levels(**data)
        assert fig.layout.xaxis.rangeslider.visible is True

    def test_has_log_toggle(self):
        data = prepare_price_levels_data(_mock_price_history(), 85000)
        fig = price_levels(**data)
        assert len(fig.layout.updatemenus) == 1
        buttons = fig.layout.updatemenus[0].buttons
        labels = [b.label for b in buttons]
        assert "Linear" in labels
        assert "Log" in labels

    def test_serializable_to_json(self):
        import plotly.io as pio
        import json
        data = prepare_price_levels_data(_mock_price_history(), 85000)
        fig = price_levels(**data)
        json_str = pio.to_json(fig)
        parsed = json.loads(json_str)
        assert "data" in parsed
        assert "layout" in parsed
