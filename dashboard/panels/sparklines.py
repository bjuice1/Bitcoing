"""Sparkline trends panel."""
from rich.panel import Panel
from rich.table import Table
from dashboard.widgets import sparkline


class SparklinesPanel:
    @staticmethod
    def render(histories=None):
        if not histories:
            return Panel("[dim]Awaiting data...[/dim]", title="Trends", border_style="cyan")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("metric", style="dim", width=12)
        table.add_column("sparkline")
        table.add_column("latest", width=12)

        for name, data in histories.items():
            if data:
                values = [v for _, v in data] if isinstance(data[0], tuple) else [d.get("value", d.get("price_usd", 0)) for d in data] if isinstance(data[0], dict) else data
                latest = f"{values[-1]:,.2f}" if values else "N/A"
                table.add_row(name, f"[cyan]{sparkline(values)}[/cyan]", latest)

        return Panel(table, title="[bold cyan]Trends (30d)[/bold cyan]", border_style="cyan")
