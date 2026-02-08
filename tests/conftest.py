"""Shared test fixtures."""
import os
import sys
import pytest
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import Database
from models.metrics import PriceMetrics, OnchainMetrics, SentimentMetrics, ValuationMetrics, CombinedSnapshot
from datetime import datetime, timezone


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    db.connect()
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture
def sample_snapshot():
    """Create a realistic test snapshot."""
    return CombinedSnapshot(
        price=PriceMetrics(
            price_usd=67500.0,
            market_cap=1_340_000_000_000.0,
            volume_24h=25_000_000_000.0,
            change_24h_pct=-2.3,
        ),
        onchain=OnchainMetrics(
            hash_rate_th=9.13e17,
            difficulty=1.1e14,
            block_time_avg=605,
            difficulty_change_pct=-3.5,
            supply_circulating=19_800_000,
        ),
        sentiment=SentimentMetrics(
            fear_greed_value=18,
            fear_greed_label="Extreme Fear",
            btc_gold_ratio=22.5,
            btc_dominance_pct=56.7,
        ),
        valuation=ValuationMetrics(
            mvrv_ratio=0.59,
            mvrv_z_score=-0.3,
        ),
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_price_data():
    """Sample daily price records for testing."""
    from datetime import date, timedelta
    records = []
    base_price = 100000
    d = date(2024, 1, 1)
    for i in range(365):
        # Simulate a decline then recovery
        if i < 180:
            price = base_price - (i * 200)
        else:
            price = 64000 + ((i - 180) * 100)
        records.append({
            "date": str(d + timedelta(days=i)),
            "price_usd": price,
            "market_cap": price * 19_500_000,
            "volume": 20_000_000_000,
        })
    return records
