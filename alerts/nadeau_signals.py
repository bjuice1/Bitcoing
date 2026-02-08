"""Nadeau-framework composite signal evaluator."""
import logging
from datetime import datetime, timezone
from models.enums import LTHProxy, ReflexivityState, SignalStatus, CyclePhase
from utils.constants import days_since_last_halving

logger = logging.getLogger("btcmonitor.alerts.nadeau")


class NadeauSignalEvaluator:
    def __init__(self, db):
        self.db = db

    def evaluate_lth_proxy(self, snapshot):
        """Proxy LTH behavior via MVRV trend, price vs 200d MA, sustained fear."""
        mvrv = snapshot.valuation.mvrv_ratio
        fear = snapshot.sentiment.fear_greed_value
        price = snapshot.price.price_usd

        # Calculate 200-day MA from price history
        history = self.db.get_price_history()
        prices = [r["price_usd"] for r in history[-200:]] if history else []
        ma_200 = sum(prices) / len(prices) if prices else 0

        if mvrv is not None and mvrv < 1.0 and fear < 25:
            return {
                "status": LTHProxy.EARLY_ACCUMULATION,
                "detail": f"MVRV {mvrv:.2f} + Fear {fear} suggest capitulation exhaustion",
                "signal": SignalStatus.BULLISH,
            }
        elif mvrv is not None and mvrv < 1.5 and price < ma_200:
            return {
                "status": LTHProxy.EARLY_ACCUMULATION,
                "detail": f"Price below 200d MA (${ma_200:,.0f}) with MVRV {mvrv:.2f}",
                "signal": SignalStatus.BULLISH,
            }
        elif mvrv is not None and mvrv > 2.5:
            return {
                "status": LTHProxy.DISTRIBUTING,
                "detail": f"MVRV {mvrv:.2f} elevated - likely LTH distribution phase",
                "signal": SignalStatus.BEARISH,
            }
        else:
            return {
                "status": LTHProxy.NEUTRAL,
                "detail": "No clear distribution/accumulation signal",
                "signal": SignalStatus.NEUTRAL,
            }

    def evaluate_cycle_position(self, snapshot):
        """Evaluate where we are per Nadeau's cycle framework."""
        since = days_since_last_halving()
        year = since / 365

        if year < 1:
            phase_desc = "Post-halving Year 1: Historically bullish, supply shock taking effect"
            expected = "Typically early-to-mid bull market"
        elif year < 2:
            phase_desc = "Post-halving Year 2: Peak territory or early correction"
            expected = "Watch for distribution signs, mid-cycle corrections common"
        elif year < 3:
            phase_desc = "Post-halving Year 3: Correction/consolidation period"
            expected = "Bear market or choppy consolidation typically in progress"
        else:
            phase_desc = "Pre-halving year: Accumulation phase building toward next cycle"
            expected = "Smart money accumulating, market resets before next halving catalyst"

        return {
            "days_since_halving": since,
            "years_into_cycle": round(year, 1),
            "phase_description": phase_desc,
            "expected_behavior": expected,
        }

    def evaluate_reflexivity_signals(self, snapshot):
        """Check for narrative shift / FUD exhaustion indicators."""
        fear = snapshot.sentiment.fear_greed_value
        mvrv = snapshot.valuation.mvrv_ratio

        # Check fear & greed trend (need historical snapshots)
        snapshots = self.db.get_snapshots(limit=30)
        if len(snapshots) >= 7:
            recent_fears = [s.sentiment.fear_greed_value for s in snapshots[:7]]
            avg_recent = sum(recent_fears) / len(recent_fears)
        else:
            avg_recent = fear

        if fear < 15 and avg_recent < 25:
            return {
                "state": ReflexivityState.FUD_EXHAUSTING,
                "detail": f"Sustained extreme fear (avg {avg_recent:.0f}) - FUD exhaustion building",
                "signal": SignalStatus.BULLISH,
            }
        elif fear < 30 and avg_recent < 35:
            return {
                "state": ReflexivityState.FUD_EXHAUSTING,
                "detail": f"Fear elevated (avg {avg_recent:.0f}) - selling pressure may be fading",
                "signal": SignalStatus.NEUTRAL,
            }
        elif fear > 75:
            return {
                "state": ReflexivityState.FUD_INTENSIFYING,
                "detail": "Extreme greed - reflexivity amplifying upside, reversal risk high",
                "signal": SignalStatus.BEARISH,
            }
        else:
            return {
                "state": ReflexivityState.NEUTRAL,
                "detail": f"Sentiment neutral (F&G: {fear})",
                "signal": SignalStatus.NEUTRAL,
            }

    def get_full_assessment(self, snapshot):
        """Combine all sub-evaluations into overall Nadeau view."""
        lth = self.evaluate_lth_proxy(snapshot)
        cycle = self.evaluate_cycle_position(snapshot)
        reflexivity = self.evaluate_reflexivity_signals(snapshot)

        signals = [lth, reflexivity]
        bullish = sum(1 for s in signals if s.get("signal") == SignalStatus.BULLISH)
        bearish = sum(1 for s in signals if s.get("signal") == SignalStatus.BEARISH)

        if bullish > bearish:
            overall = SignalStatus.BULLISH
        elif bearish > bullish:
            overall = SignalStatus.BEARISH
        else:
            overall = SignalStatus.NEUTRAL

        # Generate narrative
        parts = []
        parts.append(f"LTH Proxy: {lth['status'].value}. {lth['detail']}.")
        parts.append(f"Cycle: {cycle['phase_description']}")
        parts.append(f"Reflexivity: {reflexivity['state'].value}. {reflexivity['detail']}.")

        mvrv = snapshot.valuation.mvrv_ratio
        fear = snapshot.sentiment.fear_greed_value
        if overall == SignalStatus.BULLISH:
            parts.append("Overall: Conditions aligning for accumulation per Nadeau framework. Patience and DCA recommended.")
        elif overall == SignalStatus.BEARISH:
            parts.append("Overall: Distribution signals active. Risk management critical.")
        else:
            parts.append("Overall: Mixed signals. Monitor for directional shift.")

        return {
            "lth_proxy": lth,
            "cycle_position": cycle,
            "reflexivity": reflexivity,
            "overall_bias": overall,
            "confidence": "high" if abs(bullish - bearish) >= 2 else "medium" if bullish != bearish else "low",
            "narrative": " ".join(parts),
        }
