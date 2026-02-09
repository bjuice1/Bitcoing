"""Action engine — distills all signals into a single directive."""
import logging
from dataclasses import dataclass, asdict
from typing import Optional

from utils.plain_english import get_traffic_light

logger = logging.getLogger("btcmonitor.action")


@dataclass
class ActionRecommendation:
    """Single action recommendation with context."""
    action: str           # STACK_HARD, BUY, HOLD, REDUCE, TAKE_PROFIT
    emoji: str
    headline: str         # One-line reason
    detail: str           # Paragraph with more context
    confidence: str       # high, medium, low
    plain_english: str    # Jargon-free version
    traffic_light: str    # GREEN, YELLOW, RED
    nadeau_bias: str      # BULLISH, NEUTRAL, BEARISH
    fear_greed: int
    drawdown_pct: float
    mvrv: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


class ActionEngine:
    """Distills all market signals into a single action recommendation."""

    def __init__(self, cycle_analyzer, monitor, goal_tracker=None):
        self.cycle = cycle_analyzer
        self.monitor = monitor
        self.goal_tracker = goal_tracker

    # ── core ─────────────────────────────────────────

    def get_action(self, snapshot, nadeau_signals=None, goal_progress=None) -> ActionRecommendation:
        """Compute the single recommended action."""
        if nadeau_signals is None:
            nadeau_signals = self.cycle.get_nadeau_signals(snapshot)

        light_data = get_traffic_light(snapshot, nadeau_signals)
        light = light_data["color"]

        overall = nadeau_signals.get("overall_bias", "NEUTRAL")
        bias = overall.value if hasattr(overall, "value") else str(overall)

        fear = snapshot.sentiment.fear_greed_value
        mvrv = snapshot.valuation.mvrv_ratio
        drawdown = self._get_drawdown()
        price = snapshot.price.price_usd

        # ── decision tree ──
        if light == "GREEN" and bias == "BULLISH" and fear < 15 and drawdown > 40:
            return self._make(
                "STACK_HARD", "\U0001f525", "high", light, bias, fear, drawdown, mvrv,
                headline="Extreme fear + deep drawdown. This is what DCA is for.",
                detail=(
                    "Multiple signals point to capitulation. Historically one of the "
                    "best accumulation windows. Consider increasing your DCA if your "
                    "budget allows — these conditions don't last."
                ),
                plain_english=(
                    f"Bitcoin is at ${price:,.0f}, down {drawdown:.0f}% from its peak, "
                    f"and almost everyone is panicking (fear index: {fear}/100). "
                    "Every past cycle, moments like this rewarded patient buyers. "
                    "If you can afford to, now is the time to buy extra."
                ),
            )

        if light == "GREEN" and bias == "BULLISH":
            return self._make(
                "BUY", "\u2705", "high", light, bias, fear, drawdown, mvrv,
                headline="Signals are bullish. Keep buying on schedule.",
                detail=(
                    "The Nadeau framework is leaning bullish and conditions favor "
                    "accumulation. Stick to your DCA — or add a little more if you're "
                    "comfortable."
                ),
                plain_english=(
                    f"Bitcoin is at ${price:,.0f}. The market is fearful but the "
                    "fundamentals look strong. Good time to keep buying regularly."
                ),
            )

        if light == "GREEN":
            return self._make(
                "BUY", "\u2705", "medium", light, bias, fear, drawdown, mvrv,
                headline="Conditions favor accumulation. Stay the course.",
                detail=(
                    "Overall signals are green. Not every indicator agrees, but the "
                    "weight of evidence supports continued DCA."
                ),
                plain_english=(
                    f"Bitcoin is at ${price:,.0f}. Things look generally favorable. "
                    "Keep buying your regular amount."
                ),
            )

        if light == "RED" and bias == "BEARISH" and mvrv is not None and mvrv > 3.5:
            return self._make(
                "TAKE_PROFIT", "\U0001f4b0", "high", light, bias, fear, drawdown, mvrv,
                headline="Multiple overheated signals. Consider taking some profit.",
                detail=(
                    f"MVRV is {mvrv:.1f} (historically overvalued), greed is high, and "
                    "Nadeau signals are bearish. Past cycles peaked under similar "
                    "conditions. Consider selling 10-20% to lock in gains."
                ),
                plain_english=(
                    f"Bitcoin is at ${price:,.0f} and the market looks overheated. "
                    "Historically, prices pulled back sharply from levels like this. "
                    "Consider selling a small portion to lock in your profits."
                ),
            )

        if light == "RED" and bias == "BEARISH":
            return self._make(
                "REDUCE", "\u26a0\ufe0f", "medium", light, bias, fear, drawdown, mvrv,
                headline="Overheated signals. Consider reducing exposure.",
                detail=(
                    "Multiple indicators are flashing caution. You don't need to sell "
                    "everything, but trimming your position or pausing DCA could "
                    "protect profits."
                ),
                plain_english=(
                    f"Bitcoin is at ${price:,.0f} and things look stretched. "
                    "It might be smart to slow down buying or take a small amount "
                    "off the table."
                ),
            )

        if light == "RED":
            return self._make(
                "HOLD", "\U0001f7e1", "medium", light, bias, fear, drawdown, mvrv,
                headline="Signals are cautious. Hold steady — don't add, don't panic.",
                detail=(
                    "The market looks heated but not all signals agree on direction. "
                    "Best to wait for clarity before making moves."
                ),
                plain_english=(
                    f"Bitcoin is at ${price:,.0f}. Things are uncertain. "
                    "Best to sit tight and wait for a clearer picture."
                ),
            )

        # YELLOW or fallback
        return self._make(
            "HOLD", "\u23f8\ufe0f", "medium", light, bias, fear, drawdown, mvrv,
            headline="Mixed signals. Stick to your regular DCA schedule.",
            detail=(
                "Some indicators are positive, others negative. This is normal. "
                "The best move in uncertain markets is consistency — keep your "
                "regular DCA amount and don't try to time it."
            ),
            plain_english=(
                f"Bitcoin is at ${price:,.0f}. Signals are mixed right now. "
                "Just keep doing what you're doing — regular buys, no changes."
            ),
        )

    # ── formatters ───────────────────────────────────

    def format_terminal(self, rec: ActionRecommendation) -> str:
        """Format for Rich terminal output."""
        action_colors = {
            "STACK_HARD": "bold white on #F7931A",
            "BUY": "bold white on #00B894",
            "HOLD": "bold white on #636E72",
            "REDUCE": "bold white on #FDCB6E",
            "TAKE_PROFIT": "bold white on #FF6B6B",
        }
        style = action_colors.get(rec.action, "bold")
        lines = [
            f"\n  [{style}]  {rec.emoji}  {rec.action}  [/{style}]  "
            f"[dim](confidence: {rec.confidence})[/dim]\n",
            f"  {rec.headline}\n",
            f"  [dim]{rec.detail}[/dim]\n",
            f"  [dim]Signal: {rec.traffic_light} | Bias: {rec.nadeau_bias} | "
            f"F&G: {rec.fear_greed} | Drawdown: {rec.drawdown_pct:.0f}%"
            + (f" | MVRV: {rec.mvrv:.2f}" if rec.mvrv else "") + "[/dim]",
        ]
        return "\n".join(lines)

    def format_plain(self, rec: ActionRecommendation) -> str:
        """Format as plain text (no Rich markup)."""
        lines = [
            f"{rec.emoji} {rec.action} (confidence: {rec.confidence})",
            "",
            rec.headline,
            "",
            rec.plain_english,
        ]
        return "\n".join(lines)

    def format_markdown(self, rec: ActionRecommendation) -> str:
        """Format as Markdown (for Telegram)."""
        lines = [
            f"{rec.emoji} *{rec.action}*  _{rec.confidence} confidence_",
            "",
            rec.headline,
            "",
            rec.plain_english,
            "",
            f"Signal: {rec.traffic_light} | Bias: {rec.nadeau_bias} | "
            f"F&G: {rec.fear_greed}/100",
        ]
        return "\n".join(lines)

    # ── helpers ──────────────────────────────────────

    def _get_drawdown(self) -> float:
        history = self.cycle.db.get_price_history()
        if not history:
            return 0.0
        ath = max(r["price_usd"] for r in history)
        current = history[-1]["price_usd"]
        return ((ath - current) / ath) * 100 if ath > 0 else 0.0

    def _make(self, action, emoji, confidence, light, bias, fear, drawdown, mvrv,
              headline, detail, plain_english):
        return ActionRecommendation(
            action=action, emoji=emoji, headline=headline, detail=detail,
            confidence=confidence, plain_english=plain_english,
            traffic_light=light, nadeau_bias=bias,
            fear_greed=fear, drawdown_pct=drawdown, mvrv=mvrv,
        )
