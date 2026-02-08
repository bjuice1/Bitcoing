"""Dashboard color theme and styles."""
from rich.theme import Theme

BTC_ORANGE = "#F7931A"
BULL_GREEN = "#00C853"
BEAR_RED = "#FF1744"
NEUTRAL_BLUE = "#2196F3"
NEUTRAL_YELLOW = "#FFC107"
BG_DARK = "#1A1A2E"
GOLD = "#FFD700"
TEXT_LIGHT = "#E0E0E0"
TEXT_DIM = "#888888"
GRID = "#333355"

DASHBOARD_THEME = Theme({
    "btc": f"bold {BTC_ORANGE}",
    "bull": f"bold {BULL_GREEN}",
    "bear": f"bold {BEAR_RED}",
    "neutral": f"bold {NEUTRAL_YELLOW}",
    "info": f"{NEUTRAL_BLUE}",
    "dim": f"{TEXT_DIM}",
    "gold": f"{GOLD}",
    "critical": f"bold white on red",
    "warning": f"bold yellow",
    "price_up": f"bold {BULL_GREEN}",
    "price_down": f"bold {BEAR_RED}",
    "header": f"bold {BTC_ORANGE}",
})
