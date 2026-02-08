"""Weekly digest - automated summary with educational content."""
import logging
import random
from datetime import datetime, timezone, timedelta, date
from utils.plain_english import (
    explain_fear_greed, explain_mvrv, get_traffic_light,
    EDUCATIONAL_TOPICS,
)
from utils.formatters import format_usd, format_pct

logger = logging.getLogger("btcmonitor.digest")


class WeeklyDigest:
    def __init__(self, monitor, cycle_analyzer, alert_engine, nadeau_evaluator, db):
        self.monitor = monitor
        self.cycle = cycle_analyzer
        self.alert_engine = alert_engine
        self.nadeau = nadeau_evaluator
        self.db = db

    def generate(self, week_start=None, week_end=None):
        """Generate a weekly digest dict."""
        if week_end is None:
            week_end = date.today()
        if week_start is None:
            week_start = week_end - timedelta(days=7)

        snapshot = self.monitor.get_current_status()
        if not snapshot:
            return {"error": "No data available"}

        price = snapshot.price.price_usd
        fg = snapshot.sentiment.fear_greed_value
        mvrv = snapshot.valuation.mvrv_ratio

        # Price change over the week
        history = self.db.get_price_history(str(week_start), str(week_end))
        if len(history) >= 2:
            start_price = history[0]["price_usd"]
            end_price = history[-1]["price_usd"]
            week_change_pct = ((end_price - start_price) / start_price * 100) if start_price > 0 else 0
        else:
            start_price = price
            end_price = price
            week_change_pct = snapshot.price.change_24h_pct or 0

        # Recent alerts
        recent_alerts = self.db.get_recent_alerts(limit=10)
        week_alerts = [a for a in recent_alerts if a.get("triggered_at", "") >= str(week_start)]

        # Signal
        signals = self.cycle.get_nadeau_signals(snapshot)
        light = get_traffic_light(snapshot, signals)

        # Portfolio summary
        portfolios = self.db.list_portfolios()
        total_btc = sum(p.get("total_btc", 0) for p in portfolios)
        total_invested = sum(p.get("total_invested", 0) for p in portfolios)
        current_value = total_btc * price

        # Educational topic
        topic_idx = (week_end - date(2024, 1, 1)).days // 7
        topic = EDUCATIONAL_TOPICS[topic_idx % len(EDUCATIONAL_TOPICS)]

        # Halving info
        halving = self.cycle.get_halving_info()

        return {
            "period": f"{week_start} to {week_end}",
            "price": {
                "current": price,
                "week_start": start_price,
                "week_end": end_price,
                "change_pct": week_change_pct,
            },
            "signal": light,
            "mood": {
                "fear_greed": fg,
                "mvrv": mvrv,
                "explanation": explain_fear_greed(fg),
            },
            "alerts_this_week": len(week_alerts),
            "alert_summary": [a.get("message", "") for a in week_alerts[:5]],
            "portfolio": {
                "total_btc": total_btc,
                "total_invested": total_invested,
                "current_value": current_value,
                "pnl": current_value - total_invested,
                "roi_pct": ((current_value - total_invested) / total_invested * 100) if total_invested > 0 else 0,
            },
            "cycle": {
                "days_since_halving": halving["days_since"],
                "cycle_pct": halving["cycle_pct_elapsed"],
            },
            "education": topic,
        }

    def format_terminal(self, digest=None):
        """Format digest for terminal output using rich markup."""
        if digest is None:
            digest = self.generate()

        if "error" in digest:
            return f"[dim]{digest['error']}[/dim]"

        lines = []
        lines.append(f"[bold #F7931A]Weekly Bitcoin Digest[/bold #F7931A]")
        lines.append(f"[dim]{digest['period']}[/dim]\n")

        # Signal
        light = digest["signal"]
        color_map = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}
        c = color_map.get(light["color"], "white")
        lines.append(f"[bold {c}]Signal: {light['color']} -- {light['label']}[/bold {c}]")
        lines.append(f"{light['action']}\n")

        # Price
        p = digest["price"]
        change_c = "green" if p["change_pct"] >= 0 else "red"
        lines.append(f"[bold]Price:[/bold] ${p['current']:,.0f} ([{change_c}]{p['change_pct']:+.1f}% this week[/{change_c}])")

        # Mood
        lines.append(f"\n[bold]Market Mood:[/bold] {digest['mood']['fear_greed']}/100")
        lines.append(f"[dim]{digest['mood']['explanation']}[/dim]")

        # Portfolio
        port = digest["portfolio"]
        if port["total_invested"] > 0:
            roi_c = "green" if port["roi_pct"] >= 0 else "red"
            sats = int(port["total_btc"] * 100_000_000)
            lines.append(f"\n[bold]Your Stack:[/bold] {sats:,} sats (${port['current_value']:,.0f})")
            lines.append(f"Invested: ${port['total_invested']:,.0f} | [{roi_c}]P&L: {port['roi_pct']:+.1f}%[/{roi_c}]")

        # Alerts
        if digest["alerts_this_week"] > 0:
            lines.append(f"\n[bold]Alerts This Week:[/bold] {digest['alerts_this_week']}")
            for msg in digest["alert_summary"][:3]:
                lines.append(f"  [dim]{msg[:80]}[/dim]")

        # Cycle
        cy = digest["cycle"]
        lines.append(f"\n[bold]Cycle:[/bold] Day {cy['days_since_halving']} ({cy['cycle_pct']}% through)")

        # Education
        edu = digest["education"]
        lines.append(f"\n[bold #2196F3]Did You Know? {edu['title']}[/bold #2196F3]")
        # Show first paragraph only
        first_para = edu["content"].split("\n\n")[0]
        lines.append(f"[dim]{first_para}[/dim]")

        return "\n".join(lines)

    def format_html(self, digest=None):
        """Format digest as HTML for sharing."""
        if digest is None:
            digest = self.generate()

        if "error" in digest:
            return f"<p>{digest['error']}</p>"

        light = digest["signal"]
        light_colors = {
            "GREEN": ("#00C853", "#E8F5E9"),
            "YELLOW": ("#FFB300", "#FFF8E1"),
            "RED": ("#FF1744", "#FFEBEE"),
        }
        fg_color, bg_color = light_colors.get(light["color"], ("#888", "#F5F5F5"))

        p = digest["price"]
        port = digest["portfolio"]
        edu = digest["education"]

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Weekly Bitcoin Digest</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 16px; background: #FAFAFA; color: #333; line-height: 1.6; }}
h1 {{ color: #F7931A; text-align: center; }}
.signal {{ background: {bg_color}; border-left: 5px solid {fg_color}; padding: 16px; border-radius: 8px; margin: 16px 0; }}
.signal strong {{ color: {fg_color}; font-size: 18px; }}
.card {{ background: white; padding: 16px; border-radius: 8px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.card h2 {{ color: #F7931A; font-size: 16px; margin-bottom: 8px; }}
.learn {{ background: #E3F2FD; padding: 16px; border-radius: 8px; margin: 12px 0; }}
.learn h3 {{ color: #1565C0; }}
</style></head><body>
<h1>Weekly Bitcoin Digest</h1>
<p style="text-align:center;color:#888;">{digest['period']}</p>

<div class="signal"><strong>{light['color']} -- {light['label']}</strong><br>{light['action']}</div>

<div class="card"><h2>Price</h2>
<p>${p['current']:,.0f} ({p['change_pct']:+.1f}% this week)</p>
<p>Market mood: {digest['mood']['fear_greed']}/100</p></div>

{'<div class="card"><h2>Your Stack</h2><p>' + f"{int(port['total_btc']*1e8):,} sats (${port['current_value']:,.0f})" + f"<br>P&L: {port['roi_pct']:+.1f}%</p></div>" if port['total_invested'] > 0 else ""}

<div class="learn"><h3>{edu['title']}</h3><p>{edu['content'].split(chr(10)+chr(10))[0]}</p></div>

<p style="text-align:center;color:#AAA;font-size:12px;">Built for planning together</p>
</body></html>"""
