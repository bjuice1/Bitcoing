"""Tests for the database module."""
import pytest
from datetime import datetime, timezone


def test_table_creation(temp_db):
    """Verify all tables exist after init."""
    tables = temp_db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {t["name"] for t in tables}
    assert "metrics_snapshots" in names
    assert "price_history" in names
    assert "alert_history" in names
    assert "dca_portfolios" in names
    assert "dca_purchases" in names


def test_save_and_retrieve_snapshot(temp_db, sample_snapshot):
    temp_db.save_snapshot(sample_snapshot)
    latest = temp_db.get_latest_snapshot()
    assert latest is not None
    assert latest.price.price_usd == 67500.0
    assert latest.sentiment.fear_greed_value == 18
    assert latest.valuation.mvrv_ratio == 0.59


def test_empty_db_returns_none(temp_db):
    assert temp_db.get_latest_snapshot() is None
    assert temp_db.get_price_history() == []
    assert temp_db.get_recent_alerts() == []


def test_price_history_bulk_insert(temp_db, sample_price_data):
    temp_db.save_price_history(sample_price_data)
    count = temp_db.get_price_history_count()
    assert count == 365
    history = temp_db.get_price_history()
    assert len(history) == 365
    assert history[0]["date"] == "2024-01-01"


def test_price_history_dedup(temp_db, sample_price_data):
    temp_db.save_price_history(sample_price_data)
    temp_db.save_price_history(sample_price_data)  # Insert again
    assert temp_db.get_price_history_count() == 365  # No duplicates


def test_price_for_date(temp_db, sample_price_data):
    temp_db.save_price_history(sample_price_data)
    record = temp_db.get_price_for_date("2024-06-15")
    assert record is not None
    assert record["price_usd"] > 0


def test_price_for_date_nearest(temp_db):
    temp_db.save_price_history([
        {"date": "2024-01-01", "price_usd": 100, "market_cap": 0, "volume": 0},
        {"date": "2024-01-03", "price_usd": 200, "market_cap": 0, "volume": 0},
    ])
    # Jan 2 should fall back to Jan 1
    record = temp_db.get_price_for_date("2024-01-02")
    assert record["price_usd"] == 100


def test_dca_portfolio_crud(temp_db):
    pid = temp_db.create_portfolio("Test", "2024-01-01", "weekly", 100)
    assert pid > 0
    temp_db.add_purchase(pid, "2024-01-01", 50000, 0.002, 100)
    temp_db.add_purchase(pid, "2024-01-08", 48000, 0.00208, 100)

    port = temp_db.get_portfolio(pid)
    assert port["name"] == "Test"
    assert len(port["purchases"]) == 2

    portfolios = temp_db.list_portfolios()
    assert len(portfolios) == 1
    assert portfolios[0]["num_purchases"] == 2


def test_alert_save_and_query(temp_db):
    from models.alerts import AlertRecord
    record = AlertRecord(
        rule_id="test_rule",
        rule_name="Test",
        metric_value=15.0,
        threshold=20.0,
        severity="WARNING",
        message="Test alert",
        triggered_at=datetime.now(timezone.utc),
    )
    temp_db.save_alert(record)
    alerts = temp_db.get_recent_alerts()
    assert len(alerts) == 1
    assert alerts[0]["rule_id"] == "test_rule"

    last = temp_db.get_last_alert_time("test_rule")
    assert last is not None
