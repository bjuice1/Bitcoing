"""Yahoo Finance client for BTC-USD historical data.

yfinance provides daily OHLCV data for BTC-USD from 2014-09-17 onward.
No API key required. Rate limiting is handled by the library.
"""
import logging
from datetime import date, timedelta

logger = logging.getLogger("btcmonitor.yfinance")


class YFinanceClient:
    TICKER = "BTC-USD"
    EARLIEST_DATE = date(2014, 9, 17)

    def get_daily_prices(self, start_date: date, end_date: date) -> list[dict]:
        """Fetch daily close prices for BTC-USD.

        Returns list of {"date": "YYYY-MM-DD", "price_usd": float, "market_cap": None, "volume": float}
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed. Run: pip install yfinance")
            return []

        if start_date < self.EARLIEST_DATE:
            start_date = self.EARLIEST_DATE

        if end_date <= start_date:
            return []

        try:
            ticker = yf.Ticker(self.TICKER)
            # yfinance end date is exclusive, add 1 day
            df = ticker.history(
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                interval="1d",
            )

            if df is None or df.empty:
                logger.warning("yfinance returned empty DataFrame")
                return []

            records = []
            for idx, row in df.iterrows():
                dt = idx.date() if hasattr(idx, 'date') else idx
                price = float(row["Close"])
                volume = float(row["Volume"]) if "Volume" in row else 0

                if price <= 0:
                    continue

                records.append({
                    "date": str(dt),
                    "price_usd": price,
                    "market_cap": None,
                    "volume": volume,
                })

            logger.info(f"yfinance: fetched {len(records)} days ({start_date} to {end_date})")
            return records

        except Exception as e:
            logger.warning(f"yfinance fetch failed: {e}")
            return []

    def health_check(self) -> dict:
        """Fetch last 5 days to verify connectivity."""
        import time
        start = time.monotonic()
        try:
            end = date.today()
            start_d = end - timedelta(days=5)
            records = self.get_daily_prices(start_d, end)
            latency = int((time.monotonic() - start) * 1000)
            return {
                "status": "ok" if records else "empty",
                "latest_date": records[-1]["date"] if records else None,
                "latency_ms": latency,
            }
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            return {"status": f"error: {e}", "latest_date": None, "latency_ms": latency}
