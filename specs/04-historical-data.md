# 04 — Full-Cycle Historical Data Backfill

## Overview

The Bitcoin Cycle Monitor currently has a hard 365-day limit on price history due to the CoinGecko free tier API constraint. This makes full-cycle analysis (4-year halving cycles) impossible — the cycle overlay chart, long-range DCA backtests, and drawdown comparisons all need daily prices from at least 2013 onward.

This document specifies a multi-source backfill strategy that fills the `price_history` table with daily BTC/USD prices from January 2013 to present, using only free APIs and no API keys.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Backfill Orchestrator               │
│              (monitor/backfill.py — NEW)             │
│                                                      │
│  1. Check existing data in price_history table       │
│  2. Identify date gaps                               │
│  3. Fetch from sources in priority order             │
│  4. Validate + deduplicate                           │
│  5. Store to SQLite                                  │
│                                                      │
│  Sources (priority order):                           │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  CoinGecko   │  │   yfinance   │  │  Bundled   │  │
│  │  (chunked)   │  │  (BTC-USD)   │  │   CSV      │  │
│  │  365d/req    │  │  2014-present│  │  fallback  │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
│         └─────────────┬────┘───────────────┘         │
│                       ▼                              │
│              price_history table                     │
│         (date UNIQUE, price_usd, volume)             │
└─────────────────────────────────────────────────────┘
```

**Downstream consumers:**
- `06-interactive-charts.md` — Plotly charts need multi-year data for cycle overlay and price-with-levels
- `05-web-dashboard.md` — Web dashboard displays historical charts
- `dca/engine.py` — DCA backtests over full cycles (e.g., "what if I DCA'd from the 2018 bear?")
- `monitor/cycle.py` — Cycle comparison (Cycle 2 vs 3 vs 4) needs real price data, not just constants

## Specification

### 1. New Module: `monitor/backfill.py`

```python
"""
Multi-source historical price backfill.

Priority order:
  1. CoinGecko (chunked 365-day requests, rate-limited)
  2. yfinance (BTC-USD ticker, 2014-09-17 onward)
  3. Bundled CSV fallback (data/seed_prices.csv)

Usage:
  orchestrator = BackfillOrchestrator(db, config)
  result = orchestrator.run(start_year=2013, progress_callback=fn)
"""

class BackfillOrchestrator:
    def __init__(self, db: Database, config: dict):
        self.db = db
        self.config = config
        self.sources = [
            CoinGeckoBackfill(config),
            YFinanceBackfill(),
            CSVBackfill(),
        ]

    def get_gaps(self, start_date: date, end_date: date) -> list[tuple[date, date]]:
        """
        Query price_history for existing dates between start_date and end_date.
        Return list of (gap_start, gap_end) tuples where data is missing.
        A gap is any run of 2+ consecutive missing calendar days.
        Weekends/holidays may have missing data — only flag gaps of 3+ days.
        """

    def run(self, start_year: int = 2013, progress_callback=None) -> BackfillResult:
        """
        Main entry point. Returns BackfillResult with:
          - dates_added: int
          - date_range: (min_date, max_date)
          - sources_used: list[str]
          - gaps_remaining: list[tuple[date, date]]
          - errors: list[str]

        Algorithm:
          1. Calculate target range: Jan 1 start_year → today
          2. Call get_gaps() to find missing date ranges
          3. For each gap, try sources in priority order:
             a. CoinGecko chunked (if gap is recent, <2 years old)
             b. yfinance (primary source for older data)
             c. CSV fallback (if both APIs fail)
          4. Validate fetched prices (see validation rules below)
          5. Store via db.save_price_history()
          6. Call progress_callback(dates_added_so_far, total_dates_needed)
        """

    def validate(self, records: list[dict]) -> list[dict]:
        """
        Validation rules:
          - price_usd must be > 0
          - price_usd must be < 10,000,000 (sanity cap)
          - No duplicate dates
          - Date must be a valid calendar date
          - If adjacent days exist, price change must be < 50% day-over-day
            (flag but don't reject — BTC has had 40%+ daily moves)

        Returns only valid records. Logs warnings for flagged records.
        """
```

### 2. New Module: `monitor/api/yfinance_client.py`

```python
"""
Yahoo Finance client for BTC-USD historical data.

yfinance provides daily OHLCV data for BTC-USD from 2014-09-17 onward.
No API key required. Rate limiting is handled by the library.

Dependencies: yfinance>=0.2.30 (adds to requirements.txt)
"""

class YFinanceClient:
    TICKER = "BTC-USD"
    EARLIEST_DATE = date(2014, 9, 17)  # First BTC-USD data on Yahoo

    def get_daily_prices(self, start_date: date, end_date: date) -> list[dict]:
        """
        Fetch daily close prices for BTC-USD.

        Returns list of:
          {"date": "YYYY-MM-DD", "price_usd": float, "market_cap": None, "volume": float}

        market_cap is None because Yahoo doesn't provide it.
        Volume is daily USD volume.

        Implementation:
          import yfinance as yf
          ticker = yf.Ticker(self.TICKER)
          df = ticker.history(start=start_date, end=end_date, interval="1d")
          # df has columns: Open, High, Low, Close, Volume
          # Use Close as price_usd
          # Convert to list of dicts

        Error handling:
          - If yfinance raises, log warning and return empty list
          - If DataFrame is empty, return empty list
          - If partial data, return what's available
        """

    def health_check(self) -> dict:
        """
        Fetch last 5 days to verify connectivity.
        Returns {"status": "ok"/"error", "latest_date": str, "latency_ms": int}
        """
```

### 3. Bundled Seed Data: `data/seed_prices.csv`

A CSV file bundled with the project containing daily BTC/USD close prices from 2013-01-01 through 2014-09-16 (the gap before Yahoo Finance data begins). This covers the early period that no free API reliably serves.

Format:
```csv
date,price_usd,volume
2013-01-01,13.30,0
2013-01-02,13.25,0
...
2014-09-16,457.00,0
```

Source: CoinGecko manual export or CoinMarketCap historical snapshots. This file is ~620 rows, approximately 15 KB.

Volume is set to 0 for seed data rows (historical volume data from 2013 is unreliable across sources).

### 4. CSV Fallback Source: `monitor/api/csv_backfill.py`

```python
class CSVBackfill:
    CSV_PATH = "data/seed_prices.csv"

    def get_daily_prices(self, start_date: date, end_date: date) -> list[dict]:
        """
        Read seed CSV. Filter to requested date range.
        Returns same format as YFinanceClient.
        Falls back to empty list if CSV doesn't exist.
        """
```

### 5. Modified: `monitor/api/coingecko.py`

Change `get_full_history()` to support chunked backwards fetching:

```python
# CURRENT (broken — fetches only 365 days):
def get_full_history(self, start_year=2015):
    days_to_fetch = min(total_days, 365)  # HARD LIMIT
    records = self.get_historical_prices(days=days_to_fetch)

# NEW (chunked — fetches in 365-day windows):
def get_full_history(self, start_year=2015) -> list[dict]:
    """
    Fetch daily prices in 365-day chunks going backwards from today.

    CoinGecko free tier allows /market_chart?days=N with N up to 365
    and interval=daily. We make multiple requests to cover the full range.

    Rate limiting: 1 request per 2 seconds (30/min free tier).
    Each chunk covers 365 days. For 2015-present (~10 years), that's ~10 requests.
    Total time: ~20 seconds.
    """
    all_records = {}
    now = datetime.now(timezone.utc)
    start_dt = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    total_days = (now - start_dt).days

    # Fetch in 365-day chunks, newest first
    days_fetched = 0
    while days_fetched < total_days:
        chunk_size = min(365, total_days - days_fetched)
        # CoinGecko /market_chart?days=N returns the last N days from now
        # To get older data, we can't offset — we need the /range endpoint
        # which requires Pro. So we only get the most recent 365 days here.
        # Older data comes from yfinance/CSV via BackfillOrchestrator.
        break  # CoinGecko free tier truly only gives last 365 days

    # The chunked approach doesn't work on free tier because the endpoint
    # always returns data relative to "now". Keep single 365-day fetch.
    records = self.get_historical_prices(days=min(total_days, 365))
    for r in records:
        all_records[r["date"]] = r

    return list(all_records.values())
```

**Key insight:** CoinGecko free tier `/market_chart?days=N` always returns the last N days from now — you cannot request an arbitrary historical window. The `/market_chart/range` endpoint requires a paid API key. Therefore, CoinGecko remains capped at 365 days, and **yfinance becomes the primary backfill source for data older than 1 year.**

### 6. Modified: `monitor/monitor.py`

Update `backfill_history()` to use the new orchestrator:

```python
# CURRENT:
def backfill_history(self, start_year=2015, progress_callback=None):
    existing = self.db.get_price_date_range()
    count = self.api.backfill_prices(start_year, self.db)
    return count

# NEW:
def backfill_history(self, start_year=2013, full=False, progress_callback=None):
    """
    Backfill historical daily prices.

    Args:
        start_year: How far back to fetch (default 2013)
        full: If True, use multi-source backfill (yfinance + CSV + CoinGecko)
              If False, use CoinGecko only (last 365 days, fast)
        progress_callback: fn(dates_added, total_needed)
    """
    if full:
        from monitor.backfill import BackfillOrchestrator
        orchestrator = BackfillOrchestrator(self.db, self.config)
        return orchestrator.run(start_year=start_year, progress_callback=progress_callback)
    else:
        # Quick mode: CoinGecko last 365 days only
        count = self.api.backfill_prices(start_year, self.db)
        if progress_callback:
            progress_callback(count)
        return count
```

### 7. Modified: `main.py` CLI

Update the backfill command:

```python
@monitor_group.command("backfill")
@click.option("--full", is_flag=True, help="Full backfill from 2013 using multiple sources (slower)")
@click.option("--start-year", default=2013, type=int, help="Start year for full backfill")
@click.pass_context
def backfill(ctx, full, start_year):
    """Backfill historical price data."""
    c = ctx.obj
    monitor = c["monitor"]

    if full:
        console.print("[btc]Fetching full history from multiple sources...[/]")
        console.print("Sources: CoinGecko (recent) + Yahoo Finance (2014+) + seed CSV (2013)")
        with Progress() as progress:
            task = progress.add_task("Backfilling...", total=None)
            def cb(added, total):
                progress.update(task, completed=added, total=total)
            result = monitor.backfill_history(start_year=start_year, full=True, progress_callback=cb)
        console.print(f"[bull]Done.[/] Added {result.dates_added} days. "
                      f"Range: {result.date_range[0]} to {result.date_range[1]}")
        if result.gaps_remaining:
            console.print(f"[warning]{len(result.gaps_remaining)} gaps remain[/]")
        if result.errors:
            for err in result.errors:
                console.print(f"[bear]{err}[/]")
    else:
        console.print("[btc]Quick backfill (last 365 days via CoinGecko)...[/]")
        count = monitor.backfill_history(full=False)
        console.print(f"[bull]Done.[/] {count} days loaded.")
```

### 8. Modified: `requirements.txt`

Add:
```
yfinance>=0.2.30       # Historical BTC/USD prices (Yahoo Finance)
```

### 9. Modified: `models/database.py`

Add gap detection method:

```python
def get_price_gaps(self, start_date: str, end_date: str, max_gap_days: int = 3) -> list[tuple[str, str]]:
    """
    Find gaps in price_history where consecutive missing days exceed max_gap_days.

    Returns list of (gap_start_date, gap_end_date) as ISO strings.

    Implementation:
      1. Generate full date range from start_date to end_date
      2. Query existing dates: SELECT date FROM price_history WHERE date BETWEEN ? AND ? ORDER BY date
      3. Compare: find runs of missing dates longer than max_gap_days
      4. Return gap boundaries
    """
```

### 10. BTC/Gold Ratio Fix

While backfilling, also address the BTC/Gold 30-day change being hardcoded to 0:

In `monitor/api/coingecko.py`, the `get_btc_gold_ratio()` method returns the current ratio but no history. The 30-day change requires two data points.

**Fix approach:**
- Store BTC/Gold ratio in `metrics_snapshots` (already stored as `btc_gold_ratio`)
- In `alerts/engine.py` `compute_derived_metrics()`, calculate 30-day BTC/Gold change by querying the snapshot from 30 days ago:

```python
def _compute_btc_gold_change_30d(self) -> float:
    """
    Compare current BTC/Gold ratio to 30-day-old snapshot.
    Returns percentage change. Returns 0.0 if no historical data.
    """
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    old_snapshot = self.db.get_nearest_snapshot(thirty_days_ago)
    if old_snapshot and old_snapshot.get("btc_gold_ratio"):
        current = self.current_snapshot.sentiment.btc_gold_ratio
        old = old_snapshot["btc_gold_ratio"]
        if old > 0:
            return ((current - old) / old) * 100
    return 0.0
```

Add to `database.py`:

```python
def get_nearest_snapshot(self, target_timestamp: str) -> dict | None:
    """
    Return the metrics_snapshot closest to target_timestamp (but not after).
    Used for historical comparisons (e.g., 30-day-ago BTC/Gold ratio).
    """
    query = """
        SELECT * FROM metrics_snapshots
        WHERE timestamp <= ?
        ORDER BY timestamp DESC
        LIMIT 1
    """
    row = self.conn.execute(query, (target_timestamp,)).fetchone()
    return dict(row) if row else None
```

## Benefits

| Decision | Why | Alternative Considered |
|----------|-----|----------------------|
| **yfinance as primary backfill** | Free, no API key, reliable, goes back to Sep 2014, maintained library | CoinGecko Pro ($130/mo), Kraken API (720-day limit), manual CSV download |
| **Bundled CSV for 2013–2014** | Fills the gap before Yahoo Finance data begins. Small file (~15 KB), ships with repo | Require user to manually download and import |
| **Gap detection before fetch** | Avoids re-fetching existing data. Makes backfill idempotent and resumable | Fetch everything every time (wasteful, slow) |
| **Validation layer** | Catches corrupted API responses, prevents garbage data in DB | Trust API responses blindly |
| **`--full` flag separation** | Quick mode (365d, 5 seconds) for daily use. Full mode (2013+, 30 seconds) for first setup | Always do full backfill (slow for routine use) |

## Expectations

- **`price_history` table after full backfill:** ~4,400 rows (Jan 2013 – Feb 2026)
- **Full backfill runtime:** Under 60 seconds on a normal connection
- **Quick backfill runtime:** Under 10 seconds
- **Data accuracy:** Prices within 2% of CoinGecko/CMC reference for any given date
- **Gap tolerance:** Weekends and holidays may have interpolated or missing data — gaps of up to 2 days are acceptable. Gaps of 3+ days must be logged as warnings.
- **Idempotency:** Running `backfill --full` twice should add 0 new rows on the second run

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| yfinance library breaks or Yahoo changes API | Low (actively maintained, 30k+ GitHub stars) | High — no backfill for 2014-2024 | CSV fallback covers critical data. Can add Kraken/Binance as tertiary source later. |
| CoinGecko rate-limits during chunked fetch | Medium | Low — only affects recent 365 days | Built-in rate limiter (2s between requests). yfinance covers the same period as backup. |
| Seed CSV has inaccurate 2013 prices | Low | Low — 2013 prices are small numbers, minor impact on DCA sims | Cross-reference with multiple sources before bundling. Document data provenance. |
| yfinance returns market_cap as None | Certain | Low — market_cap is optional in price_history | Schema allows NULL for market_cap. DCA engine only needs price_usd. |
| Backfill takes too long on slow connections | Low | Medium — user might cancel | Progress callback with ETA. Resumable (gap detection skips existing data). |

## Results Criteria

1. **`python main.py monitor backfill --full`** completes without error and prints: dates added, date range, sources used
2. **`SELECT COUNT(*) FROM price_history`** returns 4,000+ rows
3. **`SELECT MIN(date), MAX(date) FROM price_history`** returns `2013-01-01` to today
4. **`python main.py monitor backfill --full`** run a second time adds 0 rows (idempotent)
5. **DCA simulation from 2015 works:** `python main.py dca simulate --start 2015-01-01 --end 2025-01-01` produces results using real prices
6. **Cycle overlay chart uses real data:** chart shows actual Cycle 2, 3, and 4 prices (not just constants)
7. **BTC/Gold 30d change is non-zero** when 30+ days of snapshots exist
8. **All 165 existing tests still pass** — no regressions

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `monitor/backfill.py` | **NEW** | BackfillOrchestrator with gap detection and multi-source fetching |
| `monitor/api/yfinance_client.py` | **NEW** | YFinanceClient wrapper |
| `monitor/api/csv_backfill.py` | **NEW** | CSV seed data reader |
| `data/seed_prices.csv` | **NEW** | Bundled daily prices Jan 2013 – Sep 2014 (~620 rows) |
| `monitor/api/coingecko.py` | **MODIFY** | Update `get_full_history()` docstring to clarify free-tier limitation |
| `monitor/monitor.py` | **MODIFY** | Update `backfill_history()` to support `--full` mode |
| `main.py` | **MODIFY** | Update `backfill` command with `--full` and `--start-year` flags |
| `models/database.py` | **MODIFY** | Add `get_price_gaps()` and `get_nearest_snapshot()` methods |
| `alerts/engine.py` | **MODIFY** | Add `_compute_btc_gold_change_30d()` using historical snapshots |
| `requirements.txt` | **MODIFY** | Add `yfinance>=0.2.30` |
| `tests/test_backfill.py` | **NEW** | Tests for BackfillOrchestrator, gap detection, validation, CSV fallback |
