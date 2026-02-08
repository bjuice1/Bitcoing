"""Footer panel - status bar."""
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from dashboard.widgets import data_age_indicator


class FooterPanel:
    @staticmethod
    def render(last_fetch=None, next_fetch_in=None, api_status=None):
        parts = []

        if last_fetch:
            parts.append(data_age_indicator(last_fetch))
        if next_fetch_in:
            parts.append(f"[dim]Next fetch: {next_fetch_in}s[/dim]")

        if api_status:
            for name, info in api_status.items():
                dot = "[green]●[/green]" if info.get("reachable") else "[red]●[/red]"
                parts.append(f"{dot} {name}")

        parts.append("[dim]q:quit  r:refresh  f:fetch[/dim]")

        return Panel(
            Text.from_markup("  |  ".join(parts)),
            style="dim",
            height=3,
        )
