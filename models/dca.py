"""Dataclasses for DCA simulation results."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class DCAResult:
    start_date: date = field(default_factory=date.today)
    end_date: date = field(default_factory=date.today)
    frequency: str = "weekly"
    amount_per_buy: float = 100.0
    total_invested: float = 0.0
    total_btc: float = 0.0
    current_value: float = 0.0
    avg_cost_basis: float = 0.0
    roi_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    num_buys: int = 0
    best_buy_price: float = 0.0
    worst_buy_price: float = 0.0
    time_series: list = field(default_factory=list)


@dataclass
class DCAComparison:
    dca_result: Optional[DCAResult] = None
    lumpsum_invested: float = 0.0
    lumpsum_btc: float = 0.0
    lumpsum_value: float = 0.0
    lumpsum_roi_pct: float = 0.0
    dca_advantage_pct: float = 0.0


@dataclass
class DCAPortfolio:
    id: Optional[int] = None
    name: str = "Default"
    start_date: date = field(default_factory=date.today)
    frequency: str = "weekly"
    amount: float = 100.0
    total_invested: float = 0.0
    total_btc: float = 0.0
    purchases: list = field(default_factory=list)

    def add_purchase(self, purchase_date, price, usd_amount=None):
        amt = usd_amount or self.amount
        btc = amt / price
        self.purchases.append({
            "date": str(purchase_date),
            "price": price,
            "btc_amount": btc,
            "usd_amount": amt,
        })
        self.total_invested += amt
        self.total_btc += btc
