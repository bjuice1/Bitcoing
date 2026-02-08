"""DCA simulation engine."""
import logging
from datetime import date, timedelta
from models.dca import DCAResult, DCAComparison
from models.enums import Frequency

logger = logging.getLogger("btcmonitor.dca")


class DCAEngine:
    def __init__(self, db):
        self.db = db

    def _generate_buy_dates(self, start, end, frequency):
        """Generate list of buy dates based on frequency."""
        dates = []
        current = start
        today = date.today()

        if frequency == Frequency.DAILY or frequency == "daily":
            while current <= end and current <= today:
                dates.append(current)
                current += timedelta(days=1)
        elif frequency == Frequency.WEEKLY or frequency == "weekly":
            # Align to Monday
            while current.weekday() != 0:
                current += timedelta(days=1)
            while current <= end and current <= today:
                dates.append(current)
                current += timedelta(weeks=1)
        elif frequency == Frequency.BIWEEKLY or frequency == "biweekly":
            while current.weekday() != 0:
                current += timedelta(days=1)
            while current <= end and current <= today:
                dates.append(current)
                current += timedelta(weeks=2)
        elif frequency == Frequency.MONTHLY or frequency == "monthly":
            while current <= end and current <= today:
                dates.append(date(current.year, current.month, 1))
                if current.month == 12:
                    current = date(current.year + 1, 1, 1)
                else:
                    current = date(current.year, current.month + 1, 1)
        return dates

    def _get_price_for_date(self, target_date):
        """Get price for a date, falling back to nearest prior date."""
        record = self.db.get_price_for_date(target_date)
        if record is None:
            raise ValueError(f"No price data available for {target_date}. Run backfill first.")
        return record["price_usd"]

    def simulate(self, start_date, end_date=None, amount=100, frequency="weekly"):
        """Run DCA simulation over a historical period."""
        if end_date is None:
            end_date = date.today()
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)

        buy_dates = self._generate_buy_dates(start_date, end_date, frequency)
        if not buy_dates:
            raise ValueError("No buy dates generated. Check date range and frequency.")

        total_invested = 0.0
        total_btc = 0.0
        best_price = float("inf")
        worst_price = 0.0
        min_ratio = float("inf")
        time_series = []

        for buy_date in buy_dates:
            try:
                price = self._get_price_for_date(buy_date)
            except ValueError:
                continue  # Skip dates with no data

            btc_bought = amount / price
            total_invested += amount
            total_btc += btc_bought

            best_price = min(best_price, price)
            worst_price = max(worst_price, price)

            # Track portfolio value for drawdown
            portfolio_value = total_btc * price
            if total_invested > 0:
                ratio = portfolio_value / total_invested
                min_ratio = min(min_ratio, ratio)

            time_series.append({
                "date": str(buy_date),
                "price": price,
                "btc_bought": btc_bought,
                "total_btc": total_btc,
                "total_invested": total_invested,
                "portfolio_value": portfolio_value,
                "avg_cost_basis": total_invested / total_btc if total_btc > 0 else 0,
            })

        # Final valuation at end_date price
        try:
            end_price = self._get_price_for_date(end_date)
        except ValueError:
            end_price = time_series[-1]["price"] if time_series else 0

        current_value = total_btc * end_price
        avg_cost = total_invested / total_btc if total_btc > 0 else 0
        roi = ((current_value - total_invested) / total_invested * 100) if total_invested > 0 else 0
        max_dd = (1 - min_ratio) * 100 if min_ratio < float("inf") else 0

        return DCAResult(
            start_date=start_date,
            end_date=end_date,
            frequency=str(frequency),
            amount_per_buy=amount,
            total_invested=total_invested,
            total_btc=total_btc,
            current_value=current_value,
            avg_cost_basis=avg_cost,
            roi_pct=roi,
            max_drawdown_pct=max(0, max_dd),
            num_buys=len(time_series),
            best_buy_price=best_price if best_price < float("inf") else 0,
            worst_buy_price=worst_price,
            time_series=time_series,
        )

    def compare_to_lumpsum(self, start_date, end_date=None, total_amount=10000, frequency="weekly"):
        """Compare DCA vs lump sum investment."""
        if end_date is None:
            end_date = date.today()
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)

        # DCA simulation
        buy_dates = self._generate_buy_dates(start_date, end_date, frequency)
        num_buys = len(buy_dates)
        per_buy = total_amount / num_buys if num_buys > 0 else total_amount
        dca_result = self.simulate(start_date, end_date, per_buy, frequency)

        # Lump sum: buy all at start
        start_price = self._get_price_for_date(start_date)
        end_price = self._get_price_for_date(end_date)
        ls_btc = total_amount / start_price
        ls_value = ls_btc * end_price
        ls_roi = ((ls_value - total_amount) / total_amount * 100)

        dca_advantage = dca_result.roi_pct - ls_roi

        return DCAComparison(
            dca_result=dca_result,
            lumpsum_invested=total_amount,
            lumpsum_btc=ls_btc,
            lumpsum_value=ls_value,
            lumpsum_roi_pct=ls_roi,
            dca_advantage_pct=dca_advantage,
        )

    def simulate_bear_scenarios(self, amount=100, frequency="weekly"):
        """Pre-defined bear market DCA comparisons."""
        scenarios = [
            ("2018 Bear", "2018-01-01", "2018-12-31"),
            ("2022 Bear", "2021-11-01", "2022-11-30"),
            ("Current Cycle", "2025-10-01", str(date.today())),
        ]
        results = []
        for name, start, end in scenarios:
            try:
                result = self.simulate(start, end, amount, frequency)
                results.append({"name": name, "result": result})
            except ValueError as e:
                results.append({"name": name, "error": str(e)})
        return results
