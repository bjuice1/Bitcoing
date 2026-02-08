"""Forward-looking DCA projection scenarios."""
import logging

logger = logging.getLogger("btcmonitor.dca.projections")


class DCAProjector:
    def __init__(self, current_price, current_btc_held=0, total_invested=0):
        self.current_price = current_price
        self.current_btc = current_btc_held
        self.total_invested = total_invested

    def project_scenario(self, target_price, months, monthly_dca):
        """Linear price path from current to target over N months."""
        prices = []
        step = (target_price - self.current_price) / max(months, 1)
        for m in range(1, months + 1):
            prices.append(self.current_price + step * m)

        additional_btc = 0
        additional_invested = 0
        for p in prices:
            if p > 0:
                additional_btc += monthly_dca / p
                additional_invested += monthly_dca

        total_btc = self.current_btc + additional_btc
        total_invested = self.total_invested + additional_invested
        final_value = total_btc * target_price

        return {
            "target_price": target_price,
            "months": months,
            "monthly_dca": monthly_dca,
            "additional_btc": additional_btc,
            "total_btc": total_btc,
            "total_invested": total_invested,
            "final_value": final_value,
            "roi_pct": ((final_value - total_invested) / total_invested * 100) if total_invested > 0 else 0,
        }

    def project_bear_then_bull(self, bear_bottom, bear_months, bull_top, bull_months, monthly_dca):
        """Two-phase: drop to bottom, then recover to top."""
        # Phase 1: Bear
        bear = self.project_scenario(bear_bottom, bear_months, monthly_dca)

        # Phase 2: Bull from bottom
        at_bottom = DCAProjector(bear_bottom, bear["total_btc"], bear["total_invested"])
        bull = at_bottom.project_scenario(bull_top, bull_months, monthly_dca)

        return {
            "at_bottom": bear,
            "at_top": bull,
            "total_months": bear_months + bull_months,
            "total_invested": bull["total_invested"],
            "final_value": bull["final_value"],
            "final_roi_pct": bull["roi_pct"],
        }

    def project_flat(self, months, monthly_dca):
        """Price stays flat at current level."""
        return self.project_scenario(self.current_price, months, monthly_dca)

    def compare_projections(self, monthly_dca=200):
        """Run standard bear/bull/flat scenarios."""
        return {
            "bear_60k": self.project_scenario(60000, 12, monthly_dca),
            "bear_45k": self.project_scenario(45000, 18, monthly_dca),
            "flat": self.project_flat(24, monthly_dca),
            "bull_100k": self.project_scenario(100000, 12, monthly_dca),
            "bull_150k": self.project_scenario(150000, 24, monthly_dca),
            "full_cycle": self.project_bear_then_bull(50000, 12, 200000, 18, monthly_dca),
        }
