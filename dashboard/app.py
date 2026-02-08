"""Main dashboard application."""
import logging
import time
import threading
import csv
from datetime import datetime, timezone
from pathlib import Path
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from dashboard.panels import (
    HeaderPanel, PricePanel, MetricsPanel, CyclePanel,
    SparklinesPanel, AlertsPanel, DCAPanel, NadeauPanel, FooterPanel,
)
from dashboard.theme import DASHBOARD_THEME

logger = logging.getLogger("btcmonitor.dashboard")


class Dashboard:
    def __init__(self, monitor, cycle_analyzer, alert_engine, nadeau_evaluator,
                 dca_tracker=None, config=None):
        self.monitor = monitor
        self.cycle = cycle_analyzer
        self.alerts = alert_engine
        self.nadeau = nadeau_evaluator
        self.dca = dca_tracker
        self.config = config or {}
        self.refresh_interval = self.config.get("dashboard", {}).get("refresh_interval", 60)
        self._running = False
        self._last_data = {}
        self._console = Console(theme=DASHBOARD_THEME)

    def _build_layout(self):
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="upper", ratio=3),
            Layout(name="lower", ratio=3),
            Layout(name="bottom", ratio=2),
            Layout(name="footer", size=3),
        )
        layout["upper"].split_row(
            Layout(name="price", ratio=1),
            Layout(name="metrics", ratio=1),
            Layout(name="cycle", ratio=1),
        )
        layout["lower"].split_row(
            Layout(name="sparklines", ratio=1),
            Layout(name="nadeau", ratio=2),
        )
        layout["bottom"].split_row(
            Layout(name="alerts", ratio=1),
            Layout(name="dca", ratio=1),
        )
        return layout

    def _refresh_data(self):
        """Gather all data for panels."""
        data = {}
        try:
            data["snapshot"] = self.monitor.get_current_status()
        except Exception as e:
            logger.warning(f"Snapshot fetch error: {e}")
            data["snapshot"] = self._last_data.get("snapshot")

        snapshot = data.get("snapshot")

        try:
            data["cycle_phase"] = self.cycle.get_cycle_phase(snapshot) if snapshot else None
        except Exception:
            data["cycle_phase"] = None

        try:
            data["halving_info"] = self.cycle.get_halving_info()
        except Exception:
            data["halving_info"] = None

        try:
            data["drawdown"] = self.cycle.get_drawdown_analysis()
        except Exception:
            data["drawdown"] = None

        try:
            data["cycle_signals"] = self.cycle.get_nadeau_signals(snapshot) if snapshot else None
        except Exception:
            data["cycle_signals"] = None

        try:
            data["nadeau"] = self.nadeau.get_full_assessment(snapshot) if snapshot else None
        except Exception:
            data["nadeau"] = None

        try:
            data["recent_alerts"] = self.monitor.db.get_recent_alerts(limit=10)
        except Exception:
            data["recent_alerts"] = []

        try:
            data["alert_stats"] = self.alerts.get_alert_stats()
        except Exception:
            data["alert_stats"] = {}

        try:
            data["price_history"] = self.monitor.db.get_price_history()
        except Exception:
            data["price_history"] = []

        try:
            data["supply_dynamics"] = self.cycle.get_supply_dynamics(
                snapshot.price.price_usd if snapshot else None
            )
        except Exception:
            data["supply_dynamics"] = None

        # Price changes
        data["price_changes"] = {}
        for label, days in [("7d", 7), ("30d", 30), ("90d", 90)]:
            try:
                data["price_changes"][label] = self.monitor.get_price_change(days)
            except Exception:
                data["price_changes"][label] = None

        # DCA portfolio
        data["dca_status"] = None
        if self.dca:
            try:
                portfolios = self.dca.list_portfolios()
                if portfolios and snapshot:
                    data["dca_status"] = self.dca.get_portfolio_status(
                        portfolios[0]["id"], snapshot.price.price_usd
                    )
            except Exception:
                pass

        # Sparkline histories
        data["histories"] = {}
        try:
            ph = data["price_history"][-30:]
            if ph:
                data["histories"]["Price"] = [r["price_usd"] for r in ph]
        except Exception:
            pass

        self._last_data = data
        return data

    def _render_panels(self, data, layout):
        snapshot = data.get("snapshot")
        layout["header"].update(HeaderPanel.render(snapshot, data.get("cycle_phase")))
        layout["price"].update(PricePanel.render(snapshot, data.get("price_history"), data.get("price_changes")))
        layout["metrics"].update(MetricsPanel.render(snapshot, data.get("supply_dynamics")))
        layout["cycle"].update(CyclePanel.render(data.get("cycle_phase"), data.get("halving_info"), data.get("drawdown")))
        layout["sparklines"].update(SparklinesPanel.render(data.get("histories")))
        layout["nadeau"].update(NadeauPanel.render(data.get("nadeau"), data.get("cycle_signals")))
        layout["alerts"].update(AlertsPanel.render(data.get("recent_alerts"), data.get("alert_stats")))
        layout["dca"].update(DCAPanel.render(data.get("dca_status"), snapshot.price.price_usd if snapshot else 0))
        layout["footer"].update(FooterPanel.render(
            snapshot.timestamp if snapshot else None,
            self.refresh_interval,
        ))

    def run(self):
        """Launch the live terminal dashboard."""
        self._running = True
        layout = self._build_layout()

        self._console.print("[bold #F7931A]Starting Bitcoin Cycle Monitor...[/bold #F7931A]")

        try:
            with Live(layout, console=self._console, refresh_per_second=1, screen=True) as live:
                while self._running:
                    data = self._refresh_data()
                    self._render_panels(data, layout)
                    # Check alerts on each refresh
                    snapshot = data.get("snapshot")
                    if snapshot:
                        try:
                            self.alerts.check(snapshot)
                        except Exception as e:
                            logger.debug(f"Alert check error: {e}")
                    time.sleep(self.refresh_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            self._console.clear()
            snapshot = self._last_data.get("snapshot")
            price = snapshot.price.price_usd if snapshot else 0
            self._console.print(f"[dim]Session ended. Last BTC: ${price:,.2f}[/dim]")

    def quick_status(self):
        """Return single-line status string."""
        try:
            snapshot = self.monitor.get_current_status()
            if not snapshot:
                return "BTC: No data available"
            p = snapshot.price
            fg = snapshot.sentiment.fear_greed_value
            mvrv = snapshot.valuation.mvrv_ratio
            phase = self.cycle.get_cycle_phase(snapshot).get("phase", "?")
            phase_str = phase.value if hasattr(phase, 'value') else str(phase)
            mvrv_str = f"{mvrv:.2f}" if mvrv else "N/A"
            c = "+" if p.change_24h_pct >= 0 else ""
            return f"BTC ${p.price_usd:,.0f} ({c}{p.change_24h_pct:.1f}% 24h) | F&G: {fg} | MVRV: {mvrv_str} | Cycle: {phase_str}"
        except Exception as e:
            return f"BTC: Error - {e}"

    def export_current(self, path="data/metrics_export.csv"):
        """Export current metrics to CSV."""
        summary = self.monitor.get_key_metrics_summary()
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=summary.keys())
            writer.writeheader()
            writer.writerow(summary)
        return path

    def export_history(self, days=30, path="data/history_export.csv"):
        """Export historical snapshots to CSV."""
        snapshots = self.monitor.db.get_snapshots(limit=days * 24)
        if not snapshots:
            return None
        rows = [s.to_dict() for s in snapshots]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return path
