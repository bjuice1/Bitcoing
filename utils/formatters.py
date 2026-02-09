"""Formatting utilities for display."""
from datetime import datetime, timezone


def format_usd(value, compact=False):
    """Format USD value with commas and 2 decimals. Compact mode for large numbers."""
    if value is None:
        return "N/A"
    value = float(value)
    if compact or abs(value) >= 1_000_000_000:
        if abs(value) >= 1_000_000_000_000:
            return f"${value / 1_000_000_000_000:,.2f}T"
        elif abs(value) >= 1_000_000_000:
            return f"${value / 1_000_000_000:,.2f}B"
        elif abs(value) >= 1_000_000:
            return f"${value / 1_000_000:,.2f}M"
    return f"${value:,.2f}"


def format_pct(value, decimals=2, with_color=False):
    """Format percentage with sign. Optionally include rich color markup."""
    if value is None:
        return "N/A"
    value = float(value)
    sign = "+" if value >= 0 else ""
    formatted = f"{sign}{value:.{decimals}f}%"
    if with_color:
        color = "green" if value >= 0 else "red"
        return f"[{color}]{formatted}[/{color}]"
    return formatted


def format_hashrate(th_per_sec):
    """Format network HR from TH/s to appropriate unit."""
    if th_per_sec is None:
        return "N/A"
    th_per_sec = float(th_per_sec)
    if th_per_sec >= 1e18:
        return f"{th_per_sec / 1e18:.2f} ZH/s"
    elif th_per_sec >= 1e15:
        return f"{th_per_sec / 1e15:.2f} EH/s"
    elif th_per_sec >= 1e12:
        return f"{th_per_sec / 1e12:.2f} TH/s"
    elif th_per_sec >= 1e9:
        return f"{th_per_sec / 1e9:.2f} GH/s"
    return f"{th_per_sec:.2f} H/s"


def format_btc(value):
    """Format BTC amount with 8 decimal places."""
    if value is None:
        return "N/A"
    return f"{float(value):.8f} BTC"


def format_compact(n):
    """Format number compactly: 1200000 → '1.2M'."""
    if n is None:
        return "N/A"
    n = float(n)
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    elif abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def format_timestamp(ts):
    """Format a datetime to human-readable string."""
    if ts is None:
        return "N/A"
    if isinstance(ts, str):
        return ts
    return ts.strftime("%Y-%m-%d %H:%M UTC")


def time_ago(dt):
    """Return human-readable time since dt. E.g., '3h ago', '2d ago'."""
    if dt is None:
        return "N/A"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h ago"
    else:
        return f"{seconds // 86400}d ago"
