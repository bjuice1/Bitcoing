"""Header panel - title bar."""
from datetime import datetime, timezone
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from dashboard.widgets import data_age_indicator


class HeaderPanel:
    @staticmethod
    def render(snapshot=None, cycle_info=None):
        title = Text("  BITCOIN CYCLE MONITOR  ", style="bold white on #F7931A")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        ts = snapshot.timestamp if snapshot else None
        freshness = data_age_indicator(ts)
        phase = cycle_info.get("phase", "").value if cycle_info and "phase" in cycle_info else "..."

        right = Text(f"{now}  |  {phase}  |  ", style="dim")

        return Panel(
            Columns([title, right, Text(freshness)], expand=True),
            style="bold #F7931A",
            height=3,
        )
