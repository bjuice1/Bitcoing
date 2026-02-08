"""Nadeau signal matrix panel."""
from rich.panel import Panel
from rich.table import Table
from dashboard.widgets import signal_indicator


class NadeauPanel:
    @staticmethod
    def render(nadeau_assessment=None, cycle_signals=None):
        if nadeau_assessment is None and cycle_signals is None:
            return Panel("[dim]Awaiting data...[/dim]", title="Nadeau Signals", border_style="#F7931A")

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Signal", style="dim", width=18)
        table.add_column("Status", width=10)
        table.add_column("Detail")

        # Cycle signals (from CycleAnalyzer)
        if cycle_signals:
            for name, status, value, interp in cycle_signals.get("signals", []):
                status_str = str(status.value) if hasattr(status, 'value') else str(status)
                colors = {"BULLISH": "green", "BEARISH": "red", "NEUTRAL": "yellow"}
                c = colors.get(status_str, "white")
                val_str = f"{value:.2f}" if isinstance(value, (int, float)) and value is not None else "N/A"
                table.add_row(name, f"[{c}]{status_str}[/{c}]", interp[:50])

        # Nadeau assessment
        if nadeau_assessment:
            lth = nadeau_assessment.get("lth_proxy", {})
            if lth:
                s = lth.get("signal", "NEUTRAL")
                s_str = s.value if hasattr(s, 'value') else str(s)
                c = {"BULLISH": "green", "BEARISH": "red"}.get(s_str, "yellow")
                table.add_row("LTH Proxy", f"[{c}]{lth.get('status', {}).value if hasattr(lth.get('status', ''), 'value') else 'N/A'}[/{c}]",
                            lth.get("detail", "")[:50])

            refl = nadeau_assessment.get("reflexivity", {})
            if refl:
                s = refl.get("signal", "NEUTRAL")
                s_str = s.value if hasattr(s, 'value') else str(s)
                c = {"BULLISH": "green", "BEARISH": "red"}.get(s_str, "yellow")
                table.add_row("Reflexivity", f"[{c}]{refl.get('state', {}).value if hasattr(refl.get('state', ''), 'value') else 'N/A'}[/{c}]",
                            refl.get("detail", "")[:50])

            # Overall bias
            overall = nadeau_assessment.get("overall_bias", "NEUTRAL")
            o_str = overall.value if hasattr(overall, 'value') else str(overall)
            conf = nadeau_assessment.get("confidence", "low")
            c = {"BULLISH": "green", "BEARISH": "red"}.get(o_str, "yellow")
            table.add_row("", "", "")
            table.add_row("[bold]OVERALL[/bold]", f"[bold {c}]{o_str}[/bold {c}]", f"Confidence: {conf}")

            # Narrative
            narrative = nadeau_assessment.get("narrative", "")
            if narrative:
                # Wrap narrative to fit
                table.add_row("", "", "")
                for i in range(0, len(narrative), 60):
                    chunk = narrative[i:i+60]
                    table.add_row("" if i > 0 else "[dim]Analysis[/dim]", "", f"[dim italic]{chunk}[/dim italic]")

        return Panel(table, title="[bold #F7931A]Nadeau Signal Matrix[/bold #F7931A]", border_style="#F7931A")
