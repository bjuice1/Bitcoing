"""Couple-friendly HTML report -- simplified, mobile-friendly, no jargon."""
import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from utils.plain_english import (
    explain_fear_greed, explain_mvrv, explain_drawdown,
    explain_hash_rate, explain_cycle_phase, get_traffic_light,
    EDUCATIONAL_TOPICS,
)

logger = logging.getLogger("btcmonitor.dashboard.couples_report")


class CouplesReportGenerator:
    def __init__(self, monitor, cycle_analyzer, alert_engine, nadeau_evaluator):
        self.monitor = monitor
        self.cycle = cycle_analyzer
        self.alert_engine = alert_engine
        self.nadeau = nadeau_evaluator

    def generate(self, output_path="data/couples_report.html", goal_progress=None, monthly_dca=200):
        """Generate a couple-friendly HTML report."""
        snapshot = self.monitor.get_current_status()
        if not snapshot:
            logger.warning("No data available for couples report")
            return None

        halving = self.cycle.get_halving_info()
        phase = self.cycle.get_cycle_phase(snapshot)
        signals = self.cycle.get_nadeau_signals(snapshot)
        light = get_traffic_light(snapshot, signals)

        price = snapshot.price.price_usd
        fg = snapshot.sentiment.fear_greed_value
        mvrv = snapshot.valuation.mvrv_ratio
        diff_change = snapshot.onchain.difficulty_change_pct
        dominance = snapshot.sentiment.btc_dominance_pct

        # Compute drawdown
        drawdown_pct = 0
        history = self.monitor.db.get_price_history()
        ath = 0
        if history:
            ath = max(r["price_usd"] for r in history)
            if ath > 0:
                drawdown_pct = ((ath - price) / ath) * 100

        # Sats per buy
        sats_per_buy = int((monthly_dca / price) * 100_000_000) if price > 0 else 0

        # Traffic light colors
        light_colors = {
            "GREEN": ("#00C853", "#E8F5E9"),
            "YELLOW": ("#FFB300", "#FFF8E1"),
            "RED": ("#FF1744", "#FFEBEE"),
        }
        fg_color, bg_color = light_colors.get(light["color"], ("#888", "#F5F5F5"))

        # Phase name
        phase_name = phase["phase"].name if hasattr(phase["phase"], "name") else str(phase["phase"])

        # Goal section
        goal_html = ""
        if goal_progress:
            pct = goal_progress.get("pct_complete", 0)
            total_btc = goal_progress.get("total_btc", 0)
            current_value = goal_progress.get("current_value", 0)
            remaining = goal_progress.get("remaining", "N/A")
            months = goal_progress.get("months_remaining")
            months_str = f"~{months:.0f} months" if months and months < 999 else "calculating..."

            goal_html = f"""
            <div class="section">
                <h2>Our DCA Progress</h2>
                <div class="progress-container">
                    <div class="progress-bar" style="width: {min(pct, 100):.0f}%"></div>
                </div>
                <p class="progress-label">{pct:.1f}% of goal reached</p>
                <div class="stats-grid">
                    <div class="stat">
                        <div class="stat-value">{total_btc:.6f}</div>
                        <div class="stat-label">BTC Stacked</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">${current_value:,.0f}</div>
                        <div class="stat-label">Current Value</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{remaining}</div>
                        <div class="stat-label">Remaining</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{months_str}</div>
                        <div class="stat-label">Est. Time Left</div>
                    </div>
                </div>
            </div>
            """

        # Generate charts for embedding
        chart_html = self._generate_embedded_charts(price, snapshot, halving, goal_progress, monthly_dca)

        # Pick a fun fact based on day of year
        day_of_year = datetime.now().timetuple().tm_yday
        topic = EDUCATIONAL_TOPICS[day_of_year % len(EDUCATIONAL_TOPICS)]

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Our Bitcoin Update</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #FAFAFA; color: #333; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; max-width: 600px; margin: 0 auto; line-height: 1.6; }}
h1 {{ text-align: center; color: #333; margin-bottom: 5px; font-size: 24px; }}
.subtitle {{ text-align: center; color: #888; margin-bottom: 20px; font-size: 14px; }}
.traffic-light {{ background: {bg_color}; border-left: 6px solid {fg_color}; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
.traffic-light .signal {{ font-size: 20px; font-weight: bold; color: {fg_color}; margin-bottom: 5px; }}
.traffic-light .action {{ font-size: 16px; color: #555; }}
.section {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.section h2 {{ color: #F7931A; font-size: 18px; margin-bottom: 12px; }}
.section p {{ margin-bottom: 10px; color: #555; }}
.bullet {{ padding: 8px 0; border-bottom: 1px solid #F0F0F0; }}
.bullet:last-child {{ border-bottom: none; }}
.bullet strong {{ color: #333; }}
.stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }}
.stat {{ text-align: center; padding: 12px; background: #F8F9FA; border-radius: 8px; }}
.stat-value {{ font-size: 20px; font-weight: bold; color: #333; }}
.stat-label {{ font-size: 12px; color: #888; margin-top: 4px; }}
.strategy {{ background: #FFF8E1; padding: 16px; border-radius: 8px; }}
.strategy strong {{ color: #F7931A; }}
.fun-fact {{ background: #E3F2FD; padding: 16px; border-radius: 8px; }}
.fun-fact h3 {{ color: #1565C0; margin-bottom: 8px; }}
.fun-fact p {{ color: #555; font-size: 14px; }}
.progress-container {{ width: 100%; background: #E0E0E0; border-radius: 10px; height: 20px; margin: 10px 0; }}
.progress-bar {{ height: 100%; background: linear-gradient(90deg, #F7931A, #FFB300); border-radius: 10px; min-width: 5px; }}
.progress-label {{ text-align: center; color: #888; font-size: 14px; }}
footer {{ text-align: center; color: #AAA; margin-top: 20px; font-size: 12px; }}
</style>
</head>
<body>

<h1>Our Bitcoin Update</h1>
<p class="subtitle">Generated: {now_str} UTC</p>

<div class="traffic-light">
    <div class="signal">{light['color']} -- {light['label']}</div>
    <div class="action">{light['action']}</div>
</div>

<div class="section">
    <h2>This Week in Bitcoin</h2>
    <div class="bullet"><strong>Price:</strong> ${price:,.0f} ({"up" if snapshot.price.change_24h_pct >= 0 else "down"} {abs(snapshot.price.change_24h_pct):.1f}% today)</div>
    <div class="bullet"><strong>Market Mood:</strong> {fg}/100 -- {"everyone is scared (good for buyers)" if fg < 25 else "people are nervous" if fg < 45 else "neutral" if fg < 55 else "people are greedy (be careful)" if fg < 75 else "extreme greed (danger zone)"}</div>
    <div class="bullet"><strong>From All-Time High:</strong> {drawdown_pct:.0f}% below ${ath:,.0f}</div>
    <div class="bullet"><strong>Cycle Position:</strong> Day {halving['days_since']} of 4-year cycle ({halving['cycle_pct_elapsed']}% through)</div>
</div>

{goal_html}

<div class="section">
    <h2>What We're Doing</h2>
    <div class="strategy">
        <p><strong>Our Strategy:</strong> Invest ${monthly_dca}/month in Bitcoin via DCA (Dollar Cost Averaging).</p>
        <p>At today's price, each ${monthly_dca} buy gets us about <strong>{sats_per_buy:,} sats</strong>.</p>
    </div>
</div>

<div class="section">
    <h2>The Big Picture</h2>
    <p>{explain_cycle_phase(phase_name, halving['days_since'], halving['cycle_pct_elapsed'])}</p>
</div>

{chart_html}

<div class="section">
    <h2>Did You Know?</h2>
    <div class="fun-fact">
        <h3>{topic['title']}</h3>
        <p>{topic['content'].replace(chr(10), '<br>')}</p>
    </div>
</div>

<footer>
    Data sources: CoinGecko, Blockchain.com, mempool.space, alternative.me<br>
    Built with love for long-term planning together
</footer>

</body>
</html>"""

        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)

        logger.info(f"Couples report saved to {output_path}")
        return output_path

    def _generate_embedded_charts(self, price, snapshot, halving, goal_progress, monthly_dca):
        """Generate charts and return HTML with embedded base64 images."""
        try:
            from dca.charts import DCAChartGenerator
            from dca.projections import DCAProjector
            from utils.constants import KEY_LEVELS, HALVING_DATES
            import tempfile

            gen = DCAChartGenerator(output_dir=tempfile.mkdtemp())
            sections = []

            # Scenario fan chart
            try:
                projector = DCAProjector(price)
                projections = projector.compare_projections(monthly_dca)
                next_halving = HALVING_DATES.get(5)
                fan_path = gen.plot_scenario_fan(price, projections, monthly_dca, KEY_LEVELS, next_halving)
                if fan_path:
                    img_b64 = self._encode_image(fan_path)
                    sections.append(f"""
<div class="section">
    <h2>Where Could Bitcoin Go?</h2>
    <img src="data:image/png;base64,{img_b64}" style="width:100%;border-radius:8px;" alt="Scenario fan chart">
    <p style="font-size:12px;color:#888;margin-top:8px;">Shows possible price paths over the next 1-3 years under different scenarios.</p>
</div>""")
            except Exception as e:
                logger.debug(f"Failed to generate fan chart for report: {e}")

            # Goal timeline chart
            if goal_progress:
                try:
                    from dca.goals import GoalTracker
                    goal_proj = None
                    if hasattr(self, '_goal_tracker'):
                        goal_proj = self._goal_tracker.project_completion(price)
                    # Build minimal projections from goal_progress if no tracker
                    if not goal_proj and goal_progress.get("goal", {}).get("target_btc"):
                        target_btc = goal_progress["goal"]["target_btc"]
                        current_btc = goal_progress.get("total_btc", 0)
                        remaining = max(0, target_btc - current_btc)
                        if remaining > 0:
                            scenarios = {}
                            for label, multiplier in [("bear", 0.6), ("flat", 1.0), ("bull", 2.0)]:
                                p = price * multiplier
                                btc_per_month = monthly_dca / p if p > 0 else 0
                                months = int(remaining / btc_per_month) if btc_per_month > 0 else 999
                                path = []
                                cumulative = current_btc
                                for m in range(min(months + 1, 73)):
                                    path.append(cumulative)
                                    cumulative += btc_per_month
                                scenarios[label] = {"price": p, "months": months, "monthly_btc_path": path,
                                                   "label": f"{label.title()} (${p:,.0f})"}
                            goal_proj = {"status": "in_progress", "target_btc": target_btc,
                                        "current_btc": current_btc, "monthly_dca": monthly_dca,
                                        "scenarios": scenarios}

                    if goal_proj and goal_proj.get("status") == "in_progress":
                        goal_path = gen.plot_goal_timeline(goal_proj)
                        if goal_path:
                            img_b64 = self._encode_image(goal_path)
                            sections.append(f"""
<div class="section">
    <h2>Our Path to the Goal</h2>
    <img src="data:image/png;base64,{img_b64}" style="width:100%;border-radius:8px;" alt="Goal timeline chart">
    <p style="font-size:12px;color:#888;margin-top:8px;">In bear markets you accumulate faster because each dollar buys more Bitcoin.</p>
</div>""")
                except Exception as e:
                    logger.debug(f"Failed to generate goal chart for report: {e}")

            return "\n".join(sections)
        except Exception as e:
            logger.debug(f"Chart generation failed for couples report: {e}")
            return ""

    @staticmethod
    def _encode_image(path):
        """Read an image file and return base64 string."""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
