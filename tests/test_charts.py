"""Tests for new visual timeline charts."""
import pytest
import os
import tempfile
from datetime import date, datetime


def _make_chart_gen():
    """Create a DCAChartGenerator with temp output dir."""
    from dca.charts import DCAChartGenerator
    tmpdir = tempfile.mkdtemp()
    return DCAChartGenerator(output_dir=tmpdir), tmpdir


def test_generate_price_path():
    gen, _ = _make_chart_gen()
    path = gen._generate_price_path(70000, 100000, 12)
    assert len(path) == 13  # 0 to 12 inclusive
    assert path[0] == 70000
    assert abs(path[-1] - 100000) < 1


def test_generate_price_path_zero_months():
    gen, _ = _make_chart_gen()
    path = gen._generate_price_path(70000, 100000, 0)
    assert len(path) == 1
    assert path[0] == 70000


def test_scenario_fan_generates_png():
    gen, tmpdir = _make_chart_gen()
    from dca.projections import DCAProjector
    proj = DCAProjector(70000)
    projections = proj.compare_projections(200)
    key_levels = [60000, 85000, 100000]
    next_halving = date(2028, 4, 17)

    path = gen.plot_scenario_fan(70000, projections, 200, key_levels, next_halving)
    assert path is not None
    assert os.path.exists(path)
    assert path.endswith(".png")
    assert os.path.getsize(path) > 1000  # Non-trivial PNG


def test_scenario_fan_no_key_levels():
    gen, tmpdir = _make_chart_gen()
    from dca.projections import DCAProjector
    proj = DCAProjector(70000)
    projections = proj.compare_projections(200)

    path = gen.plot_scenario_fan(70000, projections, 200)
    assert path is not None
    assert os.path.exists(path)


def test_cycle_overlay_generates_png():
    gen, tmpdir = _make_chart_gen()

    # Simulate price history
    price_history = []
    base_date = date(2024, 4, 20)  # Halving date
    for i in range(0, 365, 7):
        d = date.fromordinal(base_date.toordinal() + i)
        price_history.append({
            "date": d.strftime("%Y-%m-%d"),
            "price_usd": 63963 + i * 20,  # Gradual climb
        })

    halving_info = {"days_since": 659, "cycle_pct_elapsed": 45.2}

    path = gen.plot_cycle_overlay(price_history, halving_info, 70585)
    assert path is not None
    assert os.path.exists(path)
    assert path.endswith(".png")
    assert os.path.getsize(path) > 1000


def test_cycle_overlay_no_history():
    gen, tmpdir = _make_chart_gen()
    halving_info = {"days_since": 659, "cycle_pct_elapsed": 45.2}

    # Should still work with minimal path
    path = gen.plot_cycle_overlay([], halving_info, 70585)
    assert path is not None
    assert os.path.exists(path)


def test_goal_timeline_generates_png():
    gen, tmpdir = _make_chart_gen()

    goal_projections = {
        "status": "in_progress",
        "target_btc": 0.1,
        "current_btc": 0.02,
        "monthly_dca": 200,
        "scenarios": {
            "bear": {
                "label": "Bear (price -40%)",
                "price": 42000,
                "months": 17,
                "monthly_btc_path": [0.02 + (200 / 42000) * m for m in range(18)],
            },
            "flat": {
                "label": "Flat (price unchanged)",
                "price": 70000,
                "months": 28,
                "monthly_btc_path": [0.02 + (200 / 70000) * m for m in range(29)],
            },
            "bull": {
                "label": "Bull (price 2x)",
                "price": 140000,
                "months": 56,
                "monthly_btc_path": [0.02 + (200 / 140000) * m for m in range(57)],
            },
        },
    }

    path = gen.plot_goal_timeline(goal_projections)
    assert path is not None
    assert os.path.exists(path)
    assert path.endswith(".png")
    assert os.path.getsize(path) > 1000


def test_goal_timeline_complete_returns_none():
    gen, tmpdir = _make_chart_gen()
    path = gen.plot_goal_timeline({"status": "complete"})
    assert path is None


def test_goal_timeline_none_returns_none():
    gen, tmpdir = _make_chart_gen()
    path = gen.plot_goal_timeline(None)
    assert path is None


def test_price_with_levels_generates_png():
    gen, tmpdir = _make_chart_gen()

    price_history = []
    for i in range(365):
        d = date(2025, 3, 1).toordinal() + i
        d = date.fromordinal(d)
        # Simulate price movements
        price = 65000 + (i * 30) + ((-1) ** i * 500)
        price_history.append({"date": d.strftime("%Y-%m-%d"), "price_usd": price})

    key_levels = [60000, 65000, 70000, 85000, 100000]
    cost_bases = {"MicroStrategy": 76000}

    path = gen.plot_price_with_levels(price_history, 70585, key_levels, cost_bases)
    assert path is not None
    assert os.path.exists(path)
    assert path.endswith(".png")
    assert os.path.getsize(path) > 1000


def test_price_with_levels_no_history():
    gen, tmpdir = _make_chart_gen()
    path = gen.plot_price_with_levels([], 70000)
    assert path is None


def test_price_with_levels_no_extras():
    gen, tmpdir = _make_chart_gen()
    price_history = [
        {"date": "2025-06-01", "price_usd": 68000},
        {"date": "2025-07-01", "price_usd": 70000},
        {"date": "2025-08-01", "price_usd": 72000},
    ]
    path = gen.plot_price_with_levels(price_history, 72000)
    assert path is not None
    assert os.path.exists(path)


def test_cli_charts_help():
    from click.testing import CliRunner
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    import main as m
    runner = CliRunner()
    result = runner.invoke(m.cli, ["charts", "--help"])
    assert result.exit_code == 0
    assert "scenario fan" in result.output.lower() or "fan" in result.output.lower()
    assert "cycle" in result.output.lower()
    assert "goal" in result.output.lower()
    assert "levels" in result.output.lower()
