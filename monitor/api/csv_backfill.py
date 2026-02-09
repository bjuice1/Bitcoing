"""CSV seed data reader for early Bitcoin price history (2013-2014).

Reads bundled CSV from data/seed_prices.csv to fill the gap before
Yahoo Finance data begins (2014-09-17).
"""
import csv
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger("btcmonitor.csv_backfill")

DEFAULT_CSV_PATH = Path(__file__).parent.parent.parent / "data" / "seed_prices.csv"


class CSVBackfill:
    def __init__(self, csv_path=None):
        self.csv_path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH

    def get_daily_prices(self, start_date: date, end_date: date) -> list[dict]:
        """Read seed CSV filtered to requested date range.

        Returns same format as YFinanceClient:
        [{"date": "YYYY-MM-DD", "price_usd": float, "market_cap": None, "volume": float}]
        """
        if not self.csv_path.exists():
            logger.warning(f"Seed CSV not found: {self.csv_path}")
            return []

        records = []
        try:
            with open(self.csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_date = row["date"]
                    if row_date < str(start_date) or row_date > str(end_date):
                        continue

                    price = float(row["price_usd"])
                    if price <= 0:
                        continue

                    records.append({
                        "date": row_date,
                        "price_usd": price,
                        "market_cap": None,
                        "volume": float(row.get("volume", 0)),
                    })

            logger.info(f"CSV backfill: read {len(records)} records from seed file")
            return records

        except Exception as e:
            logger.warning(f"CSV backfill failed: {e}")
            return []
