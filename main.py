#!/usr/bin/env python3
"""Bitcoin Cycle Monitor - CLI Entry Point."""
import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import click
from rich.console import Console
from rich.table import Table

from __version__ import __version__

console = Console()


def _init_components(config_path=None, verbose=False):
    """Lazy initialization of all components."""
    from utils.logger import setup_logging
    from config import load_config
    from models.database import Database
    from monitor.api import APIRegistry
    from monitor.monitor import BitcoinMonitor
    from monitor.cycle import CycleAnalyzer
    from alerts.rules_manager import RulesManager
    from alerts.engine import AlertEngine
    from alerts.channels import ConsoleChannel, FileChannel, DesktopChannel
    from alerts.nadeau_signals import NadeauSignalEvaluator
    from dca.portfolio import PortfolioTracker

    setup_logging("DEBUG" if verbose else "INFO")
    config = load_config(config_path)

    db_path = config["database"]["path"]
    db = Database(db_path)
    db.connect()

    api = APIRegistry(config)
    monitor = BitcoinMonitor(db, api, config)
    cycle = CycleAnalyzer(db)

    rules = RulesManager("config/alerts_rules.yaml")
    channels = [FileChannel()]  # Always log to file

    # Console only if running interactively (not from launchd)
    if sys.stdout.isatty():
        channels.append(ConsoleChannel())

    # Desktop notifications
    if config.get("notifications", {}).get("enabled", True):
        channels.append(DesktopChannel(config))

    # Email for CRITICAL alerts
    if config.get("email", {}).get("critical_alerts_enabled", False):
        from alerts.channels import EmailChannel
        channels.append(EmailChannel(config))

    alert_engine = AlertEngine(rules, db, channels)

    nadeau = NadeauSignalEvaluator(db)
    dca_tracker = PortfolioTracker(db)

    from dca.goals import GoalTracker
    goal_tracker = GoalTracker(db)

    # Telegram (optional)
    telegram_bot = None
    tg_config = config.get("telegram", {})
    if tg_config.get("enabled") and tg_config.get("bot_token"):
        from notifications.telegram_bot import TelegramBot
        from alerts.telegram_channel import TelegramChannel
        telegram_bot = TelegramBot(tg_config["bot_token"], tg_config["chat_id"])
        if tg_config.get("critical_alerts", True):
            channels.append(TelegramChannel(
                telegram_bot,
                min_severity=tg_config.get("min_alert_severity", "WARNING"),
            ))

    return {
        "config": config, "db": db, "api": api, "monitor": monitor,
        "cycle": cycle, "alert_engine": alert_engine, "nadeau": nadeau,
        "dca_tracker": dca_tracker, "rules": rules, "goal_tracker": goal_tracker,
        "telegram_bot": telegram_bot,
    }


@click.group()
@click.option("--config", "config_path", default=None, help="Path to config YAML")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.version_option(__version__, prog_name="btcmonitor")
@click.pass_context
def cli(ctx, config_path, verbose):
    """Bitcoin Cycle Monitor - Onchain metrics, DCA simulation, alerts & dashboard."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["verbose"] = verbose


def _get_components(ctx):
    if "_components" not in ctx.obj:
        ctx.obj["_components"] = _init_components(ctx.obj.get("config_path"), ctx.obj.get("verbose"))
    return ctx.obj["_components"]


# ──────────────────────────────────────────────────────
# SETUP
# ──────────────────────────────────────────────────────
@cli.command()
@click.pass_context
def setup(ctx):
    """First-time setup: initialize DB, test APIs, fetch initial data."""
    c = _get_components(ctx)
    console.print("[bold #F7931A]Bitcoin Cycle Monitor - Setup[/bold #F7931A]\n")

    # DB init
    console.print("[green]✓[/green] Database initialized")

    # API health check
    console.print("Testing API connectivity...")
    health = c["api"].health_check()
    for name, info in health.items():
        status = "[green]✓[/green]" if info["reachable"] else "[red]✗[/red]"
        console.print(f"  {status} {name} ({info['latency_ms']}ms)")

    # Initial fetch
    console.print("\nFetching initial metrics...")
    try:
        snapshot = c["monitor"].fetch_and_store()
        console.print(f"[green]✓[/green] BTC: ${snapshot.price.price_usd:,.2f}")
    except Exception as e:
        console.print(f"[red]✗[/red] Fetch failed: {e}")

    console.print("\n[bold]Setup complete![/bold] Run [bold]python main.py dashboard[/bold] to start monitoring.")
    console.print("First time? Try [bold]python main.py onboard[/bold] for guided setup.\n")


# ──────────────────────────────────────────────────────
# ONBOARD
# ──────────────────────────────────────────────────────
@cli.command()
@click.pass_context
def onboard(ctx):
    """Interactive first-time setup wizard. Configures everything step by step."""
    c = _get_components(ctx)
    from config.onboarding import OnboardingWizard

    wizard = OnboardingWizard(
        db=c["db"],
        monitor=c["monitor"],
        goal_tracker=c["goal_tracker"],
        portfolio_tracker=c["dca_tracker"],
        config=c["config"],
    )
    user_config = wizard.run()

    # If Telegram was requested, prompt for setup
    if user_config.get("telegram", {}).get("enabled"):
        console.print("\n[bold]Let's set up Telegram...[/bold]")
        ctx.invoke(telegram_setup)

    # Show first action recommendation
    from utils.action_engine import ActionEngine
    snapshot = c["monitor"].get_current_status()
    if snapshot:
        signals = c["cycle"].get_nadeau_signals(snapshot)
        engine = ActionEngine(c["cycle"], c["monitor"], c["goal_tracker"])
        rec = engine.get_action(snapshot, signals)
        console.print("\n[bold #F7931A]Your First Action Recommendation[/bold #F7931A]")
        console.print(engine.format_terminal(rec))


# ──────────────────────────────────────────────────────
# QUICK
# ──────────────────────────────────────────────────────
@cli.command()
@click.pass_context
def quick(ctx):
    """Print single-line status summary."""
    c = _get_components(ctx)
    from dashboard.app import Dashboard
    dash = Dashboard(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"], c["dca_tracker"], c["config"])
    console.print(dash.quick_status())


# ──────────────────────────────────────────────────────
# CYCLE
# ──────────────────────────────────────────────────────
@cli.command()
@click.pass_context
def cycle(ctx):
    """Show full cycle analysis with Nadeau signals."""
    c = _get_components(ctx)
    snapshot = c["monitor"].get_current_status()

    # Halving info
    halving = c["cycle"].get_halving_info()
    console.print("\n[bold #F7931A]Halving Cycle[/bold #F7931A]")
    table = Table(show_header=False, box=None)
    table.add_column("", style="dim")
    table.add_column("")
    for k, v in halving.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)

    # Phase
    phase = c["cycle"].get_cycle_phase(snapshot)
    phase_str = phase["phase"].value if hasattr(phase["phase"], 'value') else str(phase["phase"])
    console.print(f"\n[bold]Cycle Phase:[/bold] {phase_str} (confidence: {phase['confidence']})")

    # Drawdown
    dd = c["cycle"].get_drawdown_analysis()
    console.print(f"[bold]Drawdown:[/bold] {dd['current_drawdown_pct']}% from ATH ({dd['vs_average']})")

    # Nadeau signals
    signals = c["cycle"].get_nadeau_signals(snapshot)
    console.print("\n[bold #F7931A]Nadeau Signals[/bold #F7931A]")
    sig_table = Table(show_header=True, box=None)
    sig_table.add_column("Signal", style="dim")
    sig_table.add_column("Status")
    sig_table.add_column("Value")
    sig_table.add_column("Interpretation")
    for name, status, value, interp in signals["signals"]:
        s = status.value if hasattr(status, 'value') else str(status)
        c_map = {"BULLISH": "green", "BEARISH": "red", "NEUTRAL": "yellow"}
        sig_table.add_row(name, f"[{c_map.get(s, 'white')}]{s}[/{c_map.get(s, 'white')}]",
                         f"{value:.2f}" if isinstance(value, (int, float)) and value is not None else "N/A", interp)
    console.print(sig_table)

    overall = signals["overall_bias"]
    o_str = overall.value if hasattr(overall, 'value') else str(overall)
    console.print(f"\n[bold]Overall Bias:[/bold] {o_str} ({signals['bullish_count']}B/{signals['bearish_count']}Be)")

    # Nadeau narrative
    nadeau = c["nadeau"].get_full_assessment(snapshot)
    if nadeau:
        console.print(f"\n[dim italic]{nadeau['narrative']}[/dim italic]")


# ──────────────────────────────────────────────────────
# MONITOR
# ──────────────────────────────────────────────────────
@cli.group()
def monitor():
    """Monitor Bitcoin metrics."""
    pass


@monitor.command("fetch")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", is_flag=True, help="No output, just save")
@click.pass_context
def monitor_fetch(ctx, as_json, quiet):
    """Fetch current metrics from all APIs."""
    c = _get_components(ctx)
    snapshot = c["monitor"].fetch_and_store()
    if quiet:
        return
    if as_json:
        import json
        console.print(json.dumps(snapshot.to_dict(), indent=2, default=str))
    else:
        console.print(f"[bold #F7931A]BTC[/bold #F7931A] ${snapshot.price.price_usd:,.2f} "
                      f"({snapshot.price.change_24h_pct:+.2f}%)")
        console.print(f"  Market Cap: ${snapshot.price.market_cap:,.0f}")
        console.print(f"  F&G: {snapshot.sentiment.fear_greed_value} ({snapshot.sentiment.fear_greed_label})")
        console.print(f"  MVRV: {snapshot.valuation.mvrv_ratio or 'N/A'}")
        console.print(f"  Network HR: {snapshot.onchain.hash_rate_th:.2e} TH/s")
        console.print(f"  Dominance: {snapshot.sentiment.btc_dominance_pct:.1f}%")
        console.print(f"  BTC/Gold: {snapshot.sentiment.btc_gold_ratio:.1f} oz")


@monitor.command("backfill")
@click.option("--full", is_flag=True, help="Full backfill from 2013 using multiple sources (slower)")
@click.option("--start-year", default=2013, type=int, help="Start year for backfill")
@click.pass_context
def monitor_backfill(ctx, full, start_year):
    """Backfill historical daily price data."""
    c = _get_components(ctx)

    if full:
        console.print(f"[bold #F7931A]Full backfill from {start_year}[/bold #F7931A]")
        console.print("Sources: CoinGecko (recent) + Yahoo Finance (2014+) + seed CSV (2013)\n")

        from rich.progress import Progress
        with Progress() as progress:
            task = progress.add_task("Backfilling...", total=None)

            def cb(added, total):
                progress.update(task, completed=added, total=total)

            result = c["monitor"].backfill_history(start_year=start_year, full=True, progress_callback=cb)

        console.print(f"\n[green]✓[/green] Added {result.dates_added} days")
        console.print(f"  Range: {result.date_range[0]} to {result.date_range[1]}")
        console.print(f"  Sources: {', '.join(result.sources_used) or 'none needed (already complete)'}")
        if result.gaps_remaining:
            console.print(f"  [yellow]{len(result.gaps_remaining)} gap(s) remain[/yellow]")
        if result.errors:
            for err in result.errors:
                console.print(f"  [red]{err}[/red]")
    else:
        console.print(f"Backfilling price history (last 365 days via CoinGecko)...")
        count = c["monitor"].backfill_history(start_year=start_year, full=False)
        console.print(f"[green]✓[/green] Backfilled {count} daily price records")
        console.print("[dim]Tip: Use --full for complete history from 2013[/dim]")


@monitor.command("status")
@click.pass_context
def monitor_status(ctx):
    """Show latest stored metrics."""
    c = _get_components(ctx)
    summary = c["monitor"].get_key_metrics_summary()

    table = Table(title="Bitcoin Metrics", show_header=True)
    table.add_column("Metric", style="dim")
    table.add_column("Value")

    from utils.formatters import format_usd, format_pct, format_hashrate
    rows = [
        ("Price", format_usd(summary["price_usd"])),
        ("24h Change", format_pct(summary["change_24h_pct"])),
        ("Market Cap", format_usd(summary["market_cap"], compact=True)),
        ("Volume 24h", format_usd(summary["volume_24h"], compact=True)),
        ("Network HR", format_hashrate(summary["hash_rate_th"])),
        ("F&G Index", f"{summary['fear_greed_value']} ({summary['fear_greed_label']})"),
        ("MVRV", f"{summary['mvrv_ratio']:.2f}" if summary['mvrv_ratio'] else "N/A"),
        ("BTC/Gold", f"{summary['btc_gold_ratio']:.1f} oz"),
        ("Dominance", f"{summary['btc_dominance_pct']:.1f}%"),
        ("ATH Drawdown", f"{summary['drawdown_from_ath_pct']:.1f}%"),
        ("Days Since Halving", str(summary["days_since_halving"])),
        ("Days Until Halving", str(summary["days_until_halving"])),
        ("Block Reward", f"{summary['block_reward']} BTC"),
    ]
    for name, val in rows:
        table.add_row(name, val)
    console.print(table)


@monitor.command("history")
@click.option("--metric", default="price_usd", help="Metric column name")
@click.option("--days", default=30, help="Number of days")
@click.pass_context
def monitor_history(ctx, metric, days):
    """Show metric history as sparkline."""
    c = _get_components(ctx)
    from dashboard.widgets import sparkline
    data = c["monitor"].get_metric_history(metric, days)
    if not data:
        console.print("[dim]No historical data. Run backfill first.[/dim]")
        return
    values = [v for _, v in data]
    console.print(f"[bold]{metric}[/bold] ({days}d): {sparkline(values, width=40)}")
    console.print(f"  Latest: {values[-1]:,.2f}  Min: {min(values):,.2f}  Max: {max(values):,.2f}")


# ──────────────────────────────────────────────────────
# DCA
# ──────────────────────────────────────────────────────
@cli.group()
def dca():
    """DCA simulation and portfolio tracking."""
    pass


@dca.command("simulate")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", default=None, help="End date (default: today)")
@click.option("--amount", default=100, type=float, help="USD per buy")
@click.option("--frequency", default="weekly", type=click.Choice(["daily", "weekly", "biweekly", "monthly"]))
@click.option("--chart", is_flag=True, help="Generate equity curve chart")
@click.pass_context
def dca_simulate(ctx, start, end, amount, frequency, chart):
    """Run a DCA backtesting simulation."""
    c = _get_components(ctx)
    from dca.engine import DCAEngine
    engine = DCAEngine(c["db"])

    try:
        result = engine.simulate(start, end, amount, frequency)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[dim]Tip: Run 'python main.py monitor backfill' first to get price data.[/dim]")
        return

    from utils.formatters import format_usd, format_pct, format_btc
    table = Table(title=f"DCA Simulation: {start} to {end or 'today'}", show_header=True)
    table.add_column("Metric", style="dim")
    table.add_column("Value")

    roi_color = "green" if result.roi_pct >= 0 else "red"
    table.add_row("Total Invested", format_usd(result.total_invested))
    table.add_row("Current Value", format_usd(result.current_value))
    table.add_row("ROI", f"[{roi_color}]{format_pct(result.roi_pct)}[/{roi_color}]")
    table.add_row("BTC Accumulated", format_btc(result.total_btc))
    table.add_row("Avg Cost Basis", format_usd(result.avg_cost_basis))
    table.add_row("# Buys", str(result.num_buys))
    table.add_row("Best Buy Price", format_usd(result.best_buy_price))
    table.add_row("Worst Buy Price", format_usd(result.worst_buy_price))
    table.add_row("Max Drawdown", format_pct(result.max_drawdown_pct))
    console.print(table)

    if chart:
        from dca.charts import DCAChartGenerator
        gen = DCAChartGenerator()
        path = gen.plot_dca_equity_curve(result)
        if path:
            console.print(f"[green]Chart saved:[/green] {path}")


@dca.command("compare")
@click.option("--start", required=True, help="Start date")
@click.option("--end", default=None, help="End date")
@click.option("--total", default=10000, type=float, help="Total USD to invest")
@click.option("--frequency", default="weekly")
@click.pass_context
def dca_compare(ctx, start, end, total, frequency):
    """Compare DCA vs lump sum investment."""
    c = _get_components(ctx)
    from dca.engine import DCAEngine
    from utils.formatters import format_usd, format_pct
    engine = DCAEngine(c["db"])

    try:
        comp = engine.compare_to_lumpsum(start, end, total, frequency)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    table = Table(title="DCA vs Lump Sum", show_header=True)
    table.add_column("", style="dim")
    table.add_column("DCA")
    table.add_column("Lump Sum")

    table.add_row("Invested", format_usd(comp.dca_result.total_invested), format_usd(comp.lumpsum_invested))
    table.add_row("Value", format_usd(comp.dca_result.current_value), format_usd(comp.lumpsum_value))
    table.add_row("ROI", format_pct(comp.dca_result.roi_pct), format_pct(comp.lumpsum_roi_pct))

    adv = comp.dca_advantage_pct
    adv_str = f"DCA {'wins' if adv > 0 else 'loses'} by {abs(adv):.1f}%"
    table.add_row("Advantage", adv_str, "")
    console.print(table)


@dca.command("project")
@click.option("--monthly-dca", default=200, type=float, help="Monthly DCA amount")
@click.pass_context
def dca_project(ctx, monthly_dca):
    """Show forward DCA projection scenarios."""
    c = _get_components(ctx)
    from dca.projections import DCAProjector
    from utils.formatters import format_usd, format_pct

    snapshot = c["monitor"].get_current_status()
    price = snapshot.price.price_usd if snapshot else 70000

    proj = DCAProjector(price)
    scenarios = proj.compare_projections(monthly_dca)

    table = Table(title=f"DCA Projections (${monthly_dca}/mo from ${price:,.0f})", show_header=True)
    table.add_column("Scenario", style="dim")
    table.add_column("Target")
    table.add_column("Months")
    table.add_column("Total Invested")
    table.add_column("Final Value")
    table.add_column("ROI")

    for name, s in scenarios.items():
        if name == "full_cycle":
            continue
        roi_c = "green" if s["roi_pct"] >= 0 else "red"
        table.add_row(name.replace("_", " ").title(),
                     format_usd(s.get("target_price", 0)),
                     str(s["months"]),
                     format_usd(s["total_invested"]),
                     format_usd(s["final_value"]),
                     f"[{roi_c}]{format_pct(s['roi_pct'])}[/{roi_c}]")
    console.print(table)


@dca.group("portfolio")
def dca_portfolio():
    """Manage DCA portfolios."""
    pass


@dca_portfolio.command("create")
@click.option("--name", required=True, help="Portfolio name")
@click.option("--amount", default=100, type=float, help="USD per buy")
@click.option("--frequency", default="weekly")
@click.pass_context
def portfolio_create(ctx, name, amount, frequency):
    """Create a new DCA portfolio."""
    c = _get_components(ctx)
    pid = c["dca_tracker"].create_portfolio(name, frequency, amount)
    console.print(f"[green]✓[/green] Created portfolio '{name}' (id={pid}, ${amount}/{frequency})")


@dca_portfolio.command("buy")
@click.option("--id", "pid", required=True, type=int, help="Portfolio ID")
@click.option("--price", required=True, type=float, help="Buy price in USD")
@click.option("--date", "buy_date", default=None, help="Purchase date (default: today)")
@click.pass_context
def portfolio_buy(ctx, pid, price, buy_date):
    """Record a purchase."""
    c = _get_components(ctx)
    from datetime import date
    d = date.fromisoformat(buy_date) if buy_date else date.today()
    btc = c["dca_tracker"].record_purchase(pid, d, price)
    console.print(f"[green]✓[/green] Bought {btc:.8f} BTC at ${price:,.2f}")


@dca_portfolio.command("status")
@click.option("--id", "pid", required=True, type=int, help="Portfolio ID")
@click.pass_context
def portfolio_status(ctx, pid):
    """Show portfolio performance."""
    c = _get_components(ctx)
    snapshot = c["monitor"].get_current_status()
    price = snapshot.price.price_usd if snapshot else 70000
    status = c["dca_tracker"].get_portfolio_status(pid, price)
    if not status:
        console.print("[red]Portfolio not found[/red]")
        return

    from utils.formatters import format_usd, format_pct, format_btc
    table = Table(title=f"Portfolio: {status['name']}", show_header=False)
    table.add_column("", style="dim")
    table.add_column("")

    roi_c = "green" if status["roi_pct"] >= 0 else "red"
    table.add_row("Invested", format_usd(status["total_invested"]))
    table.add_row("Value", format_usd(status["current_value"]))
    table.add_row("P&L", f"[{roi_c}]{format_usd(status['pnl_usd'])} ({format_pct(status['roi_pct'])})[/{roi_c}]")
    table.add_row("BTC Held", format_btc(status["total_btc"]))
    table.add_row("Avg Cost", format_usd(status["avg_cost_basis"]))
    table.add_row("Purchases", str(status["num_purchases"]))
    console.print(table)


@dca_portfolio.command("list")
@click.pass_context
def portfolio_list(ctx):
    """List all portfolios."""
    c = _get_components(ctx)
    portfolios = c["dca_tracker"].list_portfolios()
    if not portfolios:
        console.print("[dim]No portfolios. Create one with: dca portfolio create --name Main[/dim]")
        return
    table = Table(title="DCA Portfolios", show_header=True)
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Frequency")
    table.add_column("Amount")
    table.add_column("Purchases")
    table.add_column("Total Invested")
    table.add_column("Total BTC")
    for p in portfolios:
        table.add_row(str(p["id"]), p["name"], p["frequency"],
                     f"${p['amount']}", str(p["num_purchases"]),
                     f"${p['total_invested']:,.2f}", f"{p['total_btc']:.8f}")
    console.print(table)


# ──────────────────────────────────────────────────────
# ALERTS
# ──────────────────────────────────────────────────────
@cli.group()
def alerts():
    """Alert management."""
    pass


@alerts.command("check")
@click.pass_context
def alerts_check(ctx):
    """Evaluate all enabled alert rules against latest data."""
    c = _get_components(ctx)
    snapshot = c["monitor"].get_current_status()
    triggered = c["alert_engine"].check(snapshot)
    if triggered:
        console.print(f"[bold yellow]{len(triggered)} alert(s) triggered:[/bold yellow]")
        for a in triggered:
            console.print(f"  [{a.severity}] {a.message}")
    else:
        console.print("[green]All clear - no alerts triggered[/green]")


@alerts.command("test")
@click.pass_context
def alerts_test(ctx):
    """Test all rules (ignore cooldowns) against latest data."""
    c = _get_components(ctx)
    snapshot = c["monitor"].get_current_status()
    results = c["alert_engine"].test_rules(snapshot)

    table = Table(title="Alert Rules Test", show_header=True)
    table.add_column("Rule")
    table.add_column("Metric")
    table.add_column("Condition")
    table.add_column("Current")
    table.add_column("Would Fire")
    table.add_column("Enabled")

    for r in results:
        fire_str = "[green]YES[/green]" if r["would_fire"] else "[dim]no[/dim]"
        en_str = "✓" if r["enabled"] else "✗"
        val = f"{r['current_value']:.2f}" if r["current_value"] is not None else "N/A"
        table.add_row(r["name"], r["metric"], f"{r['operator']} {r['threshold']}",
                     val, fire_str, en_str)
    console.print(table)


@alerts.command("history")
@click.option("--days", default=7, help="Days to look back")
@click.pass_context
def alerts_history(ctx, days):
    """Show past alerts."""
    c = _get_components(ctx)
    recent = c["db"].get_recent_alerts(limit=days * 24)
    if not recent:
        console.print("[dim]No alerts in history[/dim]")
        return
    table = Table(title=f"Alert History (last {days}d)", show_header=True)
    table.add_column("Time", style="dim")
    table.add_column("Severity")
    table.add_column("Rule")
    table.add_column("Message")
    for a in recent[:50]:
        table.add_row(a["triggered_at"][:16], a["severity"], a["rule_name"], (a["message"] or "")[:60])
    console.print(table)


@alerts.command("rules")
@click.pass_context
def alerts_rules(ctx):
    """List all configured alert rules."""
    c = _get_components(ctx)
    rules = c["rules"].get_all_rules()
    table = Table(title="Alert Rules", show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Condition")
    table.add_column("Severity")
    table.add_column("Enabled")
    for r in rules:
        table.add_row(r.id, r.name, f"{r.metric} {r.operator} {r.threshold}", r.severity,
                     "[green]✓[/green]" if r.enabled else "[red]✗[/red]")
    console.print(table)

    composites = c["rules"].get_composites()
    if composites:
        console.print("\n[bold]Composite Signals:[/bold]")
        for comp in composites:
            console.print(f"  {comp.name}: {' AND '.join(comp.required_rules)} → [{comp.severity}]")


# ──────────────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────────────
@cli.command()
@click.option("--port", default=5000, type=int, help="Port to bind to")
@click.option("--host", default="0.0.0.0", type=str, help="Host to bind to")
@click.pass_context
def web(ctx, port, host):
    """Launch the web dashboard."""
    from web.app import create_app
    import socket

    c = _get_components(ctx)
    from utils.action_engine import ActionEngine
    action_engine = ActionEngine(c["cycle"], c["monitor"], c["goal_tracker"])

    engines = {
        "monitor": c["monitor"],
        "cycle": c["cycle"],
        "alert_engine": c["alert_engine"],
        "nadeau": c["nadeau"],
        "action_engine": action_engine,
        "db": c["db"],
        "dca_portfolio": c["dca_tracker"],
        "goal_tracker": c["goal_tracker"],
    }

    app = create_app(c["config"], engines)

    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"

    console.print(f"\n[bold #F7931A]Bitcoin Cycle Monitor -- Web Dashboard[/bold #F7931A]\n")
    console.print(f"  Local:    http://localhost:{port}")
    console.print(f"  Network:  http://{local_ip}:{port}")
    console.print(f"  Partner:  http://{local_ip}:{port}/partner")
    console.print(f"\n  Press Ctrl+C to stop.\n")

    app.run(host=host, port=port, debug=False)


@cli.command()
@click.option("--refresh", default=60, type=int, help="Refresh interval in seconds")
@click.pass_context
def dashboard(ctx, refresh):
    """Launch the terminal dashboard."""
    c = _get_components(ctx)
    c["config"]["dashboard"] = c["config"].get("dashboard", {})
    c["config"]["dashboard"]["refresh_interval"] = refresh

    from dashboard.app import Dashboard
    dash = Dashboard(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"],
                    c["dca_tracker"], c["config"])
    dash.run()


# ──────────────────────────────────────────────────────
# REPORT
# ──────────────────────────────────────────────────────
@cli.command()
@click.option("--output", default=None, help="Output path")
@click.option("--open", "open_browser", is_flag=True, help="Open in browser")
@click.option("--couples", is_flag=True, help="Generate couple-friendly report")
@click.option("--monthly", default=200, type=float, help="Monthly DCA amount (for couples report)")
@click.pass_context
def report(ctx, output, open_browser, couples, monthly):
    """Generate an HTML report."""
    c = _get_components(ctx)

    if couples:
        from dashboard.couples_report import CouplesReportGenerator
        gen = CouplesReportGenerator(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"])
        snapshot = c["monitor"].get_current_status()
        price = snapshot.price.price_usd if snapshot else 70000
        goal_progress = c["goal_tracker"].get_progress(price)
        out = output or "data/couples_report.html"
        path = gen.generate(out, goal_progress=goal_progress, monthly_dca=monthly)
    else:
        from dashboard.html_report import HTMLReportGenerator
        gen = HTMLReportGenerator(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"])
        out = output or "data/btc_report.html"
        path = gen.generate(out)

    console.print(f"[green]✓[/green] Report saved to {path}")
    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(path)}")


# ──────────────────────────────────────────────────────
# EXPORT
# ──────────────────────────────────────────────────────
@cli.command()
@click.option("--format", "fmt", default="csv", type=click.Choice(["csv", "json"]))
@click.option("--days", default=30, type=int, help="Days to export")
@click.option("--output", default=None, help="Output file path")
@click.pass_context
def export(ctx, fmt, days, output):
    """Export metrics data."""
    c = _get_components(ctx)
    from dashboard.app import Dashboard
    dash = Dashboard(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"],
                    c["dca_tracker"], c["config"])
    if output is None:
        output = f"data/export_{days}d.{fmt}"
    path = dash.export_history(days, output)
    if path:
        console.print(f"[green]✓[/green] Exported to {path}")
    else:
        console.print("[dim]No data to export[/dim]")


# ──────────────────────────────────────────────────────
# SIMPLE (Plain English)
# ──────────────────────────────────────────────────────
@cli.command()
@click.option("--for-two", is_flag=True, help="Add couple-friendly framing")
@click.option("--monthly", default=200, type=float, help="Your monthly DCA amount")
@click.pass_context
def simple(ctx, for_two, monthly):
    """Plain English summary -- no jargon, just what you need to know."""
    c = _get_components(ctx)
    from utils.plain_english import explain_overall_signal, get_couple_framing

    snapshot = c["monitor"].get_current_status()
    if not snapshot:
        console.print("[dim]No data yet. Run: python main.py setup[/dim]")
        return

    signals = c["cycle"].get_nadeau_signals(snapshot)
    halving = c["cycle"].get_halving_info()
    phase = c["cycle"].get_cycle_phase(snapshot)

    cycle_info = {"phase": phase, "halving": halving}
    summary = explain_overall_signal(snapshot, signals, cycle_info, monthly_dca=monthly)

    if for_two:
        summary = get_couple_framing(summary)

    console.print(summary)


# ──────────────────────────────────────────────────────
# ACTION (What Should I Do?)
# ──────────────────────────────────────────────────────
@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--plain", is_flag=True, help="Plain text (no Rich formatting)")
@click.pass_context
def action(ctx, as_json, plain):
    """What should I do? ONE clear action based on all signals."""
    c = _get_components(ctx)
    from utils.action_engine import ActionEngine
    import json as jsonlib

    snapshot = c["monitor"].get_current_status()
    if not snapshot:
        console.print("[dim]No data yet. Run: python main.py setup[/dim]")
        return

    signals = c["cycle"].get_nadeau_signals(snapshot)
    price = snapshot.price.price_usd
    goal_progress = None
    try:
        goal_progress = c["goal_tracker"].get_progress(price)
    except Exception:
        pass

    engine = ActionEngine(c["cycle"], c["monitor"], c["goal_tracker"])
    rec = engine.get_action(snapshot, signals, goal_progress)

    if as_json:
        console.print(jsonlib.dumps(rec.to_dict(), indent=2, default=str))
    elif plain:
        console.print(engine.format_plain(rec))
    else:
        console.print(engine.format_terminal(rec))


# ──────────────────────────────────────────────────────
# GOAL
# ──────────────────────────────────────────────────────
@cli.group()
def goal():
    """Set and track your Bitcoin accumulation goals."""
    pass


@goal.command("set")
@click.option("--name", required=True, help="Goal name (e.g., 'Our BTC Fund')")
@click.option("--target-btc", type=float, default=None, help="Target BTC amount")
@click.option("--target-usd", type=float, default=None, help="Target USD value")
@click.option("--monthly", default=200, type=float, help="Monthly DCA amount")
@click.pass_context
def goal_set(ctx, name, target_btc, target_usd, monthly):
    """Set a new accumulation goal."""
    if not target_btc and not target_usd:
        console.print("[red]Specify --target-btc or --target-usd[/red]")
        return
    c = _get_components(ctx)
    gid = c["goal_tracker"].create_goal(name, target_btc=target_btc, target_usd=target_usd, monthly_dca=monthly)
    target_str = f"{target_btc} BTC" if target_btc else f"${target_usd:,.0f}"
    console.print(f"[green]Goal set![/green] '{name}' -- target: {target_str} at ${monthly}/month (id={gid})")


@goal.command("status")
@click.option("--id", "goal_id", default=None, type=int, help="Goal ID (default: latest)")
@click.pass_context
def goal_status(ctx, goal_id):
    """Show progress toward your goal."""
    c = _get_components(ctx)
    snapshot = c["monitor"].get_current_status()
    price = snapshot.price.price_usd if snapshot else 70000

    progress = c["goal_tracker"].get_progress(price, goal_id)
    if not progress:
        console.print("[dim]No goals set. Run: python main.py goal set --name 'Our Fund' --target-btc 0.1 --monthly 200[/dim]")
        return

    from utils.formatters import format_usd, format_btc
    g = progress["goal"]
    console.print(f"\n[bold #F7931A]Goal: {g['name']}[/bold #F7931A]")

    target_str = f"{g['target_btc']} BTC" if g["target_btc"] else format_usd(g["target_usd"])
    console.print(f"Target: {target_str} | DCA: ${g['monthly_dca']}/month\n")

    # Progress bar
    pct = progress["pct_complete"]
    bar_len = 30
    filled = int(bar_len * pct / 100)
    bar = "[green]" + "█" * filled + "[/green]" + "[dim]░[/dim]" * (bar_len - filled)
    console.print(f"  {bar} {pct:.1f}%\n")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("", style="dim", width=16)
    table.add_column("")
    table.add_row("BTC Stacked", format_btc(progress["total_btc"]))
    table.add_row("Current Value", format_usd(progress["current_value"]))
    table.add_row("Total Invested", format_usd(progress["total_invested"]))
    table.add_row("Remaining", progress["remaining"])
    if progress["months_remaining"]:
        table.add_row("Est. Time Left", f"~{progress['months_remaining']:.0f} months at current price")
    console.print(table)

    # Projections
    projections = c["goal_tracker"].project_completion(price, goal_id)
    if projections and projections["status"] == "in_progress":
        console.print(f"\n[bold]Completion Projections:[/bold]")
        for key, scenario in projections["scenarios"].items():
            months = scenario.get("months")
            if months:
                console.print(f"  {scenario['label']}: ~{months} months (${scenario['price']:,.0f}/BTC)")
            if "note" in scenario:
                console.print(f"    [dim]{scenario['note']}[/dim]")


@goal.command("celebrate")
@click.pass_context
def goal_celebrate(ctx):
    """Show all milestones you've hit!"""
    c = _get_components(ctx)
    snapshot = c["monitor"].get_current_status()
    price = snapshot.price.price_usd if snapshot else 70000

    messages = c["goal_tracker"].get_celebration_messages(price)
    if not messages:
        console.print("[dim]No milestones yet -- keep stacking![/dim]")
        return

    console.print("[bold #F7931A]Your Milestones[/bold #F7931A]\n")
    for msg in messages:
        console.print(f"  [green]★[/green] {msg}")


# ──────────────────────────────────────────────────────
# DIGEST
# ──────────────────────────────────────────────────────
@cli.command()
@click.option("--html", "as_html", is_flag=True, help="Output as HTML file")
@click.pass_context
def digest(ctx, as_html):
    """Generate your weekly Bitcoin digest."""
    c = _get_components(ctx)
    from digest.weekly_digest import WeeklyDigest
    wd = WeeklyDigest(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"], c["db"])

    if as_html:
        html = wd.format_html()
        path = "data/weekly_digest.html"
        with open(path, "w") as f:
            f.write(html)
        console.print(f"[green]Digest saved to {path}[/green]")
    else:
        console.print(wd.format_terminal())


# ──────────────────────────────────────────────────────
# LEARN
# ──────────────────────────────────────────────────────
@cli.command()
@click.option("--topic", default=None, type=int, help="Topic number (1-8)")
@click.option("--list", "list_topics", is_flag=True, help="List all topics")
@click.pass_context
def learn(ctx, topic, list_topics):
    """Learn about Bitcoin concepts -- one topic at a time."""
    from utils.plain_english import EDUCATIONAL_TOPICS

    if list_topics:
        console.print("[bold #F7931A]Available Topics[/bold #F7931A]\n")
        for i, t in enumerate(EDUCATIONAL_TOPICS, 1):
            console.print(f"  {i}. {t['title']}")
        console.print(f"\n[dim]Run: python main.py learn --topic 1[/dim]")
        return

    if topic is not None:
        idx = topic - 1
        if 0 <= idx < len(EDUCATIONAL_TOPICS):
            t = EDUCATIONAL_TOPICS[idx]
        else:
            console.print(f"[red]Topic must be 1-{len(EDUCATIONAL_TOPICS)}[/red]")
            return
    else:
        import random
        t = random.choice(EDUCATIONAL_TOPICS)

    console.print(f"\n[bold #2196F3]{t['title']}[/bold #2196F3]\n")
    console.print(t["content"])
    console.print(f"\n[dim]({len(EDUCATIONAL_TOPICS)} topics available -- run 'learn --list' to see all)[/dim]")


# ──────────────────────────────────────────────────────
# CHARTS
# ──────────────────────────────────────────────────────
@cli.command()
@click.option("--fan", is_flag=True, help="Scenario fan chart only")
@click.option("--cycles", is_flag=True, help="Cycle overlay chart only")
@click.option("--goal-chart", is_flag=True, help="Goal timeline chart only")
@click.option("--levels", is_flag=True, help="Price levels chart only")
@click.option("--open", "open_files", is_flag=True, help="Open charts after generating")
@click.option("--monthly", default=200, type=float, help="Monthly DCA amount for projections")
@click.pass_context
def charts(ctx, fan, cycles, goal_chart, levels, open_files, monthly):
    """Generate visual timeline charts (scenario fan, cycle overlay, goal path, price levels)."""
    c = _get_components(ctx)
    from dca.charts import DCAChartGenerator
    from dca.projections import DCAProjector
    from utils.constants import KEY_LEVELS, REFERENCE_COST_BASES, HALVING_DATES

    gen = DCAChartGenerator()

    # Fresh price fetch for chart accuracy
    console.print("[dim]Fetching latest price...[/dim]")
    try:
        snapshot = c["monitor"].fetch_and_store()
        price = snapshot.price.price_usd
        change = snapshot.price.change_24h_pct
        console.print(f"[bold #F7931A]BTC ${price:,.0f}[/bold #F7931A] ({change:+.1f}%)\n")
    except Exception:
        snapshot = c["monitor"].get_current_status()
        price = snapshot.price.price_usd if snapshot else 70000
        console.print(f"[bold #F7931A]BTC ${price:,.0f}[/bold #F7931A] (cached)\n")

    halving = c["cycle"].get_halving_info()

    generate_all = not (fan or cycles or goal_chart or levels)
    generated = []

    # 1. Scenario Fan
    if fan or generate_all:
        projector = DCAProjector(price)
        projections = projector.compare_projections(monthly)
        next_halving = HALVING_DATES.get(5)
        path = gen.plot_scenario_fan(price, projections, monthly, KEY_LEVELS, next_halving)
        if path:
            generated.append(path)
            console.print(f"  [green]✓[/green] Scenario fan: {path}")

    # 2. Cycle Overlay
    if cycles or generate_all:
        price_history = c["db"].get_price_history()
        path = gen.plot_cycle_overlay(price_history, halving, price)
        if path:
            generated.append(path)
            console.print(f"  [green]✓[/green] Cycle overlay: {path}")

    # 3. Goal Timeline
    if goal_chart or generate_all:
        goal_proj = c["goal_tracker"].project_completion(price)
        if goal_proj and goal_proj.get("status") == "in_progress":
            path = gen.plot_goal_timeline(goal_proj)
            if path:
                generated.append(path)
                console.print(f"  [green]✓[/green] Goal timeline: {path}")
        else:
            console.print("  [dim]No active goal. Set one: python main.py goal set --name 'Fund' --target-btc 0.1[/dim]")

    # 4. Price Levels
    if levels or generate_all:
        price_history = c["db"].get_price_history()
        if price_history:
            path = gen.plot_price_with_levels(price_history, price, KEY_LEVELS, REFERENCE_COST_BASES)
            if path:
                generated.append(path)
                console.print(f"  [green]✓[/green] Price levels: {path}")
        else:
            console.print("  [dim]No price history. Run: python main.py monitor backfill[/dim]")

    if not generated:
        console.print("[dim]No charts generated. Need data first.[/dim]")
    else:
        console.print(f"\n[bold]{len(generated)} chart(s) ready[/bold] — price as of {datetime.now().strftime('%H:%M:%S')}")
        if open_files:
            import subprocess
            for p in generated:
                subprocess.Popen(["open", p])


# ──────────────────────────────────────────────────────
# TELEGRAM
# ──────────────────────────────────────────────────────
@cli.group()
def telegram():
    """Telegram bot setup and notifications."""
    pass


@telegram.command("setup")
@click.pass_context
def telegram_setup(ctx):
    """Interactive Telegram bot setup wizard."""
    from rich.prompt import Prompt, Confirm
    import yaml
    from pathlib import Path

    console.print("\n[bold #F7931A]Telegram Bot Setup[/bold #F7931A]\n")
    console.print("1. Open Telegram, search for [bold]@BotFather[/bold]")
    console.print("2. Send [bold]/newbot[/bold] and follow the prompts")
    console.print("3. Copy the bot token below\n")

    token = Prompt.ask("Bot token")
    if not token:
        console.print("[red]No token provided.[/red]")
        return

    # Verify token
    from notifications.telegram_bot import TelegramBot
    try:
        bot = TelegramBot(token, "0")
        info = bot.verify_token()
        bot_name = info.get("result", {}).get("username", "unknown")
        console.print(f"[green]✓[/green] Verified: @{bot_name}\n")
    except Exception as e:
        console.print(f"[red]Token verification failed: {e}[/red]")
        return

    console.print("Now get your chat ID:")
    console.print("1. Open Telegram, search for [bold]@userinfobot[/bold]")
    console.print("2. Send [bold]/start[/bold] — it will reply with your ID\n")

    chat_id = Prompt.ask("Chat ID")
    if not chat_id:
        console.print("[red]No chat ID provided.[/red]")
        return

    # Test send
    bot = TelegramBot(token, chat_id)
    try:
        bot.send_message("\u2705 Bitcoin Cycle Monitor connected! You'll receive weekly digests and alerts here.")
        console.print("[green]✓[/green] Test message sent!\n")
    except Exception as e:
        console.print(f"[red]Send failed: {e}[/red]")
        return

    # Save to user_config.yaml
    user_config_path = Path("config/user_config.yaml")
    user_config = {}
    if user_config_path.exists():
        with open(user_config_path) as f:
            user_config = yaml.safe_load(f) or {}
    user_config["telegram"] = {
        "enabled": True,
        "bot_token": token,
        "chat_id": chat_id,
        "weekly_digest": True,
        "action_alerts": True,
        "critical_alerts": True,
        "min_alert_severity": "WARNING",
    }
    with open(user_config_path, "w") as f:
        yaml.dump(user_config, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]✓[/green] Config saved to {user_config_path}")
    console.print("[dim]Restart commands to pick up Telegram integration.[/dim]")


@telegram.command("test")
@click.pass_context
def telegram_test(ctx):
    """Send a test message to verify Telegram setup."""
    c = _get_components(ctx)
    bot = c.get("telegram_bot")
    if not bot:
        console.print("[red]Telegram not configured. Run: python main.py telegram setup[/red]")
        return
    try:
        bot.send_message("\u2705 Bitcoin Cycle Monitor test — Telegram is working!")
        console.print("[green]Test message sent![/green]")
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")


@telegram.command("send-digest")
@click.pass_context
def telegram_send_digest(ctx):
    """Send the weekly digest via Telegram now."""
    c = _get_components(ctx)
    bot = c.get("telegram_bot")
    if not bot:
        console.print("[red]Telegram not configured. Run: python main.py telegram setup[/red]")
        return
    from digest.weekly_digest import WeeklyDigest
    wd = WeeklyDigest(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"], c["db"])
    digest_data = wd.generate()
    bot.send_weekly_digest(digest_data)
    console.print("[green]Digest sent via Telegram![/green]")


@telegram.command("send-action")
@click.pass_context
def telegram_send_action(ctx):
    """Send the action recommendation via Telegram now."""
    c = _get_components(ctx)
    bot = c.get("telegram_bot")
    if not bot:
        console.print("[red]Telegram not configured. Run: python main.py telegram setup[/red]")
        return
    from utils.action_engine import ActionEngine
    snapshot = c["monitor"].get_current_status()
    if not snapshot:
        console.print("[dim]No data. Run: python main.py setup[/dim]")
        return
    signals = c["cycle"].get_nadeau_signals(snapshot)
    engine = ActionEngine(c["cycle"], c["monitor"], c["goal_tracker"])
    rec = engine.get_action(snapshot, signals)
    bot.send_action(rec)
    console.print("[green]Action sent via Telegram![/green]")


# ──────────────────────────────────────────────────────
# SERVICE (launchd automation)
# ──────────────────────────────────────────────────────
@cli.group()
def service():
    """Manage background automation (macOS launchd)."""
    pass


@service.command("install")
@click.option("--fetch-interval", default=15, type=int, help="Fetch interval in minutes (default: 15)")
@click.option("--digest-day", default=0, type=int, help="Digest day: 0=Sun, 1=Mon, ... (default: 0)")
@click.option("--digest-hour", default=9, type=int, help="Digest hour in 24h format (default: 9)")
@click.pass_context
def service_install(ctx, fetch_interval, digest_day, digest_hour):
    """Install launchd jobs for background monitoring."""
    from service.launchd import LaunchdManager

    project_dir = os.path.dirname(os.path.abspath(__file__))
    manager = LaunchdManager(project_dir)

    console.print("\n[bold #F7931A]Installing Bitcoin Monitor background services...[/bold #F7931A]\n")

    results = manager.install(
        fetch_interval=fetch_interval,
        digest_day=digest_day,
        digest_hour=digest_hour,
    )

    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    for job, status in results.items():
        if status == "installed":
            console.print(f"  [green]{job}:[/green] installed and loaded")
        else:
            console.print(f"  [red]{job}:[/red] {status}")

    console.print(f"\n  Fetch: every {fetch_interval} minutes")
    console.print(f"  Digest: {day_names[digest_day]}s at {digest_hour:02d}:00")
    console.print(f"  Logs: ~/Library/Logs/bitcoin-monitor/")
    console.print(f"\n  Run [dim]python main.py service status[/dim] to verify.")
    console.print(f"  Run [dim]python main.py service logs[/dim] to view output.\n")


@service.command("uninstall")
@click.pass_context
def service_uninstall(ctx):
    """Remove launchd jobs."""
    from service.launchd import LaunchdManager

    project_dir = os.path.dirname(os.path.abspath(__file__))
    manager = LaunchdManager(project_dir)

    console.print("\n[bold #F7931A]Removing Bitcoin Monitor background services...[/bold #F7931A]\n")
    results = manager.uninstall()

    for job, status in results.items():
        if status == "removed":
            console.print(f"  [green]{job}:[/green] removed")
        elif status == "not installed":
            console.print(f"  [dim]{job}:[/dim] not installed")
        else:
            console.print(f"  [red]{job}:[/red] {status}")

    console.print()


@service.command("status")
@click.pass_context
def service_status(ctx):
    """Check if background jobs are running."""
    from service.launchd import LaunchdManager

    project_dir = os.path.dirname(os.path.abspath(__file__))
    manager = LaunchdManager(project_dir)

    console.print("\n[bold #F7931A]Bitcoin Monitor Service Status[/bold #F7931A]\n")
    status = manager.status()

    for job, info in status.items():
        if info["loaded"]:
            state = "[green]running[/green]" if info["running"] else "[yellow]loaded (idle)[/yellow]"
            pid_str = f" (PID {info['pid']})" if info["pid"] else ""
            exit_str = f"  last exit: {info['last_exit']}" if info.get("last_exit") is not None else ""
            console.print(f"  {job}: {state}{pid_str}{exit_str}")
            if info.get("last_log_line"):
                console.print(f"    [dim]{info['last_log_line']}[/dim]")
        else:
            console.print(f"  {job}: [dim]not installed[/dim]")

    console.print(f"\n  [dim]Install: python main.py service install[/dim]")
    console.print(f"  [dim]Logs:    python main.py service logs[/dim]\n")


@service.command("logs")
@click.option("--job", type=click.Choice(["fetch", "digest", "all"]), default="all")
@click.option("--lines", default=50, type=int, help="Number of lines to show")
@click.pass_context
def service_logs(ctx, job, lines):
    """Show recent log output."""
    from service.launchd import LaunchdManager

    project_dir = os.path.dirname(os.path.abspath(__file__))
    manager = LaunchdManager(project_dir)

    output = manager.get_logs(job=job, lines=lines)
    console.print(output)


@service.command("run-fetch")
@click.pass_context
def service_run_fetch(ctx):
    """Single fetch cycle (called by launchd, not for manual use)."""
    import logging as _logging
    from service.launchd import rotate_logs

    logger = _logging.getLogger("bitcoin-monitor")
    logger.info(f"=== Fetch cycle started at {datetime.now().isoformat()} ===")

    rotate_logs()

    c = _get_components(ctx)
    monitor = c["monitor"]
    alert_engine = c["alert_engine"]

    try:
        # Fetch and store
        snapshot = monitor.fetch_and_store()
        if snapshot is None:
            logger.error("Fetch returned no data")
            raise SystemExit(1)

        logger.info(f"Fetched: BTC ${snapshot.price.price_usd:,.0f}, "
                    f"F&G {snapshot.sentiment.fear_greed_value}")

        # Evaluate alert rules
        triggered = alert_engine.check(snapshot)
        if triggered:
            logger.info(f"Alerts triggered: {len(triggered)}")
            for alert in triggered:
                sev = alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity)
                logger.info(f"  [{sev}] {alert.rule_name}: {alert.message}")
        else:
            logger.info("No alerts triggered")

        logger.info("=== Fetch cycle completed successfully ===\n")

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Fetch cycle failed: {e}", exc_info=True)
        raise SystemExit(1)


@service.command("run-digest")
@click.pass_context
def service_run_digest(ctx):
    """Single digest cycle (called by launchd, not for manual use)."""
    import logging as _logging
    from service.launchd import rotate_logs

    logger = _logging.getLogger("bitcoin-monitor")
    logger.info(f"=== Digest cycle started at {datetime.now().isoformat()} ===")

    rotate_logs()

    c = _get_components(ctx)
    config = c["config"]

    # Check if email is configured
    email_config = config.get("email", {})
    if not email_config.get("enabled") or not email_config.get("digest_enabled"):
        logger.info("Email digest not enabled — skipping")
        raise SystemExit(0)

    try:
        from notifications.email_sender import EmailSender
        from digest.weekly_digest import WeeklyDigest

        sender = EmailSender(config)
        if not sender.is_configured():
            logger.warning("Email not fully configured — skipping digest")
            raise SystemExit(0)

        # Generate digest
        logger.info("Generating weekly digest...")
        wd = WeeklyDigest(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"], c["db"])
        html = wd.format_html()

        logger.info(f"Digest generated: {len(html)} chars HTML")

        # Send email
        result = sender.send_digest(html, subject="Your Weekly Bitcoin Digest")
        if result:
            logger.info(f"Digest email sent to {sender.to_address}")

            # Desktop notification
            try:
                import subprocess as sp
                sp.run(["osascript", "-e",
                        'display notification "Weekly digest sent to your inbox" '
                        'with title "Bitcoin Monitor" sound name "Purr"'],
                       capture_output=True, timeout=5)
            except Exception:
                pass
        else:
            logger.error("Failed to send digest email")
            raise SystemExit(1)

        logger.info("=== Digest cycle completed successfully ===\n")

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Digest cycle failed: {e}", exc_info=True)
        raise SystemExit(1)


# ──────────────────────────────────────────────────────
# EMAIL
# ──────────────────────────────────────────────────────
@cli.group()
def email():
    """Email configuration and sending."""
    pass


@email.command("setup")
@click.pass_context
def email_setup(ctx):
    """Interactive email setup wizard."""
    from rich.prompt import Prompt, Confirm
    import yaml

    console.print("\n[bold #F7931A]Email Setup[/bold #F7931A]\n")
    console.print("You'll need SMTP credentials. For Gmail, use an App Password:")
    console.print("  https://myaccount.google.com/apppasswords\n")

    smtp_host = Prompt.ask("SMTP host", default="smtp.gmail.com")
    smtp_port = Prompt.ask("SMTP port", default="587")
    from_addr = Prompt.ask("From email address")
    to_addr = Prompt.ask("To email address (where digests go)")
    username = Prompt.ask("SMTP username (usually your email)")
    password = Prompt.ask("SMTP password (app password)", password=True)

    email_config = {
        "enabled": True,
        "smtp_host": smtp_host,
        "smtp_port": int(smtp_port),
        "from_address": from_addr,
        "to_address": to_addr,
        "smtp_username": username,
        "smtp_password": password,
        "use_tls": True,
        "digest_enabled": True,
        "critical_alerts_enabled": True,
    }

    user_config_path = Path("config/user_config.yaml")
    user_config = {}
    if user_config_path.exists():
        with open(user_config_path) as f:
            user_config = yaml.safe_load(f) or {}
    user_config["email"] = email_config
    with open(user_config_path, "w") as f:
        yaml.dump(user_config, f, default_flow_style=False, sort_keys=False)

    console.print(f"\n[green]Config saved to {user_config_path}[/green]")

    if Confirm.ask("Test the connection now?"):
        from notifications.email_sender import EmailSender
        sender = EmailSender({"email": email_config})
        result = sender.test_connection()
        if result["status"] == "ok":
            console.print("[green]Connection successful![/green]")
        else:
            console.print(f"[red]Failed:[/red] {result['message']}")


@email.command("test")
@click.pass_context
def email_test(ctx):
    """Send a test email."""
    c = _get_components(ctx)
    from notifications.email_sender import EmailSender
    sender = EmailSender(c["config"])

    if not sender.is_configured():
        console.print("[red]Email not configured.[/red] Run: python main.py email setup")
        return

    result = sender.send_digest(
        html_content="<h1>Test Email</h1><p>Bitcoin Cycle Monitor email is working.</p>",
        subject="BTC Monitor -- Test Email",
    )
    if result:
        console.print(f"[green]Test email sent to {sender.to_address}[/green]")
    else:
        console.print("[red]Failed to send test email. Check logs.[/red]")


@email.command("send-digest")
@click.pass_context
def email_send_digest(ctx):
    """Send the weekly digest via email."""
    c = _get_components(ctx)
    from notifications.email_sender import EmailSender
    from digest.weekly_digest import WeeklyDigest

    sender = EmailSender(c["config"])
    if not sender.is_configured():
        console.print("[red]Email not configured.[/red] Run: python main.py email setup")
        return

    console.print("[bold #F7931A]Generating weekly digest...[/bold #F7931A]")

    wd = WeeklyDigest(c["monitor"], c["cycle"], c["alert_engine"], c["nadeau"], c["db"])
    html = wd.format_html()

    result = sender.send_digest(html, subject="Your Weekly Bitcoin Digest")
    if result:
        console.print(f"[green]Digest sent to {sender.to_address}[/green]")
    else:
        console.print("[red]Failed to send digest.[/red]")


if __name__ == "__main__":
    cli()
