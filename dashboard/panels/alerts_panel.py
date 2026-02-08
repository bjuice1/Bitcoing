"""Alerts status panel."""
from rich.panel import Panel
from rich.table import Table


class AlertsPanel:
    @staticmethod
    def render(recent_alerts=None, alert_stats=None):
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("info")

        # Overall status
        if not recent_alerts:
            table.add_row("[green]ALL CLEAR[/green] - No active alerts")
        else:
            crits = sum(1 for a in recent_alerts if a.get("severity") == "CRITICAL")
            warns = sum(1 for a in recent_alerts if a.get("severity") == "WARNING")
            if crits > 0:
                table.add_row(f"[bold red]!!! {crits} CRITICAL[/bold red] | {warns} warnings")
            elif warns > 0:
                table.add_row(f"[yellow]!! {warns} WARNINGS[/yellow]")
            else:
                table.add_row(f"[blue]{len(recent_alerts)} info alerts[/blue]")

        # Recent alerts
        if recent_alerts:
            for alert in recent_alerts[:5]:
                sev = alert.get("severity", "INFO")
                name = alert.get("rule_name", "Unknown")
                ts = alert.get("triggered_at", "")[:16]
                colors = {"CRITICAL": "red", "WARNING": "yellow", "INFO": "blue"}
                c = colors.get(sev, "white")
                table.add_row(f"[{c}][{sev[:4]}] {name}[/{c}] [dim]{ts}[/dim]")

        # Stats
        if alert_stats:
            stats_str = " | ".join(f"{sev}: {cnt}" for sev, cnt in alert_stats.items())
            table.add_row(f"[dim]30d: {stats_str}[/dim]")

        return Panel(table, title="[bold yellow]Alerts[/bold yellow]", border_style="yellow")
