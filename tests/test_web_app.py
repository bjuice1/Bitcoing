"""Tests for Flask web dashboard."""
import pytest
from unittest.mock import MagicMock, patch
from web.app import create_app


def _mock_snapshot():
    """Create a mock snapshot object."""
    snap = MagicMock()
    snap.price.price_usd = 85000
    snap.price.change_24h_pct = 2.5
    snap.price.market_cap = 1700000000000
    snap.sentiment.fear_greed_value = 45
    snap.sentiment.fear_greed_label = "Fear"
    snap.sentiment.btc_dominance_pct = 60.5
    snap.sentiment.btc_gold_ratio = 35.2
    snap.valuation.mvrv_ratio = 1.8
    snap.onchain.hash_rate_th = 750e6
    return snap


def _mock_engines():
    """Create mock engine objects for Flask app."""
    monitor = MagicMock()
    monitor.get_current_status.return_value = _mock_snapshot()

    cycle = MagicMock()
    cycle.get_halving_info.return_value = {
        "days_since": 295,
        "cycle_pct_elapsed": 20.2,
        "last_halving": "2024-04-20",
        "next_halving_est": "2028-04-17",
        "days_until": 1165,
        "current_block_reward": 3.125,
        "next_block_reward": 1.5625,
        "halving_era": 4,
    }
    cycle.get_cycle_phase.return_value = {"phase": "Post-Halving", "confidence": "HIGH"}
    cycle.get_drawdown_analysis.return_value = {
        "current_drawdown_pct": 8.5,
        "avg_cycle_max_drawdown": 80,
        "vs_average": "Below historical average (80%)",
        "days_since_halving": 295,
    }
    cycle.get_nadeau_signals.return_value = {
        "signals": [],
        "overall_bias": "NEUTRAL",
        "bullish_count": 2,
        "bearish_count": 1,
    }

    alert_engine = MagicMock()
    db = MagicMock()
    db.get_recent_alerts.return_value = []
    db.get_price_history.return_value = [
        {"date": "2024-01-01", "price_usd": 42000},
        {"date": "2024-06-01", "price_usd": 68000},
        {"date": "2025-01-01", "price_usd": 85000},
    ]

    nadeau = MagicMock()
    action_engine = MagicMock()
    rec = MagicMock()
    rec.action = "HOLD"
    rec.headline = "Market is neutral."
    rec.plain_english = "Conditions are stable. Keep your regular DCA going."
    rec.traffic_light = "YELLOW"
    rec.confidence = "medium"
    rec.nadeau_bias = "NEUTRAL"
    rec.fear_greed = 45
    rec.drawdown_pct = 8.5
    rec.mvrv = 1.8
    action_engine.get_action.return_value = rec

    dca_portfolio = MagicMock()
    dca_portfolio.list_portfolios.return_value = []

    goal_tracker = MagicMock()
    goal_tracker.get_progress.return_value = None
    goal_tracker.project_completion.return_value = None

    return {
        "monitor": monitor,
        "cycle": cycle,
        "alert_engine": alert_engine,
        "nadeau": nadeau,
        "action_engine": action_engine,
        "db": db,
        "dca_portfolio": dca_portfolio,
        "goal_tracker": goal_tracker,
    }


@pytest.fixture
def app():
    config = {
        "dca": {"default_amount": 200},
        "reference_levels": {
            "support": [70000, 75000],
            "resistance": [100000],
            "cost_bases": {"MicroStrategy": 76000},
        },
    }
    engines = _mock_engines()
    app = create_app(config, engines)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestDashboardRoutes:
    def test_dashboard_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_dashboard_has_bitcoin(self, client):
        resp = client.get("/")
        assert b"Bitcoin" in resp.data

    def test_partner_200(self, client):
        resp = client.get("/partner")
        assert resp.status_code == 200

    def test_partner_has_strategy(self, client):
        resp = client.get("/partner")
        assert b"Strategy" in resp.data


class TestAPIEndpoints:
    def test_api_snapshot_200(self, client):
        resp = client.get("/api/snapshot")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "price" in data
        assert "signal" in data
        assert "fear_greed" in data
        assert "timestamp" in data

    def test_api_snapshot_price(self, client):
        resp = client.get("/api/snapshot")
        data = resp.get_json()
        assert data["price"]["usd"] == 85000

    def test_api_history_200(self, client):
        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "dates" in data
        assert "prices" in data
        assert "count" in data

    def test_api_history_with_days(self, client):
        resp = client.get("/api/history?days=30")
        assert resp.status_code == 200

    def test_api_alerts_200(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "alerts" in data
        assert "count" in data

    def test_api_chart_unknown_404(self, client):
        resp = client.get("/api/chart/nonexistent")
        assert resp.status_code == 404

    def test_api_chart_scenario_fan(self, client):
        resp = client.get("/api/chart/scenario_fan")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        assert "layout" in data

    def test_api_chart_goal_timeline_no_goal(self, client):
        resp = client.get("/api/chart/goal_timeline")
        assert resp.status_code == 404


class TestTemplateFilters:
    def test_format_usd_large(self, app):
        with app.app_context():
            f = app.jinja_env.filters["format_usd"]
            assert f(1_500_000_000) == "1.5B"
            assert f(2_500_000) == "2.5M"
            assert f(85000) == "85,000"
            assert f(0.5) == "0.50"

    def test_format_pct(self, app):
        with app.app_context():
            f = app.jinja_env.filters["format_pct"]
            assert f(2.5) == "+2.5%"
            assert f(-3.1) == "-3.1%"

    def test_format_btc(self, app):
        with app.app_context():
            f = app.jinja_env.filters["format_btc"]
            assert f(0.00123456) == "0.00123456"

    def test_format_sats(self, app):
        with app.app_context():
            f = app.jinja_env.filters["format_sats"]
            assert f(1234567) == "1,234,567"

    def test_time_ago(self, app):
        with app.app_context():
            f = app.jinja_env.filters["time_ago"]
            assert f("invalid") == "invalid"
