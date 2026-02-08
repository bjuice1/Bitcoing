"""Cycle position panel."""
from rich.panel import Panel
from rich.table import Table
from dashboard.widgets import cycle_progress_bar
from utils.formatters import format_pct


class CyclePanel:
    @staticmethod
    def render(cycle_info=None, halving_info=None, drawdown_info=None):
        if halving_info is None:
            return Panel("[dim]Awaiting data...[/dim]", title="Cycle", border_style="magenta")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("label", style="dim", width=16)
        table.add_column("value")

        # Cycle phase
        if cycle_info:
            phase = cycle_info.get("phase", "?")
            conf = cycle_info.get("confidence", "?")
            phase_val = phase.value if hasattr(phase, 'value') else str(phase)
            table.add_row("Phase", f"[bold]{phase_val}[/bold] ({conf})")

        # Halving info
        table.add_row("Last Halving", halving_info.get("last_halving", "N/A"))
        table.add_row("Days Since", str(halving_info.get("days_since", 0)))

        until = halving_info.get("days_until")
        table.add_row("Next Halving", f"~{halving_info.get('next_halving_est', 'N/A')}")
        if until:
            table.add_row("Days Until", str(until))

        # Cycle progress bar
        pct = halving_info.get("cycle_pct_elapsed", 0)
        table.add_row("", cycle_progress_bar(pct, "Progress"))

        table.add_row("Block Reward", f"{halving_info.get('current_block_reward', 3.125)} BTC")

        # Drawdown
        if drawdown_info:
            dd = drawdown_info.get("current_drawdown_pct", 0)
            dd_color = "red" if dd > 40 else "yellow" if dd > 20 else "green"
            table.add_row("ATH Drawdown", f"[{dd_color}]{dd:.1f}%[/{dd_color}]")
            avg = drawdown_info.get("avg_cycle_max_drawdown", 80)
            table.add_row("vs Avg Max DD", f"{dd:.0f}% vs {avg:.0f}%")

        return Panel(table, title="[bold magenta]Cycle Position[/bold magenta]", border_style="magenta")
