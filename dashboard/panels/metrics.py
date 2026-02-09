"""Onchain metrics panel."""
from rich.panel import Panel
from rich.table import Table
from utils.formatters import format_hashrate, format_pct, format_compact


class MetricsPanel:
    @staticmethod
    def render(snapshot=None, supply_dynamics=None):
        if snapshot is None:
            return Panel("[dim]Awaiting data...[/dim]", title="Onchain", border_style="blue")

        o = snapshot.onchain
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("label", style="dim", width=14)
        table.add_column("value")

        table.add_row("Network HR", format_hashrate(o.hash_rate_th))
        table.add_row("Difficulty", format_compact(o.difficulty))

        dc = o.difficulty_change_pct
        dc_color = "green" if dc >= 0 else "red"
        table.add_row("Next Adj.", f"[{dc_color}]{format_pct(dc)}[/{dc_color}]")

        table.add_row("Block Time", f"{o.block_time_avg:.0f}s ({o.block_time_avg / 60:.1f}m)")

        circ = o.supply_circulating
        pct_mined = (circ / o.supply_max * 100) if o.supply_max > 0 else 0
        table.add_row("Supply", f"{format_compact(circ)} / {format_compact(o.supply_max)}")
        table.add_row("% Mined", f"{pct_mined:.2f}%")

        dom = snapshot.sentiment.btc_dominance_pct
        table.add_row("Dominance", f"{dom:.1f}%")

        if supply_dynamics and supply_dynamics.get("pct_in_profit") is not None:
            pip = supply_dynamics["pct_in_profit"]
            pip_color = "green" if pip > 50 else "red"
            table.add_row("Est. In Profit", f"[{pip_color}]{pip:.1f}%[/{pip_color}]")

        return Panel(table, title="[bold blue]Onchain Metrics[/bold blue]", border_style="blue")
