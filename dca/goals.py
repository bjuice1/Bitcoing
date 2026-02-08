"""Goal tracker with milestones and projections."""
import logging
from datetime import date, datetime, timezone

logger = logging.getLogger("btcmonitor.dca.goals")

# Milestone definitions (fraction of target)
BTC_MILESTONES = [0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
PCT_MILESTONES = [10, 25, 50, 75, 90, 100]


class GoalTracker:
    def __init__(self, db):
        self.db = db

    def create_goal(self, name, target_btc=None, target_usd=None, monthly_dca=200, target_date=None):
        """Create a new accumulation goal."""
        if target_btc is None and target_usd is None:
            raise ValueError("Must set either target_btc or target_usd")

        self.db.conn.execute("""
            INSERT INTO goals (name, target_btc, target_usd, monthly_dca, target_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, target_btc, target_usd, monthly_dca,
              str(target_date) if target_date else None,
              datetime.now(timezone.utc).isoformat()))
        self.db.conn.commit()
        logger.info(f"Created goal '{name}': target_btc={target_btc}, target_usd={target_usd}")
        return self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_goal(self, goal_id=None):
        """Get a goal by ID, or the most recent goal if no ID given."""
        if goal_id:
            row = self.db.conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        else:
            row = self.db.conn.execute("SELECT * FROM goals ORDER BY created_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def list_goals(self):
        """List all goals."""
        rows = self.db.conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_progress(self, current_price, goal_id=None):
        """Calculate progress toward a goal using portfolio data."""
        goal = self.get_goal(goal_id)
        if not goal:
            return None

        # Aggregate all portfolio purchases
        portfolios = self.db.list_portfolios()
        total_btc = sum(p.get("total_btc", 0) for p in portfolios)
        total_invested = sum(p.get("total_invested", 0) for p in portfolios)
        current_value = total_btc * current_price

        # Determine progress percentage
        if goal["target_btc"]:
            target = goal["target_btc"]
            pct_complete = (total_btc / target * 100) if target > 0 else 0
            remaining = max(0, target - total_btc)
            remaining_str = f"{remaining:.8f} BTC"
        elif goal["target_usd"]:
            target = goal["target_usd"]
            pct_complete = (current_value / target * 100) if target > 0 else 0
            remaining = max(0, target - current_value)
            remaining_str = f"${remaining:,.0f}"
        else:
            pct_complete = 0
            remaining_str = "N/A"

        # Project months to completion at current DCA rate
        monthly_dca = goal["monthly_dca"] or 200
        if goal["target_btc"] and current_price > 0:
            btc_per_month = monthly_dca / current_price
            months_remaining = (remaining / btc_per_month) if btc_per_month > 0 else float("inf")
        elif goal["target_usd"]:
            # Rough estimate: assume price stays flat
            months_remaining = (remaining / monthly_dca) if monthly_dca > 0 else float("inf")
        else:
            months_remaining = float("inf")

        return {
            "goal": goal,
            "total_btc": total_btc,
            "total_invested": total_invested,
            "current_value": current_value,
            "pct_complete": min(pct_complete, 100),
            "remaining": remaining_str,
            "months_remaining": months_remaining if months_remaining != float("inf") else None,
            "monthly_dca": monthly_dca,
            "current_price": current_price,
        }

    def get_milestone_status(self, current_price, goal_id=None):
        """Check which milestones have been hit."""
        progress = self.get_progress(current_price, goal_id)
        if not progress:
            return []

        goal = progress["goal"]
        total_btc = progress["total_btc"]
        milestones = []

        # BTC milestones
        for m in BTC_MILESTONES:
            hit = total_btc >= m
            milestones.append({
                "type": "btc",
                "target": m,
                "label": f"{m} BTC",
                "hit": hit,
                "current": total_btc,
            })

        # Percentage milestones (of goal)
        pct = progress["pct_complete"]
        for p in PCT_MILESTONES:
            milestones.append({
                "type": "pct",
                "target": p,
                "label": f"{p}% of goal",
                "hit": pct >= p,
                "current": pct,
            })

        return milestones

    def get_celebration_messages(self, current_price, goal_id=None):
        """Get milestone celebration messages for milestones that have been hit."""
        milestones = self.get_milestone_status(current_price, goal_id)
        messages = []

        for m in milestones:
            if not m["hit"]:
                continue
            if m["type"] == "btc":
                btc_val = m["target"]
                usd_val = btc_val * current_price
                messages.append(
                    f"You've stacked {btc_val} BTC (worth ${usd_val:,.0f} today)!"
                )
            elif m["type"] == "pct":
                messages.append(
                    f"You've reached {m['target']}% of your goal!"
                )

        return messages

    def project_completion(self, current_price, goal_id=None):
        """Project when the goal will be reached under different scenarios."""
        progress = self.get_progress(current_price, goal_id)
        if not progress or not progress["goal"]["target_btc"]:
            return None

        from dca.projections import DCAProjector

        goal = progress["goal"]
        remaining_btc = max(0, goal["target_btc"] - progress["total_btc"])
        monthly_dca = goal["monthly_dca"] or 200

        if remaining_btc <= 0:
            return {"status": "complete", "message": "Goal already reached!"}

        scenarios = {}

        # Bear scenario: price drops 40%
        bear_price = current_price * 0.6
        btc_per_month_bear = monthly_dca / bear_price if bear_price > 0 else 0
        months_bear = (remaining_btc / btc_per_month_bear) if btc_per_month_bear > 0 else None
        scenarios["bear"] = {
            "label": "Bear (price -40%)",
            "price": bear_price,
            "months": round(months_bear) if months_bear else None,
            "note": "Lower prices = more BTC per buy = faster accumulation",
        }

        # Flat scenario
        btc_per_month_flat = monthly_dca / current_price if current_price > 0 else 0
        months_flat = (remaining_btc / btc_per_month_flat) if btc_per_month_flat > 0 else None
        scenarios["flat"] = {
            "label": "Flat (price unchanged)",
            "price": current_price,
            "months": round(months_flat) if months_flat else None,
        }

        # Bull scenario: price doubles
        bull_price = current_price * 2
        btc_per_month_bull = monthly_dca / bull_price if bull_price > 0 else 0
        months_bull = (remaining_btc / btc_per_month_bull) if btc_per_month_bull > 0 else None
        scenarios["bull"] = {
            "label": "Bull (price 2x)",
            "price": bull_price,
            "months": round(months_bull) if months_bull else None,
            "note": "Higher prices = less BTC per buy = slower accumulation (but your existing stack is worth more)",
        }

        # Generate monthly accumulation arrays for charting
        current_btc = progress["total_btc"]
        max_months = 72  # 6 years max
        for key, scenario in scenarios.items():
            price = scenario["price"]
            if price <= 0:
                scenario["monthly_btc_path"] = []
                continue
            btc_per_month = monthly_dca / price
            path = []
            cumulative = current_btc
            for m in range(max_months + 1):
                path.append(cumulative)
                cumulative += btc_per_month
            scenario["monthly_btc_path"] = path

        return {
            "status": "in_progress",
            "remaining_btc": remaining_btc,
            "current_btc": current_btc,
            "target_btc": goal["target_btc"],
            "monthly_dca": monthly_dca,
            "scenarios": scenarios,
        }
