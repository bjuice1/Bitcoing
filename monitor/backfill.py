"""Multi-source historical price backfill.

Priority order:
  1. CoinGecko (last 365 days, already in DB from routine fetches)
  2. yfinance (BTC-USD ticker, 2014-09-17 onward)
  3. Bundled CSV fallback (data/seed_prices.csv, 2013-01 to 2014-09)

Usage:
  orchestrator = BackfillOrchestrator(db, config)
  result = orchestrator.run(start_year=2013, progress_callback=fn)
"""
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger("btcmonitor.backfill")


@dataclass
class BackfillResult:
    dates_added: int = 0
    date_range: tuple = (None, None)
    sources_used: list = field(default_factory=list)
    gaps_remaining: list = field(default_factory=list)
    errors: list = field(default_factory=list)


class BackfillOrchestrator:
    def __init__(self, db, config=None):
        self.db = db
        self.config = config or {}

    def get_existing_dates(self) -> set[str]:
        """Return set of all dates already in price_history."""
        rows = self.db.get_price_history()
        return {r["date"] for r in rows}

    def get_gaps(self, start_date: date, end_date: date, existing: set[str]) -> list[tuple[date, date]]:
        """Find date ranges with missing data.

        Only flags gaps of 3+ consecutive missing days (weekends/holidays
        may have no trading data and that's normal).
        """
        gaps = []
        gap_start = None
        gap_len = 0
        current = start_date

        while current <= end_date:
            date_str = current.isoformat()
            if date_str not in existing:
                if gap_start is None:
                    gap_start = current
                gap_len += 1
            else:
                if gap_start and gap_len >= 3:
                    gaps.append((gap_start, current - timedelta(days=1)))
                gap_start = None
                gap_len = 0
            current += timedelta(days=1)

        # Handle trailing gap
        if gap_start and gap_len >= 3:
            gaps.append((gap_start, end_date))

        return gaps

    def validate(self, records: list[dict]) -> list[dict]:
        """Validate fetched price records.

        Rules:
          - price_usd must be > 0
          - price_usd must be < 10,000,000 (sanity cap)
          - No duplicate dates (keep last)
          - Date must be a valid string
        """
        seen = {}
        for r in records:
            price = r.get("price_usd", 0)
            if price <= 0 or price >= 10_000_000:
                logger.warning(f"Skipping invalid price: {r.get('date')} = ${price}")
                continue
            if not r.get("date"):
                continue
            seen[r["date"]] = r

        return list(seen.values())

    def run(self, start_year: int = 2013, progress_callback=None) -> BackfillResult:
        """Main backfill entry point.

        Fetches from multiple sources to fill gaps in price_history.
        """
        result = BackfillResult()
        target_start = date(start_year, 1, 1)
        target_end = date.today()
        total_days = (target_end - target_start).days

        existing = self.get_existing_dates()
        initial_count = len(existing)
        logger.info(f"Existing price records: {initial_count}")

        gaps = self.get_gaps(target_start, target_end, existing)
        if not gaps:
            logger.info("No gaps found — price history is complete")
            date_range = self.db.get_price_date_range()
            result.date_range = (date_range["min_date"], date_range["max_date"])
            return result

        logger.info(f"Found {len(gaps)} gaps to fill")
        dates_added = 0

        # Source 1: CoinGecko (recent 365 days — likely already in DB)
        # We don't re-fetch from CoinGecko here since routine fetches handle it.
        # The BackfillOrchestrator focuses on older data.

        # Source 2: yfinance (2014-09-17 onward)
        try:
            from monitor.api.yfinance_client import YFinanceClient
            yf_client = YFinanceClient()

            for gap_start, gap_end in gaps:
                if gap_end < YFinanceClient.EARLIEST_DATE:
                    continue  # Too old for yfinance, CSV will handle it

                fetch_start = max(gap_start, YFinanceClient.EARLIEST_DATE)
                logger.info(f"yfinance: fetching {fetch_start} to {gap_end}")

                records = yf_client.get_daily_prices(fetch_start, gap_end)
                if records:
                    valid = self.validate(records)
                    if valid:
                        self.db.save_price_history(valid)
                        dates_added += len(valid)
                        existing.update(r["date"] for r in valid)
                        if "yfinance" not in result.sources_used:
                            result.sources_used.append("yfinance")

                if progress_callback:
                    progress_callback(dates_added, total_days)

        except Exception as e:
            err = f"yfinance backfill failed: {e}"
            logger.warning(err)
            result.errors.append(err)

        # Source 3: CSV seed data (2013-01 to 2014-09)
        try:
            from monitor.api.csv_backfill import CSVBackfill
            csv_client = CSVBackfill()

            for gap_start, gap_end in gaps:
                if gap_start >= YFinanceClient.EARLIEST_DATE:
                    continue  # Already handled by yfinance

                csv_end = min(gap_end, YFinanceClient.EARLIEST_DATE - timedelta(days=1))
                logger.info(f"CSV: reading {gap_start} to {csv_end}")

                records = csv_client.get_daily_prices(gap_start, csv_end)
                if records:
                    # Only save records we don't already have
                    new_records = [r for r in records if r["date"] not in existing]
                    valid = self.validate(new_records)
                    if valid:
                        self.db.save_price_history(valid)
                        dates_added += len(valid)
                        existing.update(r["date"] for r in valid)
                        if "csv" not in result.sources_used:
                            result.sources_used.append("csv")

                if progress_callback:
                    progress_callback(dates_added, total_days)

        except Exception as e:
            err = f"CSV backfill failed: {e}"
            logger.warning(err)
            result.errors.append(err)

        # Re-check for remaining gaps
        existing = self.get_existing_dates()
        remaining_gaps = self.get_gaps(target_start, target_end, existing)

        date_range = self.db.get_price_date_range()
        result.dates_added = dates_added
        result.date_range = (date_range["min_date"], date_range["max_date"])
        result.gaps_remaining = [(str(s), str(e)) for s, e in remaining_gaps]

        logger.info(f"Backfill complete: {dates_added} records added. "
                    f"Range: {result.date_range[0]} to {result.date_range[1]}. "
                    f"Gaps remaining: {len(remaining_gaps)}")

        return result
