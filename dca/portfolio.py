"""Track real DCA purchases."""
import logging
from datetime import date

logger = logging.getLogger("btcmonitor.dca.portfolio")


class PortfolioTracker:
    def __init__(self, db):
        self.db = db

    def create_portfolio(self, name, frequency="weekly", amount=100):
        portfolio_id = self.db.create_portfolio(name, date.today(), frequency, amount)
        logger.info(f"Created portfolio '{name}' (id={portfolio_id})")
        return portfolio_id

    def record_purchase(self, portfolio_id, purchase_date, price, usd_amount=None):
        portfolio = self.db.get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")
        amt = usd_amount or portfolio["amount"]
        btc_amount = amt / price
        self.db.add_purchase(portfolio_id, purchase_date, price, btc_amount, amt)
        logger.info(f"Recorded purchase: {btc_amount:.8f} BTC at ${price:,.2f}")
        return btc_amount

    def get_portfolio_status(self, portfolio_id, current_price):
        portfolio = self.db.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        purchases = portfolio.get("purchases", [])
        total_invested = sum(p["usd_amount"] for p in purchases)
        total_btc = sum(p["btc_amount"] for p in purchases)
        current_value = total_btc * current_price
        avg_cost = total_invested / total_btc if total_btc > 0 else 0
        pnl = current_value - total_invested
        roi = (pnl / total_invested * 100) if total_invested > 0 else 0

        return {
            "id": portfolio_id,
            "name": portfolio["name"],
            "frequency": portfolio["frequency"],
            "amount_per_buy": portfolio["amount"],
            "num_purchases": len(purchases),
            "total_invested": total_invested,
            "total_btc": total_btc,
            "current_value": current_value,
            "avg_cost_basis": avg_cost,
            "current_price": current_price,
            "pnl_usd": pnl,
            "roi_pct": roi,
        }

    def list_portfolios(self):
        return self.db.list_portfolios()
