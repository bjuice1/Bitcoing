"""Static HTML report generator."""
import base64
import logging
from datetime import datetime
from pathlib import Path
from utils.formatters import format_usd, format_pct, format_hashrate

logger = logging.getLogger("btcmonitor.report")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bitcoin Cycle Report</title>
<style>
:root {{
    --bg: #1A1A2E;
    --card: #16213E;
    --text: #E0E0E0;
    --dim: #888;
    --orange: #F7931A;
    --green: #00C853;
    --red: #FF1744;
    --blue: #2196F3;
    --gold: #FFD700;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Courier New', monospace; padding: 20px; }}
h1 {{ color: var(--orange); text-align: center; margin-bottom: 5px; }}
.subtitle {{ text-align: center; color: var(--dim); margin-bottom: 30px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 20px; }}
.card {{ background: var(--card); border-radius: 8px; padding: 20px; border: 1px solid #333; }}
.card h2 {{ color: var(--orange); font-size: 16px; margin-bottom: 15px; border-bottom: 1px solid #333; padding-bottom: 8px; }}
.metric {{ display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #222; }}
.metric .label {{ color: var(--dim); }}
.metric .value {{ font-weight: bold; }}
.up {{ color: var(--green); }}
.down {{ color: var(--red); }}
.neutral {{ color: var(--gold); }}
.signal-row {{ display: flex; justify-content: space-between; padding: 6px 0; }}
.signal-name {{ color: var(--dim); }}
.bullish {{ color: var(--green); font-weight: bold; }}
.bearish {{ color: var(--red); font-weight: bold; }}
.chart-container {{ text-align: center; margin: 15px 0; }}
.chart-container img {{ max-width: 100%; border-radius: 4px; }}
.narrative {{ background: #0D1117; padding: 15px; border-radius: 4px; font-style: italic; color: var(--dim); line-height: 1.6; margin-top: 15px; }}
footer {{ text-align: center; color: var(--dim); margin-top: 30px; font-size: 12px; }}
</style>
</head>
<body>
<h1>Bitcoin Cycle Report</h1>
<p class="subtitle">Generated: {generated_at}</p>

<div class="grid">
<div class="card">
<h2>Price Overview</h2>
{price_section}
</div>

<div class="card">
<h2>Onchain Metrics</h2>
{metrics_section}
</div>

<div class="card">
<h2>Cycle Position</h2>
{cycle_section}
</div>

<div class="card">
<h2>Nadeau Signals</h2>
{signals_section}
</div>

<div class="card">
<h2>Alerts</h2>
{alerts_section}
</div>

<div class="card">
<h2>DCA Status</h2>
{dca_section}
</div>
</div>

{charts_section}

<div class="narrative">
{narrative}
</div>

<footer>
Data sources: CoinGecko, Blockchain.com, mempool.space, alternative.me, CoinMetrics<br>
Methodology: Michael Nadeau / The DeFi Report framework (proxy-based signals)
</footer>
</body>
</html>"""


class HTMLReportGenerator:
    def __init__(self, monitor, cycle_analyzer, alert_engine, nadeau_evaluator, dca_engine=None):
        self.monitor = monitor
        self.cycle = cycle_analyzer
        self.alerts = alert_engine
        self.nadeau = nadeau_evaluator
        self.dca = dca_engine

    def generate(self, output_path="data/btc_report.html"):
        snapshot = self.monitor.get_current_status()
        summary = self.monitor.get_key_metrics_summary()
        halving = self.cycle.get_halving_info()
        drawdown = self.cycle.get_drawdown_analysis()
        cycle_phase = self.cycle.get_cycle_phase(snapshot)
        signals = self.cycle.get_nadeau_signals(snapshot)
        nadeau = self.nadeau.get_full_assessment(snapshot)
        recent_alerts = self.monitor.db.get_recent_alerts(limit=10)

        # Price section
        p = snapshot.price
        chg_class = "up" if p.change_24h_pct >= 0 else "down"
        price_html = f"""
        <div class="metric"><span class="label">Price</span><span class="value">{format_usd(p.price_usd)}</span></div>
        <div class="metric"><span class="label">24h Change</span><span class="value {chg_class}">{format_pct(p.change_24h_pct)}</span></div>
        <div class="metric"><span class="label">Market Cap</span><span class="value">{format_usd(p.market_cap, compact=True)}</span></div>
        <div class="metric"><span class="label">Volume</span><span class="value">{format_usd(p.volume_24h, compact=True)}</span></div>
        <div class="metric"><span class="label">ATH</span><span class="value">{format_usd(summary['ath_price'])}</span></div>
        <div class="metric"><span class="label">Drawdown</span><span class="value down">{summary['drawdown_from_ath_pct']:.1f}%</span></div>
        """

        # Metrics section
        o = snapshot.onchain
        metrics_html = f"""
        <div class="metric"><span class="label">Network HR</span><span class="value">{format_hashrate(o.hash_rate_th)}</span></div>
        <div class="metric"><span class="label">Difficulty Adj</span><span class="value">{format_pct(o.difficulty_change_pct)}</span></div>
        <div class="metric"><span class="label">F&G Index</span><span class="value">{snapshot.sentiment.fear_greed_value} ({snapshot.sentiment.fear_greed_label})</span></div>
        <div class="metric"><span class="label">MVRV</span><span class="value">{f'{snapshot.valuation.mvrv_ratio:.2f}' if snapshot.valuation.mvrv_ratio else 'N/A'}</span></div>
        <div class="metric"><span class="label">BTC/Gold</span><span class="value">{snapshot.sentiment.btc_gold_ratio:.1f} oz</span></div>
        <div class="metric"><span class="label">Dominance</span><span class="value">{snapshot.sentiment.btc_dominance_pct:.1f}%</span></div>
        """

        # Cycle section
        phase_val = cycle_phase["phase"].value if hasattr(cycle_phase["phase"], 'value') else str(cycle_phase["phase"])
        cycle_html = f"""
        <div class="metric"><span class="label">Phase</span><span class="value">{phase_val} ({cycle_phase['confidence']})</span></div>
        <div class="metric"><span class="label">Days Since Halving</span><span class="value">{halving['days_since']}</span></div>
        <div class="metric"><span class="label">Days Until Next</span><span class="value">{halving['days_until']}</span></div>
        <div class="metric"><span class="label">Cycle Progress</span><span class="value">{halving['cycle_pct_elapsed']}%</span></div>
        <div class="metric"><span class="label">Block Reward</span><span class="value">{halving['current_block_reward']} BTC</span></div>
        """

        # Signals section
        signals_html = ""
        for name, status, value, interp in signals.get("signals", []):
            s = status.value if hasattr(status, 'value') else str(status)
            cls = s.lower()
            signals_html += f'<div class="signal-row"><span class="signal-name">{name}</span><span class="{cls}">{s}</span></div>\n'
        overall = signals.get("overall_bias", "NEUTRAL")
        o_str = overall.value if hasattr(overall, 'value') else str(overall)
        signals_html += f'<div class="signal-row"><span class="signal-name"><strong>OVERALL</strong></span><span class="{o_str.lower()}"><strong>{o_str}</strong></span></div>'

        # Alerts section
        if recent_alerts:
            alerts_html = "".join(
                f'<div class="metric"><span class="label">[{a.get("severity", "?")}]</span><span class="value">{a.get("rule_name", "")}</span></div>'
                for a in recent_alerts[:5]
            )
        else:
            alerts_html = '<div class="metric"><span class="up">All clear - no alerts</span></div>'

        # DCA section
        dca_html = '<div class="metric"><span class="label">No portfolio configured</span></div>'

        # Narrative
        narrative = nadeau.get("narrative", "No assessment available.") if nadeau else "Assessment unavailable."

        html = HTML_TEMPLATE.format(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            price_section=price_html,
            metrics_section=metrics_html,
            cycle_section=cycle_html,
            signals_section=signals_html,
            alerts_section=alerts_html,
            dca_section=dca_html,
            charts_section="",
            narrative=narrative,
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)

        logger.info(f"HTML report saved to {output_path}")
        return output_path
