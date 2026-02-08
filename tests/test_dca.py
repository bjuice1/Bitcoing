"""Tests for DCA engine, projections, and portfolio tracker."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from dca.engine import DCAEngine
from dca.projections import DCAProjector
from dca.portfolio import PortfolioTracker


def _seed_prices(db, prices_by_date):
    """Helper to seed price_history with specific date-price pairs."""
    records = [
        {"date": d, "price_usd": p, "market_cap": p * 19_500_000, "volume": 1_000_000}
        for d, p in prices_by_date.items()
    ]
    db.save_price_history(records)


# ── DCA Engine ──────────────────────────────────────────

def test_dca_simulate_basic(temp_db):
    """Known prices, verify exact BTC amounts and ROI."""
    _seed_prices(temp_db, {
        "2024-01-01": 100,
        "2024-01-08": 50,
        "2024-01-15": 100,
        "2024-01-22": 150,
        "2024-01-29": 150,  # end price
    })
    engine = DCAEngine(temp_db)
    result = engine.simulate("2024-01-01", "2024-01-29", amount=100, frequency="weekly")

    # 2024-01-01 is a Monday, so buys on: Jan 1, 8, 15, 22, 29 = 5 buys
    assert result.num_buys == 5
    # Buy 1: 100/100=1, Buy 2: 100/50=2, Buy 3: 100/100=1, Buy 4: 100/150≈0.667, Buy 5: 100/150≈0.667
    expected_btc = 1.0 + 2.0 + 1.0 + (100 / 150) + (100 / 150)
    assert abs(result.total_btc - expected_btc) < 0.001
    assert result.total_invested == 500
    # Value at end price ($150): expected_btc * 150
    assert abs(result.current_value - expected_btc * 150) < 0.1
    assert result.roi_pct > 0  # Ended above avg cost


def test_dca_simulate_declining_market(temp_db):
    """DCA into a declining market should show lower avg cost than start."""
    prices = {}
    d = date(2024, 1, 1)
    from datetime import timedelta
    for i in range(31):
        prices[str(d + timedelta(days=i))] = 100 - i  # 100 down to 70
    _seed_prices(temp_db, prices)

    engine = DCAEngine(temp_db)
    result = engine.simulate("2024-01-01", "2024-01-31", amount=100, frequency="daily")
    assert result.avg_cost_basis < 100  # Lower than start price
    assert result.best_buy_price < result.worst_buy_price


def test_dca_buy_date_generation_weekly(temp_db):
    """Weekly buy dates should fall on Mondays."""
    _seed_prices(temp_db, {str(date(2024, 1, 1) + __import__("datetime").timedelta(days=i)): 50000
                           for i in range(35)})
    engine = DCAEngine(temp_db)
    dates = engine._generate_buy_dates(date(2024, 1, 1), date(2024, 2, 1), "weekly")
    assert len(dates) >= 4
    for d in dates:
        assert d.weekday() == 0  # Monday


def test_dca_buy_date_generation_monthly(temp_db):
    """Monthly buys on 1st of month."""
    _seed_prices(temp_db, {str(date(2024, m, 1)): 50000 for m in range(1, 7)})
    engine = DCAEngine(temp_db)
    dates = engine._generate_buy_dates(date(2024, 1, 1), date(2024, 6, 1), "monthly")
    assert len(dates) == 6
    for d in dates:
        assert d.day == 1


def test_dca_no_data_returns_zero_buys(temp_db):
    """With no price data, engine skips all dates and produces 0 buys."""
    engine = DCAEngine(temp_db)
    # Engine generates buy dates but can't find prices, skips them all
    result = engine.simulate("2024-01-01", "2024-01-31", 100, "weekly")
    assert result.num_buys == 0
    assert result.total_invested == 0


def test_dca_single_buy(temp_db):
    """Single buy date should produce valid result."""
    _seed_prices(temp_db, {"2024-01-01": 50000})
    engine = DCAEngine(temp_db)
    result = engine.simulate("2024-01-01", "2024-01-01", 100, "daily")
    assert result.num_buys == 1
    assert abs(result.total_btc - 0.002) < 0.0001


# ── DCA vs Lump Sum ────────────────────────────────────

def test_compare_dca_vs_lumpsum_declining(temp_db):
    """DCA should outperform lump sum in a declining market."""
    prices = {}
    d = date(2024, 1, 1)
    from datetime import timedelta
    for i in range(60):
        prices[str(d + timedelta(days=i))] = 100 - i * 0.5  # decline from 100 to 70
    _seed_prices(temp_db, prices)

    engine = DCAEngine(temp_db)
    comp = engine.compare_to_lumpsum("2024-01-01", "2024-02-28", 1000, "weekly")
    assert comp.dca_advantage_pct > 0  # DCA wins in declining


def test_compare_dca_vs_lumpsum_rising(temp_db):
    """Lump sum should outperform DCA in a rising market."""
    prices = {}
    d = date(2024, 1, 1)
    from datetime import timedelta
    for i in range(60):
        prices[str(d + timedelta(days=i))] = 100 + i * 2  # rise from 100 to 220
    _seed_prices(temp_db, prices)

    engine = DCAEngine(temp_db)
    comp = engine.compare_to_lumpsum("2024-01-01", "2024-02-28", 1000, "weekly")
    assert comp.dca_advantage_pct < 0  # Lump sum wins when rising


# ── Max Drawdown ────────────────────────────────────────

def test_max_drawdown(temp_db):
    """Drawdown should capture the worst underwater moment."""
    # Buy at 100, drops to 50, recovers to 200
    _seed_prices(temp_db, {
        "2024-01-01": 100,
        "2024-01-02": 50,
        "2024-01-03": 200,
    })
    engine = DCAEngine(temp_db)
    result = engine.simulate("2024-01-01", "2024-01-03", 100, "daily")
    assert result.max_drawdown_pct > 0
    # After buying at 100 and 50, when price is 50 the portfolio is underwater
    assert result.max_drawdown_pct < 60  # Rough bound


# ── Projections ─────────────────────────────────────────

def test_projection_bear_scenario():
    """Project DCA through a price decline."""
    proj = DCAProjector(70000, current_btc_held=0, total_invested=0)
    result = proj.project_scenario(50000, 6, 200)

    assert result["months"] == 6
    assert result["total_invested"] == 1200
    assert result["additional_btc"] > 0
    assert result["final_value"] == result["total_btc"] * 50000


def test_projection_bull_scenario():
    """Project DCA through a price rise."""
    proj = DCAProjector(70000)
    result = proj.project_scenario(150000, 12, 200)

    assert result["total_invested"] == 2400
    assert result["roi_pct"] > 0  # Price went up, should be positive


def test_projection_flat():
    """Flat price means all DCA buys at same price."""
    proj = DCAProjector(70000)
    result = proj.project_flat(12, 200)

    assert result["total_invested"] == 2400
    # All bought at ~70K, final value ≈ invested
    assert abs(result["roi_pct"]) < 1  # Roughly break even


def test_projection_bear_then_bull():
    """Full cycle: decline then recovery."""
    proj = DCAProjector(70000)
    result = proj.project_bear_then_bull(40000, 12, 200000, 18, 200)

    assert result["total_months"] == 30
    assert result["total_invested"] > 0
    assert result["final_roi_pct"] > 0  # Ended at 200K, should be very positive


def test_compare_projections():
    """Verify all standard scenarios are generated."""
    proj = DCAProjector(70000)
    scenarios = proj.compare_projections(200)

    assert "bear_60k" in scenarios
    assert "bear_45k" in scenarios
    assert "flat" in scenarios
    assert "bull_100k" in scenarios
    assert "bull_150k" in scenarios
    assert "full_cycle" in scenarios


# ── Portfolio Tracker ───────────────────────────────────

def test_portfolio_create_and_purchase(temp_db):
    """Create a portfolio and record purchases."""
    tracker = PortfolioTracker(temp_db)
    pid = tracker.create_portfolio("Test DCA", "weekly", 100)
    assert pid > 0

    btc = tracker.record_purchase(pid, date(2024, 1, 1), 50000)
    assert abs(btc - 0.002) < 0.0001

    btc2 = tracker.record_purchase(pid, date(2024, 1, 8), 48000)
    assert btc2 > btc  # More BTC at lower price


def test_portfolio_status(temp_db):
    """Portfolio status aggregation."""
    tracker = PortfolioTracker(temp_db)
    pid = tracker.create_portfolio("Main", "weekly", 100)
    tracker.record_purchase(pid, date(2024, 1, 1), 50000, usd_amount=100)
    tracker.record_purchase(pid, date(2024, 1, 8), 40000, usd_amount=100)

    status = tracker.get_portfolio_status(pid, 60000)
    assert status["total_invested"] == 200
    assert status["num_purchases"] == 2
    assert status["total_btc"] > 0
    assert status["current_value"] == status["total_btc"] * 60000
    assert status["roi_pct"] > 0  # Bought at 50K/40K, current 60K


def test_portfolio_not_found(temp_db):
    """Non-existent portfolio returns None."""
    tracker = PortfolioTracker(temp_db)
    assert tracker.get_portfolio_status(999, 50000) is None


def test_portfolio_list(temp_db):
    """List portfolios."""
    tracker = PortfolioTracker(temp_db)
    tracker.create_portfolio("Alpha", "weekly", 50)
    tracker.create_portfolio("Beta", "monthly", 200)

    portfolios = tracker.list_portfolios()
    assert len(portfolios) == 2
    names = {p["name"] for p in portfolios}
    assert "Alpha" in names
    assert "Beta" in names
