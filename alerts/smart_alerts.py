"""Smart alerts - friendly, proactive notifications in plain English."""
import logging
from datetime import datetime, timezone, date

logger = logging.getLogger("btcmonitor.alerts.smart")


class SmartAlertEngine:
    def __init__(self, db, config=None):
        self.db = db
        self.config = config or {}
        self.smart_config = self.config.get("smart_alerts", {})

    def check_all(self, snapshot, portfolios=None, goal_progress=None):
        """Run all smart alert checks and return list of messages."""
        messages = []

        if not self.smart_config.get("enabled", True):
            return messages

        if snapshot:
            msg = self.check_dca_reminder(snapshot, portfolios)
            if msg:
                messages.append(msg)

            msg = self.check_dip_opportunity(snapshot)
            if msg:
                messages.append(msg)

        if goal_progress:
            msg = self.check_milestone(goal_progress)
            if msg:
                messages.append(msg)

        if snapshot:
            msg = self.check_weekly_summary(snapshot, portfolios)
            if msg:
                messages.append(msg)

        if portfolios:
            msg = self.check_streak(portfolios)
            if msg:
                messages.append(msg)

        return messages

    def check_dca_reminder(self, snapshot, portfolios=None):
        """Generate a DCA buy reminder with current price context."""
        if not self.smart_config.get("dca_reminders", True):
            return None

        if not portfolios:
            return None

        for p in portfolios:
            amount = p.get("amount", 100)
            price = snapshot.price.price_usd
            if price <= 0:
                continue
            sats = int((amount / price) * 100_000_000)
            return {
                "type": "dca_reminder",
                "severity": "INFO",
                "title": "DCA Buy Reminder",
                "message": (
                    f"Time for your ${amount} DCA buy! "
                    f"BTC is at ${price:,.0f} -- you'll get about {sats:,} sats."
                ),
                "plain_english": (
                    f"Your regular ${amount} purchase would get you roughly "
                    f"{sats:,} satoshis at today's price of ${price:,.0f}."
                ),
            }
        return None

    def check_dip_opportunity(self, snapshot):
        """Alert when price has dropped significantly (DCA is working!)."""
        if not self.smart_config.get("dip_alerts", True):
            return None

        change = snapshot.price.change_24h_pct
        price = snapshot.price.price_usd

        if change is not None and change <= -5:
            return {
                "type": "dip_opportunity",
                "severity": "INFO",
                "title": "Price Dip -- Your DCA is Working",
                "message": (
                    f"BTC dropped {abs(change):.1f}% to ${price:,.0f}. "
                    f"Your DCA automatically buys more sats at lower prices -- "
                    f"this is the strategy working as designed!"
                ),
                "plain_english": (
                    f"Bitcoin is down {abs(change):.1f}% today. "
                    "This feels bad, but for DCA buyers it's actually good news: "
                    "your next buy gets you more Bitcoin for the same dollars."
                ),
            }
        return None

    def check_milestone(self, goal_progress):
        """Check for newly hit milestones."""
        if not self.smart_config.get("milestone_alerts", True):
            return None

        if not goal_progress:
            return None

        pct = goal_progress.get("pct_complete", 0)
        total_btc = goal_progress.get("total_btc", 0)

        # Check round BTC milestones
        btc_milestones = [0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
        for m in reversed(btc_milestones):
            if total_btc >= m:
                price = goal_progress.get("current_price", 0)
                usd_val = m * price
                return {
                    "type": "milestone",
                    "severity": "INFO",
                    "title": f"Milestone: {m} BTC!",
                    "message": (
                        f"You've stacked {m} BTC (worth ${usd_val:,.0f} today)! "
                        f"Keep going -- consistency wins."
                    ),
                    "plain_english": (
                        f"You've accumulated {m} Bitcoin! "
                        f"At today's price, that's worth ${usd_val:,.0f}. "
                        "Every sat counts."
                    ),
                }

        # Check percentage milestones
        pct_milestones = [25, 50, 75, 100]
        for p in reversed(pct_milestones):
            if pct >= p:
                return {
                    "type": "milestone",
                    "severity": "INFO",
                    "title": f"Goal Progress: {p}%!",
                    "message": f"You've reached {p}% of your goal! {'Almost there!' if p >= 75 else 'Great progress!'}",
                    "plain_english": f"You're {p}% of the way to your Bitcoin goal. {'The finish line is in sight!' if p >= 75 else 'Keep stacking!'}",
                }

        return None

    def check_weekly_summary(self, snapshot, portfolios=None):
        """Generate a weekly summary if it's the right day."""
        if not self.smart_config.get("weekly_summary", True):
            return None

        # Only generate on Sundays
        if date.today().weekday() != 6:
            return None

        price = snapshot.price.price_usd
        fg = snapshot.sentiment.fear_greed_value

        total_btc = 0
        total_invested = 0
        if portfolios:
            for p in portfolios:
                total_btc += p.get("total_btc", 0)
                total_invested += p.get("total_invested", 0)

        current_value = total_btc * price
        pnl = current_value - total_invested
        roi = (pnl / total_invested * 100) if total_invested > 0 else 0
        sats = int(total_btc * 100_000_000)

        roi_word = "up" if roi >= 0 else "down"
        msg_parts = [f"BTC is at ${price:,.0f}. Market mood: {fg}/100."]
        if total_invested > 0:
            msg_parts.append(
                f"Your stack: {sats:,} sats (${current_value:,.0f}, {roi_word} {abs(roi):.1f}%)."
            )

        return {
            "type": "weekly_summary",
            "severity": "INFO",
            "title": "Weekly Bitcoin Update",
            "message": " ".join(msg_parts),
            "plain_english": " ".join(msg_parts),
        }

    def check_streak(self, portfolios):
        """Check for DCA consistency streaks."""
        if not self.smart_config.get("streak_alerts", True):
            return None

        if not portfolios:
            return None

        # Count consecutive weeks with purchases across all portfolios
        all_dates = []
        for p in portfolios:
            purchases = p.get("purchases", [])
            if isinstance(purchases, list):
                for pu in purchases:
                    if isinstance(pu, dict) and "date" in pu:
                        all_dates.append(pu["date"])

        if not all_dates:
            return None

        # Count unique weeks
        weeks = set()
        for d in all_dates:
            try:
                if isinstance(d, str):
                    dt = date.fromisoformat(d)
                else:
                    dt = d
                weeks.add(dt.isocalendar()[1])
            except (ValueError, AttributeError):
                continue

        num_weeks = len(weeks)

        if num_weeks >= 4:
            streaks = [4, 8, 12, 26, 52]
            for s in reversed(streaks):
                if num_weeks >= s:
                    return {
                        "type": "streak",
                        "severity": "INFO",
                        "title": f"DCA Streak: {s}+ Weeks!",
                        "message": (
                            f"You've been DCA'ing for {num_weeks} weeks! "
                            "Consistency is the key to long-term success."
                        ),
                        "plain_english": (
                            f"You've stuck with your plan for {num_weeks} weeks straight. "
                            "That discipline is what separates successful investors from the rest."
                        ),
                    }

        return None
