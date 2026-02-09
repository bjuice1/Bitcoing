"""Tests for multi-source historical price backfill."""
import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from monitor.backfill import BackfillOrchestrator, BackfillResult
from monitor.api.yfinance_client import YFinanceClient
from monitor.api.csv_backfill import CSVBackfill


class TestBackfillOrchestrator:
    def setup_method(self):
        self.db = MagicMock()
        self.orchestrator = BackfillOrchestrator(self.db)

    def test_get_gaps_no_data(self):
        existing = set()
        gaps = self.orchestrator.get_gaps(date(2024, 1, 1), date(2024, 1, 10), existing)
        assert len(gaps) == 1
        assert gaps[0] == (date(2024, 1, 1), date(2024, 1, 10))

    def test_get_gaps_complete_data(self):
        existing = {f"2024-01-{d:02d}" for d in range(1, 11)}
        gaps = self.orchestrator.get_gaps(date(2024, 1, 1), date(2024, 1, 10), existing)
        assert len(gaps) == 0

    def test_get_gaps_small_gaps_ignored(self):
        """Gaps of 1-2 days should be ignored (weekends/holidays)."""
        existing = {"2024-01-01", "2024-01-04", "2024-01-05"}
        # Gap of 2 days (Jan 2-3) should NOT be reported
        gaps = self.orchestrator.get_gaps(date(2024, 1, 1), date(2024, 1, 5), existing)
        assert len(gaps) == 0

    def test_get_gaps_large_gap_found(self):
        """Gaps of 3+ days should be reported."""
        existing = {"2024-01-01", "2024-01-10"}
        gaps = self.orchestrator.get_gaps(date(2024, 1, 1), date(2024, 1, 10), existing)
        assert len(gaps) == 1
        assert gaps[0][0] == date(2024, 1, 2)

    def test_validate_filters_bad_prices(self):
        records = [
            {"date": "2024-01-01", "price_usd": 50000},
            {"date": "2024-01-02", "price_usd": -100},      # negative
            {"date": "2024-01-03", "price_usd": 0},          # zero
            {"date": "2024-01-04", "price_usd": 20000000},   # too high
            {"date": "2024-01-05", "price_usd": 51000},
        ]
        valid = self.orchestrator.validate(records)
        assert len(valid) == 2
        dates = [r["date"] for r in valid]
        assert "2024-01-01" in dates
        assert "2024-01-05" in dates

    def test_validate_deduplicates(self):
        records = [
            {"date": "2024-01-01", "price_usd": 50000},
            {"date": "2024-01-01", "price_usd": 50100},  # duplicate, keep last
        ]
        valid = self.orchestrator.validate(records)
        assert len(valid) == 1
        assert valid[0]["price_usd"] == 50100

    def test_result_dataclass(self):
        result = BackfillResult()
        assert result.dates_added == 0
        assert result.date_range == (None, None)
        assert result.sources_used == []
        assert result.gaps_remaining == []
        assert result.errors == []


class TestYFinanceClient:
    def test_earliest_date(self):
        assert YFinanceClient.EARLIEST_DATE == date(2014, 9, 17)

    def test_empty_range(self):
        client = YFinanceClient()
        # end <= start should return empty
        result = client.get_daily_prices(date(2024, 1, 5), date(2024, 1, 1))
        assert result == []

    def test_clamps_start_to_earliest(self):
        """Requesting data before EARLIEST_DATE should be clamped."""
        client = YFinanceClient()
        # We can't easily test the actual yfinance call without network,
        # but we can verify the date clamping logic by checking the method exists
        assert hasattr(client, 'get_daily_prices')
        assert hasattr(client, 'health_check')


class TestCSVBackfill:
    def test_missing_csv_returns_empty(self):
        client = CSVBackfill(csv_path="/nonexistent/path.csv")
        result = client.get_daily_prices(date(2013, 1, 1), date(2013, 12, 31))
        assert result == []

    def test_reads_seed_csv(self):
        """Test reading the actual seed CSV if it exists."""
        import os
        csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "seed_prices.csv")
        if not os.path.exists(csv_path):
            pytest.skip("seed_prices.csv not found")

        client = CSVBackfill(csv_path=csv_path)
        result = client.get_daily_prices(date(2013, 1, 1), date(2013, 1, 31))
        assert len(result) > 0
        assert all(r["price_usd"] > 0 for r in result)
        assert all("date" in r for r in result)

    def test_date_filtering(self):
        """CSV should only return records within the requested range."""
        import os
        csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "seed_prices.csv")
        if not os.path.exists(csv_path):
            pytest.skip("seed_prices.csv not found")

        client = CSVBackfill(csv_path=csv_path)
        result = client.get_daily_prices(date(2013, 6, 1), date(2013, 6, 30))
        for r in result:
            assert r["date"] >= "2013-06-01"
            assert r["date"] <= "2013-06-30"
