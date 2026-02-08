"""CycleAnalyzer - Bitcoin cycle analysis based on Nadeau's framework."""
import logging
from datetime import date
from models.enums import CyclePhase, SignalStatus
from utils.constants import (
    HALVING_DATES, HALVING_PRICES, CYCLE_ATH, BLOCK_REWARDS,
    days_since_last_halving, days_until_next_halving, get_current_block_reward,
)

logger = logging.getLogger("btcmonitor.cycle")


class CycleAnalyzer:
    def __init__(self, db):
        self.db = db

    def get_halving_info(self):
        """Current halving cycle information."""
        since = days_since_last_halving()
        until = days_until_next_halving()
        total_cycle = since + (until or 0)
        pct_elapsed = (since / total_cycle * 100) if total_cycle > 0 else 0

        return {
            "last_halving": str(HALVING_DATES[4]),
            "next_halving_est": str(HALVING_DATES[5]),
            "days_since": since,
            "days_until": until,
            "cycle_pct_elapsed": round(pct_elapsed, 1),
            "current_block_reward": get_current_block_reward(),
            "next_block_reward": BLOCK_REWARDS.get(5, 1.5625),
            "halving_era": 4,
        }

    def get_cycle_phase(self, snapshot=None):
        """Determine current cycle phase based on multiple signals."""
        since = days_since_last_halving()
        drawdown = self._get_drawdown_pct()
        fear_greed = snapshot.sentiment.fear_greed_value if snapshot else 50
        mvrv = snapshot.valuation.mvrv_ratio if snapshot else None

        # Phase determination logic based on Nadeau's framework
        if drawdown > 70 or (mvrv is not None and mvrv < 0.5):
            phase = CyclePhase.CAPITULATION
            confidence = "high" if (drawdown > 70 and fear_greed < 15) else "medium"
        elif drawdown > 50 or (mvrv is not None and mvrv < 1.0):
            phase = CyclePhase.MID_BEAR
            confidence = "high" if fear_greed < 25 else "medium"
        elif drawdown > 30:
            if since < 365:
                phase = CyclePhase.DISTRIBUTION
                confidence = "medium"
            else:
                phase = CyclePhase.EARLY_BEAR
                confidence = "medium"
        elif drawdown > 15:
            if fear_greed > 60:
                phase = CyclePhase.LATE_BULL
                confidence = "medium"
            else:
                phase = CyclePhase.DISTRIBUTION
                confidence = "low"
        elif drawdown < 5:
            if since < 180:
                phase = CyclePhase.EARLY_BULL
                confidence = "medium"
            elif fear_greed > 75:
                phase = CyclePhase.LATE_BULL
                confidence = "high"
            else:
                phase = CyclePhase.MID_BULL
                confidence = "medium"
        else:
            phase = CyclePhase.MID_BULL
            confidence = "low"

        # Override: if very far into cycle (>3 years) and drawdown significant
        if since > 1095 and drawdown < 30 and fear_greed < 40:
            phase = CyclePhase.ACCUMULATION
            confidence = "medium"

        return {"phase": phase, "confidence": confidence}

    def get_cycle_comparison(self):
        """Compare current cycle to prior cycles at same days-since-halving."""
        since = days_since_last_halving()
        current_price = self._get_current_price()
        halving_price = HALVING_PRICES.get(4, 63963)

        comparisons = []
        for era in [2, 3]:
            halving_date = HALVING_DATES[era]
            h_price = HALVING_PRICES.get(era, 0)
            target_date = date(
                halving_date.year + since // 365,
                min(12, halving_date.month + (since % 365) // 30),
                min(28, halving_date.day),
            )
            ath = CYCLE_ATH.get(era, {})
            comparisons.append({
                "cycle": f"Cycle {era} ({halving_date.year})",
                "halving_price": h_price,
                "ath_price": ath.get("price", 0),
                "ath_date": str(ath.get("date", "N/A")),
                "gain_to_ath_pct": ((ath.get("price", 0) - h_price) / h_price * 100) if h_price > 0 else 0,
            })

        current_gain = ((current_price - halving_price) / halving_price * 100) if halving_price > 0 else 0
        comparisons.append({
            "cycle": f"Current (2024)",
            "halving_price": halving_price,
            "current_price": current_price,
            "gain_from_halving_pct": current_gain,
            "days_since_halving": since,
        })

        return comparisons

    def get_drawdown_analysis(self):
        """Analyze current drawdown vs historical cycle drawdowns."""
        drawdown = self._get_drawdown_pct()
        since = days_since_last_halving()

        historical_drawdowns = {
            "Cycle 2 (2016)": {"max_drawdown": 83, "months_to_bottom": 12},
            "Cycle 3 (2020)": {"max_drawdown": 77, "months_to_bottom": 12},
            "Cycle 4 (2024)": {"max_drawdown": round(drawdown, 1), "months_to_bottom": "ongoing"},
        }

        avg_max = (83 + 77) / 2

        return {
            "current_drawdown_pct": round(drawdown, 1),
            "historical": historical_drawdowns,
            "avg_cycle_max_drawdown": avg_max,
            "vs_average": f"{'Below' if drawdown < avg_max else 'Above'} historical average ({avg_max:.0f}%)",
            "days_since_halving": since,
        }

    def get_nadeau_signals(self, snapshot=None):
        """Evaluate Nadeau-style indicators."""
        signals = []
        drawdown = self._get_drawdown_pct()

        # MVRV
        mvrv = snapshot.valuation.mvrv_ratio if snapshot else None
        if mvrv is not None:
            if mvrv < 1.0:
                status = SignalStatus.BULLISH
                interp = f"MVRV {mvrv:.2f} - below realized value, historically undervalued"
            elif mvrv > 3.0:
                status = SignalStatus.BEARISH
                interp = f"MVRV {mvrv:.2f} - historically overvalued zone"
            else:
                status = SignalStatus.NEUTRAL
                interp = f"MVRV {mvrv:.2f} - fair value range"
            signals.append(("MVRV Ratio", status, mvrv, interp))
        else:
            signals.append(("MVRV Ratio", SignalStatus.NEUTRAL, None, "Data unavailable"))

        # Fear & Greed
        fg = snapshot.sentiment.fear_greed_value if snapshot else 50
        if fg < 20:
            status = SignalStatus.BULLISH
            interp = f"Extreme Fear ({fg}) - contrarian bullish, capitulation zone"
        elif fg < 40:
            status = SignalStatus.BULLISH
            interp = f"Fear ({fg}) - sentiment sour, opportunity per Nadeau"
        elif fg > 80:
            status = SignalStatus.BEARISH
            interp = f"Extreme Greed ({fg}) - distribution risk"
        elif fg > 60:
            status = SignalStatus.BEARISH
            interp = f"Greed ({fg}) - elevated risk"
        else:
            status = SignalStatus.NEUTRAL
            interp = f"Neutral ({fg})"
        signals.append(("Fear & Greed", status, fg, interp))

        # Drawdown
        if drawdown > 50:
            status = SignalStatus.BULLISH
            interp = f"{drawdown:.1f}% from ATH - historically strong entry zone"
        elif drawdown > 30:
            status = SignalStatus.NEUTRAL
            interp = f"{drawdown:.1f}% from ATH - mid-cycle correction territory"
        elif drawdown < 10:
            status = SignalStatus.BEARISH
            interp = f"{drawdown:.1f}% from ATH - near top, distribution risk"
        else:
            status = SignalStatus.NEUTRAL
            interp = f"{drawdown:.1f}% from ATH"
        signals.append(("Drawdown", status, drawdown, interp))

        # Hash rate trend
        hr = snapshot.onchain.hash_rate_th if snapshot else 0
        if hr > 0:
            # We'd need historical hash rate for trend; use difficulty_change as proxy
            diff_change = snapshot.onchain.difficulty_change_pct if snapshot else 0
            if diff_change < -10:
                status = SignalStatus.BEARISH
                interp = f"Difficulty dropping {diff_change:.1f}% - miner stress"
            elif diff_change > 5:
                status = SignalStatus.BULLISH
                interp = f"Difficulty rising {diff_change:.1f}% - network strength"
            else:
                status = SignalStatus.NEUTRAL
                interp = f"Difficulty change {diff_change:.1f}% - stable"
            signals.append(("Hash Rate / Mining", status, diff_change, interp))

        # BTC/Gold ratio
        gold = snapshot.sentiment.btc_gold_ratio if snapshot else 0
        if gold > 0:
            signals.append(("BTC/Gold Ratio", SignalStatus.NEUTRAL, gold,
                          f"BTC = {gold:.1f} oz gold"))

        # Dominance
        dom = snapshot.sentiment.btc_dominance_pct if snapshot else 0
        if dom > 60:
            status = SignalStatus.BULLISH
            interp = f"BTC dominance {dom:.1f}% - flight to quality"
        elif dom < 40:
            status = SignalStatus.BEARISH
            interp = f"BTC dominance {dom:.1f}% - alt rotation"
        else:
            status = SignalStatus.NEUTRAL
            interp = f"BTC dominance {dom:.1f}%"
        signals.append(("Dominance", status, dom, interp))

        # Overall bias
        bullish = sum(1 for _, s, _, _ in signals if s == SignalStatus.BULLISH)
        bearish = sum(1 for _, s, _, _ in signals if s == SignalStatus.BEARISH)
        if bullish > bearish + 1:
            overall = SignalStatus.BULLISH
        elif bearish > bullish + 1:
            overall = SignalStatus.BEARISH
        else:
            overall = SignalStatus.NEUTRAL

        return {
            "signals": signals,
            "overall_bias": overall,
            "bullish_count": bullish,
            "bearish_count": bearish,
        }

    def get_supply_dynamics(self, current_price=None):
        """Estimate % of supply in profit using price history."""
        history = self.db.get_price_history()
        if not history or current_price is None:
            return {"pct_in_profit": None, "note": "Insufficient data"}

        prices = [r["price_usd"] for r in history]
        in_profit = sum(1 for p in prices if p <= current_price)
        total = len(prices)

        return {
            "pct_in_profit": round(in_profit / total * 100, 1) if total > 0 else None,
            "total_days_analyzed": total,
            "note": "Proxy: % of historical daily prices below current price (not UTXO-based)",
        }

    def _get_drawdown_pct(self):
        history = self.db.get_price_history()
        if not history:
            return 0
        ath = max(r["price_usd"] for r in history)
        current = history[-1]["price_usd"]
        if ath == 0:
            return 0
        return ((ath - current) / ath) * 100

    def _get_current_price(self):
        history = self.db.get_price_history()
        if not history:
            return 0
        return history[-1]["price_usd"]
