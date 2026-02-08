"""DCA portfolio panel."""
from rich.panel import Panel
from rich.table import Table
from utils.formatters import format_usd, format_pct, format_btc
from dashboard.widgets import sparkline


class DCAPanel:
    @staticmethod
    def render(portfolio_status=None, current_price=0):
        if portfolio_status is None:
            return Panel("[dim]No DCA portfolio. Create one:\npython main.py dca portfolio create --name Main[/dim]",
                        title="DCA Portfolio", border_style="green")

        ps = portfolio_status
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("label", style="dim", width=14)
        table.add_column("value")

        table.add_row("Portfolio", f"[bold]{ps['name']}[/bold]")
        table.add_row("Invested", format_usd(ps["total_invested"]))
        table.add_row("Value", format_usd(ps["current_value"]))

        pnl = ps.get("pnl_usd", 0)
        roi = ps.get("roi_pct", 0)
        c = "green" if pnl >= 0 else "red"
        table.add_row("P&L", f"[{c}]{format_usd(pnl)} ({format_pct(roi)})[/{c}]")

        table.add_row("Avg Cost", format_usd(ps["avg_cost_basis"]))
        table.add_row("BTC Held", format_btc(ps["total_btc"]))
        table.add_row("# Buys", str(ps["num_purchases"]))
        table.add_row("Frequency", ps.get("frequency", "weekly"))

        return Panel(table, title="[bold green]DCA Portfolio[/bold green]", border_style="green")
