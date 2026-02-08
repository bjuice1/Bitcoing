"""Reusable dashboard UI widgets."""
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.progress_bar import ProgressBar
from utils.formatters import format_usd, format_pct, format_hashrate, time_ago
from dashboard.theme import BULL_GREEN, BEAR_RED, NEUTRAL_YELLOW, BTC_ORANGE, TEXT_DIM

SPARK_CHARS = "▁▂▃▄▅▆▇█"


def sparkline(values, width=20):
    """Generate Unicode sparkline from a list of values."""
    if not values:
        return ""
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    # Subsample if longer than width
    if len(vals) > width:
        step = len(vals) / width
        vals = [vals[int(i * step)] for i in range(width)]
    mn, mx = min(vals), max(vals)
    rng = mx - mn if mx != mn else 1
    return "".join(SPARK_CHARS[min(7, int((v - mn) / rng * 7))] for v in vals)


def metric_card(label, value, change_pct=None, spark_data=None):
    """Single metric display with optional change and sparkline."""
    lines = []
    lines.append(f"[bold]{label}[/bold]")
    lines.append(f"[bold white]{value}[/bold white]")
    if change_pct is not None:
        lines.append(format_pct(change_pct, with_color=True))
    if spark_data:
        lines.append(f"[dim]{sparkline(spark_data)}[/dim]")
    return "\n".join(lines)


def signal_indicator(name, status, value=None):
    """Colored signal row for Nadeau panel."""
    colors = {"BULLISH": BULL_GREEN, "BEARISH": BEAR_RED, "NEUTRAL": NEUTRAL_YELLOW}
    color = colors.get(str(status), TEXT_DIM)
    icons = {"BULLISH": "+", "BEARISH": "-", "NEUTRAL": "~"}
    icon = icons.get(str(status), "?")
    val_str = f" ({value:.2f})" if value is not None else ""
    return f"[{color}][{icon}] {name}{val_str}[/{color}]"


def cycle_progress_bar(pct, label="Cycle"):
    """Visual progress bar for cycle position."""
    filled = int(pct / 5)
    empty = 20 - filled
    bar = f"[{BTC_ORANGE}]{'█' * filled}[/{BTC_ORANGE}][dim]{'░' * empty}[/dim]"
    return f"{label}: {bar} {pct:.1f}%"


def fear_greed_gauge(value):
    """Visual gauge for Fear & Greed Index."""
    if value < 25:
        color = BEAR_RED
        zone = "Extreme Fear"
    elif value < 45:
        color = "#FF6B6B"
        zone = "Fear"
    elif value < 55:
        color = NEUTRAL_YELLOW
        zone = "Neutral"
    elif value < 75:
        color = "#66BB6A"
        zone = "Greed"
    else:
        color = BULL_GREEN
        zone = "Extreme Greed"

    filled = int(value / 5)
    empty = 20 - filled
    bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
    return f"F&G: {bar} {value} ({zone})"


def data_age_indicator(timestamp):
    """Show data freshness with color coding."""
    if timestamp is None:
        return "[red]No data[/red]"
    age_str = time_ago(timestamp)
    from datetime import datetime, timezone
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()
    if age_seconds < 300:
        return f"[green]Updated {age_str}[/green]"
    elif age_seconds < 1800:
        return f"[yellow]Updated {age_str}[/yellow]"
    else:
        return f"[red]Stale: {age_str}[/red]"
