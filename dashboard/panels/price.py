"""Price panel - current price and market data."""
from rich.panel import Panel
from rich.table import Table
from utils.formatters import format_usd, format_pct
from utils.constants import REFERENCE_COST_BASES, KEY_LEVELS
from dashboard.widgets import sparkline


class PricePanel:
    @staticmethod
    def render(snapshot=None, price_history=None, price_changes=None):
        if snapshot is None:
            return Panel("[dim]Awaiting data...[/dim]", title="Price", border_style="yellow")

        p = snapshot.price
        change_color = "green" if p.change_24h_pct >= 0 else "red"

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("label", style="dim", width=12)
        table.add_column("value", style="bold")

        table.add_row("Price", f"[bold white]${p.price_usd:,.2f}[/bold white]")
        table.add_row("24h", f"[{change_color}]{format_pct(p.change_24h_pct)}[/{change_color}]")
        table.add_row("Market Cap", format_usd(p.market_cap, compact=True))
        table.add_row("Volume 24h", format_usd(p.volume_24h, compact=True))

        if price_changes:
            for period, change in price_changes.items():
                if change is not None:
                    c = "green" if change >= 0 else "red"
                    table.add_row(period, f"[{c}]{format_pct(change)}[/{c}]")

        # Sparkline
        if price_history:
            prices = [r["price_usd"] for r in price_history[-30:]]
            table.add_row("30d", f"[dim]{sparkline(prices)}[/dim]")

        # Reference levels
        for name, basis in REFERENCE_COST_BASES.items():
            diff_pct = ((p.price_usd - basis) / basis * 100) if basis > 0 else 0
            c = "green" if diff_pct >= 0 else "red"
            table.add_row(f"vs {name}", f"[{c}]{format_pct(diff_pct)}[/{c}] (${basis:,.0f})")

        # Nearest support/resistance from key levels
        supports = [s for s in KEY_LEVELS if s < p.price_usd]
        resistances = [r for r in KEY_LEVELS if r > p.price_usd]
        if supports:
            nearest_sup = max(supports)
            table.add_row("Support", f"${nearest_sup:,.0f} ({(p.price_usd - nearest_sup) / nearest_sup * 100:+.1f}%)")
        if resistances:
            nearest_res = min(resistances)
            table.add_row("Resistance", f"${nearest_res:,.0f} ({(p.price_usd - nearest_res) / nearest_res * 100:+.1f}%)")

        return Panel(table, title="[bold #F7931A]Price[/bold #F7931A]", border_style="#F7931A")
