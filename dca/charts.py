"""Chart generation for DCA analysis using matplotlib — clean modern style."""
import logging
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from datetime import datetime, timedelta, date
import numpy as np

logger = logging.getLogger("btcmonitor.dca.charts")

# ─── Clean Modern Palette ────────────────────────────────────────
BG = "#F0F1F6"               # Soft cool grey page background
CHART_BG = "#FFFFFF"          # Pure white chart area
GRID = "#E4E7ED"              # Very subtle grid
TEXT = "#1E272E"               # Near-black for titles
TEXT_DIM = "#636E72"           # Muted secondary text
SPINE = "#DFE6E9"              # Almost invisible borders

# Vibrant data colors (pop against white)
ORANGE = "#F7931A"             # Bitcoin iconic
ORANGE_GLOW = "#FFC675"        # Warm glow
GREEN = "#00B894"              # Fresh mint bull
GREEN_BRIGHT = "#55EFC4"       # Lighter green
RED = "#FF6B6B"                # Coral bear
RED_DEEP = "#E17055"           # Deeper coral
BLUE = "#0984E3"               # Electric blue
BLUE_LIGHT = "#74B9FF"         # Soft blue
GOLD = "#F9CA24"               # Warm gold
PURPLE = "#6C5CE7"             # Rich purple
CYAN = "#00CEC9"               # Teal
PINK = "#FD79A8"               # Pink accent


def _apply_theme(ax, fig):
    """Apply clean modern light theme."""
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(CHART_BG)
    ax.tick_params(colors=TEXT_DIM, labelsize=9, length=0, pad=6)
    ax.xaxis.label.set_color(TEXT_DIM)
    ax.yaxis.label.set_color(TEXT_DIM)
    ax.title.set_color(TEXT)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["bottom", "left"]:
        ax.spines[s].set_color(SPINE)
        ax.spines[s].set_linewidth(0.5)
    ax.grid(True, alpha=0.5, color=GRID, linestyle="-", linewidth=0.5)


def _glow(ax, x, y, color, lw=2, glow_color=None, **kwargs):
    """Plot a line with a soft neon glow effect."""
    gc = glow_color or color
    ax.plot(x, y, color=gc, linewidth=lw + 6, alpha=0.07, solid_capstyle="round", **kwargs)
    ax.plot(x, y, color=gc, linewidth=lw + 3, alpha=0.14, solid_capstyle="round", **kwargs)
    return ax.plot(x, y, color=color, linewidth=lw, alpha=1, solid_capstyle="round", **kwargs)


def _price_badge(fig, price, ts_label=None):
    """Floating BTC price badge in top-right corner."""
    ts = ts_label or datetime.now().strftime("%H:%M")
    fig.text(0.97, 0.97, f"  BTC  ${price:,.0f}  ",
             fontsize=13, fontweight="bold", color="#FFFFFF",
             ha="right", va="top", transform=fig.transFigure,
             bbox=dict(boxstyle="round,pad=0.5", facecolor=ORANGE,
                       edgecolor="none", alpha=0.92))
    fig.text(0.97, 0.915, f"as of {ts}",
             fontsize=7, color=TEXT_DIM,
             ha="right", va="top", transform=fig.transFigure)


def _styled_legend(ax, **kwargs):
    """Consistent styled legend."""
    defaults = dict(facecolor=CHART_BG, edgecolor=SPINE,
                    labelcolor=TEXT, fontsize=9, framealpha=0.9)
    defaults.update(kwargs)
    return ax.legend(**defaults)


def _save(fig, path, logger_msg="Saved chart"):
    """Save with high DPI and clean background."""
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor(),
                edgecolor="none", pad_inches=0.3)
    plt.close(fig)
    logger.info(f"{logger_msg}: {path}")


# Keep old names as aliases for backward compat in any external code
DARK_BG = BG
GRID_COLOR = GRID
TEXT_COLOR = TEXT

def _apply_dark_theme(ax, fig):
    """Alias — routes to the new clean theme."""
    _apply_theme(ax, fig)


class DCAChartGenerator:
    def __init__(self, output_dir="data/"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ─── Original Chart Methods (reskinned) ──────────────────────

    def plot_dca_equity_curve(self, result, filename="dca_equity_curve.png", current_price=None):
        """Portfolio value vs total invested over time."""
        ts = result.time_series
        if not ts:
            return None

        dates = [datetime.strptime(t["date"], "%Y-%m-%d") for t in ts]
        values = [t["portfolio_value"] for t in ts]
        invested = [t["total_invested"] for t in ts]
        prices = [t["price"] for t in ts]

        fig, ax1 = plt.subplots(figsize=(14, 7))
        _apply_theme(ax1, fig)

        # Invested area — soft blue
        ax1.fill_between(dates, invested, alpha=0.12, color=BLUE)
        ax1.plot(dates, invested, color=BLUE_LIGHT, linewidth=1.2, alpha=0.6, label="Total Invested")

        # Portfolio value — glow green
        _glow(ax1, dates, values, GREEN, lw=2.5, glow_color=GREEN_BRIGHT)
        ax1.plot([], [], color=GREEN, linewidth=2.5, label="Portfolio Value")  # legend proxy

        ax1.set_ylabel("USD")
        _styled_legend(ax1, loc="upper left")

        # Price on secondary axis
        ax2 = ax1.twinx()
        ax2.plot(dates, prices, color=ORANGE, linewidth=1, alpha=0.4)
        ax2.set_ylabel("BTC Price", color=ORANGE)
        ax2.tick_params(axis="y", colors=ORANGE, labelsize=8)
        ax2.spines["right"].set_color(ORANGE)
        ax2.spines["right"].set_visible(True)
        ax2.spines["right"].set_linewidth(0.5)

        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        fig.autofmt_xdate()

        roi = result.roi_pct
        roi_c = GREEN if roi >= 0 else RED
        ax1.set_title(f"DCA Equity Curve   |   ROI: {roi:+.1f}%   |   Invested: ${result.total_invested:,.0f}",
                      fontsize=14, fontweight="bold", pad=20)

        if current_price or prices:
            _price_badge(fig, current_price or prices[-1])

        path = self.output_dir / filename
        _save(fig, path)
        return str(path)

    def plot_dca_vs_lumpsum(self, comparison, filename="dca_vs_lumpsum.png"):
        """Bar chart comparing DCA vs lump sum."""
        fig, ax = plt.subplots(figsize=(10, 7))
        _apply_theme(ax, fig)

        labels = ["DCA Strategy", "Lump Sum"]
        rois = [comparison.dca_result.roi_pct, comparison.lumpsum_roi_pct]
        colors = [GREEN if r > 0 else RED for r in rois]

        bars = ax.bar(labels, rois, color=colors, width=0.45, edgecolor="none",
                      linewidth=0, zorder=3)
        # Add value labels on bars
        for bar, roi, color in zip(bars, rois, colors):
            y = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, y + (1 if y >= 0 else -3),
                    f"{roi:+.1f}%", ha="center", va="bottom" if y >= 0 else "top",
                    color=color, fontsize=18, fontweight="bold")

        ax.set_ylabel("Return on Investment (%)")
        advantage = comparison.dca_advantage_pct
        ax.set_title(f"DCA vs Lump Sum   |   DCA advantage: {advantage:+.1f}%",
                      fontsize=14, fontweight="bold", pad=20)
        ax.axhline(y=0, color=TEXT_DIM, linewidth=0.5, alpha=0.3)

        path = self.output_dir / filename
        _save(fig, path)
        return str(path)

    def plot_cost_basis_vs_price(self, result, filename="cost_basis_vs_price.png"):
        """Running average cost basis vs BTC price."""
        ts = result.time_series
        if not ts:
            return None

        dates = [datetime.strptime(t["date"], "%Y-%m-%d") for t in ts]
        prices = [t["price"] for t in ts]
        bases = [t["avg_cost_basis"] for t in ts]

        fig, ax = plt.subplots(figsize=(14, 7))
        _apply_theme(ax, fig)

        _glow(ax, dates, prices, ORANGE, lw=2, glow_color=ORANGE_GLOW)
        ax.plot([], [], color=ORANGE, linewidth=2, label="BTC Price")
        ax.plot(dates, bases, color=BLUE, linewidth=2, linestyle="--", label="Avg Cost Basis")

        # Underwater shading
        prices_arr = np.array(prices)
        bases_arr = np.array(bases)
        underwater = bases_arr > prices_arr
        ax.fill_between(dates, prices, bases,
                        where=underwater, alpha=0.12, color=RED,
                        interpolate=True, label="Underwater")

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        fig.autofmt_xdate()
        ax.set_ylabel("USD")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:,.0f}"))
        ax.set_title("Cost Basis vs BTC Price", fontsize=14, fontweight="bold", pad=20)
        _styled_legend(ax)

        path = self.output_dir / filename
        _save(fig, path)
        return str(path)

    def plot_btc_accumulation(self, result, filename="btc_accumulation.png"):
        """Cumulative BTC held over time."""
        ts = result.time_series
        if not ts:
            return None

        dates = [datetime.strptime(t["date"], "%Y-%m-%d") for t in ts]
        btc = [t["total_btc"] for t in ts]

        fig, ax = plt.subplots(figsize=(14, 7))
        _apply_theme(ax, fig)

        # Gradient-like fill: layer multiple fills with decreasing alpha
        ax.fill_between(dates, btc, alpha=0.06, color=ORANGE)
        ax.fill_between(dates, [b * 0.7 for b in btc], btc, alpha=0.08, color=ORANGE)
        _glow(ax, dates, btc, ORANGE, lw=2.5, glow_color=ORANGE_GLOW)

        ax.set_ylabel("BTC Accumulated")
        ax.set_title(f"BTC Accumulation   |   Total: {btc[-1]:.8f} BTC",
                      fontsize=14, fontweight="bold", pad=20)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        fig.autofmt_xdate()

        path = self.output_dir / filename
        _save(fig, path)
        return str(path)

    def plot_projection_scenarios(self, projections, filename="projections.png"):
        """Bar chart for forward projection scenarios."""
        fig, ax = plt.subplots(figsize=(12, 7))
        _apply_theme(ax, fig)

        bar_colors = {"bear_60k": RED, "bear_45k": RED_DEEP, "flat": GOLD,
                      "bull_100k": GREEN, "bull_150k": GREEN_BRIGHT}
        names, rois = [], []
        for name, proj in projections.items():
            if name == "full_cycle":
                continue
            names.append(name.replace("_", " ").title())
            rois.append(proj["roi_pct"])

        colors = [bar_colors.get(n, BLUE) for n in projections if n != "full_cycle"]
        bars = ax.bar(names, rois, color=colors, width=0.55, edgecolor="none", zorder=3)
        for bar, roi in zip(bars, rois):
            y = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, y + (1 if y >= 0 else -2),
                    f"{roi:+.1f}%", ha="center",
                    va="bottom" if y >= 0 else "top",
                    color=TEXT, fontsize=11, fontweight="bold")

        ax.set_ylabel("Projected ROI (%)")
        ax.set_title("DCA Projection Scenarios", fontsize=14, fontweight="bold", pad=20)
        ax.axhline(y=0, color=TEXT_DIM, linewidth=0.5, alpha=0.3)

        path = self.output_dir / filename
        _save(fig, path)
        return str(path)

    # ─── Visual Timeline Charts ──────────────────────────────────

    def _generate_price_path(self, current_price, target_price, months):
        """Generate monthly price points along a linear path."""
        if months <= 0:
            return [current_price]
        step = (target_price - current_price) / months
        return [current_price + step * m for m in range(months + 1)]

    def plot_scenario_fan(self, current_price, projections, monthly_dca=200,
                          key_levels=None, next_halving_date=None,
                          filename="scenario_fan.png"):
        """Forward-looking price fan chart with scenario paths from today."""
        fig, ax = plt.subplots(figsize=(16, 9))
        _apply_theme(ax, fig)

        today = date.today()

        scenario_styles = {
            "bull_150k": (GREEN_BRIGHT, "-", 2.5),
            "bull_100k": (GREEN, "-", 2.5),
            "flat":      (GOLD, "--", 2),
            "bear_60k":  (RED, "-", 2.5),
            "bear_45k":  (RED_DEEP, "-", 2),
        }

        paths = {}
        for name, proj in projections.items():
            if name == "full_cycle" or name not in scenario_styles:
                continue
            months = proj["months"]
            target = proj["target_price"]
            price_path = self._generate_price_path(current_price, target, months)
            month_dates = [today + timedelta(days=30 * m) for m in range(len(price_path))]
            paths[name] = (month_dates, price_path)

            color, ls, lw = scenario_styles[name]
            label = f"{name.replace('_', ' ').title()} (${target:,.0f})"
            _glow(ax, month_dates, price_path, color, lw=lw)
            ax.plot([], [], color=color, linewidth=lw, label=label)  # legend proxy
            # End label with pill background
            ax.annotate(f" ${target/1000:.0f}K ", xy=(month_dates[-1], price_path[-1]),
                        fontsize=9, color="#FFF", fontweight="bold",
                        xytext=(8, 0), textcoords="offset points", va="center",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor=color, edgecolor="none", alpha=0.85))

        # Full cycle path
        if "full_cycle" in projections:
            fc = projections["full_cycle"]
            bear_months = fc["at_bottom"]["months"]
            bull_months = fc["at_top"]["months"]
            bottom = fc["at_bottom"]["target_price"]
            top = fc["at_top"]["target_price"]
            bear_path = self._generate_price_path(current_price, bottom, bear_months)
            bull_path = self._generate_price_path(bottom, top, bull_months)[1:]
            full_path = bear_path + bull_path
            full_dates = [today + timedelta(days=30 * m) for m in range(len(full_path))]
            _glow(ax, full_dates, full_path, CYAN, lw=2)
            ax.plot([], [], color=CYAN, linewidth=2, linestyle="-.",
                    label=f"Full Cycle (${bottom/1000:.0f}K → ${top/1000:.0f}K)")
            ax.annotate(f" ${top/1000:.0f}K ", xy=(full_dates[-1], full_path[-1]),
                        fontsize=9, color="#FFF", fontweight="bold",
                        xytext=(8, 0), textcoords="offset points", va="center",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor=CYAN, edgecolor="none", alpha=0.85))

        # Accumulation zone shading
        if "bear_45k" in paths and "bear_60k" in paths:
            b45_dates, b45_prices = paths["bear_45k"]
            b60_dates, b60_prices = paths["bear_60k"]
            min_len = min(len(b45_prices), len(b60_prices))
            ax.fill_between(b45_dates[:min_len], b45_prices[:min_len], b60_prices[:min_len],
                            alpha=0.06, color=GREEN, label="Accumulation Zone")

        # TODAY marker — big orange star
        ax.plot(today, current_price, marker="*", color=ORANGE, markersize=22,
                zorder=10, markeredgecolor="#FFF", markeredgewidth=1)
        ax.annotate(f"TODAY  ${current_price:,.0f}", xy=(today, current_price),
                    fontsize=12, fontweight="bold", color=ORANGE,
                    xytext=(-100, 30), textcoords="offset points",
                    arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=2),
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=CHART_BG,
                              edgecolor=ORANGE, linewidth=1.5, alpha=0.95))

        # Key levels
        if key_levels:
            for level in key_levels:
                if abs(level - current_price) < 2000:
                    continue
                lcolor = GREEN if level < current_price else RED
                ax.axhline(y=level, color=lcolor, linewidth=0.7, linestyle=":", alpha=0.35, zorder=1)
                ax.text(ax.get_xlim()[1], level, f"  ${level/1000:.0f}K",
                        fontsize=7, color=lcolor, va="center", alpha=0.55)

        # Next halving
        if next_halving_date:
            hdt = datetime.combine(next_halving_date, datetime.min.time()) if isinstance(next_halving_date, date) else next_halving_date
            ax.axvline(x=hdt, color=GOLD, linewidth=1.2, linestyle="--", alpha=0.5)
            ax.text(hdt, ax.get_ylim()[1] * 0.97,
                    "  HALVING\n  Apr 2028", fontsize=8, fontweight="bold",
                    color=GOLD, va="top", alpha=0.7)

        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:,.0f}"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        fig.autofmt_xdate()
        ax.set_ylabel("BTC Price")
        ax.set_title(f"Where Could BTC Go?   |   Your ${monthly_dca}/mo DCA Horizon",
                      fontsize=16, fontweight="bold", pad=22)
        _styled_legend(ax, loc="upper left", ncol=2, fontsize=8)
        _price_badge(fig, current_price)

        path = self.output_dir / filename
        _save(fig, path, "Saved scenario fan chart")
        return str(path)

    def plot_cycle_overlay(self, price_history, halving_info, current_price,
                           filename="cycle_overlay.png"):
        """Past Bitcoin cycles overlaid with current cycle, normalized to halving day."""
        from utils.constants import HALVING_DATES, HALVING_PRICES, CYCLE_ATH

        fig, ax = plt.subplots(figsize=(16, 9))
        _apply_theme(ax, fig)

        cycle_data = {
            2: {
                "label": "Cycle 2  (2016 → 2020)",
                "color": BLUE_LIGHT,
                "halving_price": HALVING_PRICES[2],
                "ath_price": CYCLE_ATH[2]["price"],
                "ath_day": 527,
                "bottom_price": 3200,
                "bottom_day": 1090,
                "end_price": HALVING_PRICES[3],
                "end_day": 1402,
            },
            3: {
                "label": "Cycle 3  (2020 → 2024)",
                "color": PURPLE,
                "halving_price": HALVING_PRICES[3],
                "ath_price": CYCLE_ATH[3]["price"],
                "ath_day": 549,
                "bottom_price": 15500,
                "bottom_day": 1100,
                "end_price": HALVING_PRICES[4],
                "end_day": 1441,
            },
        }

        max_day = 1461

        for era, cd in cycle_data.items():
            days = [0, cd["ath_day"], cd["bottom_day"], cd["end_day"]]
            prices = [cd["halving_price"], cd["ath_price"], cd["bottom_price"], cd["end_price"]]
            base = cd["halving_price"]
            indexed = [p / base * 100 for p in prices]
            all_days = np.arange(0, cd["end_day"] + 1)
            all_indexed = np.interp(all_days, days, indexed)

            ax.plot(all_days, all_indexed, color=cd["color"], linewidth=2,
                    label=cd["label"], alpha=0.65)
            # Soft fill under past cycles
            ax.fill_between(all_days, 100, all_indexed, where=all_indexed > 100,
                            alpha=0.03, color=cd["color"])

        # Current cycle
        days_since = halving_info.get("days_since", 0)
        halving_price = HALVING_PRICES.get(4, 63963)

        if price_history and len(price_history) > 1:
            halving_date = HALVING_DATES[4]
            cycle_days, cycle_indexed = [], []
            for ph in price_history:
                ph_date = datetime.strptime(ph["date"], "%Y-%m-%d").date() if isinstance(ph["date"], str) else ph["date"]
                day_num = (ph_date - halving_date).days
                if day_num >= 0:
                    cycle_days.append(day_num)
                    cycle_indexed.append(ph["price_usd"] / halving_price * 100)
            if cycle_days:
                _glow(ax, cycle_days, cycle_indexed, ORANGE, lw=3, glow_color=ORANGE_GLOW)
                ax.plot([], [], color=ORANGE, linewidth=3, label="Cycle 4  (Current)")
                ax.fill_between(cycle_days, 100, cycle_indexed,
                                where=[c > 100 for c in cycle_indexed],
                                alpha=0.06, color=ORANGE)
        else:
            current_indexed = current_price / halving_price * 100
            _glow(ax, [0, days_since], [100, current_indexed], ORANGE, lw=3)
            ax.plot([], [], color=ORANGE, linewidth=3, label="Cycle 4  (Current)")

        # WE ARE HERE marker
        current_indexed = current_price / halving_price * 100
        ax.plot(days_since, current_indexed, marker="*", color=ORANGE, markersize=22,
                zorder=10, markeredgecolor="#FFF", markeredgewidth=1.5)
        ax.annotate(f"WE ARE HERE\nDay {days_since}",
                    xy=(days_since, current_indexed),
                    fontsize=12, fontweight="bold", color=ORANGE,
                    xytext=(35, 35), textcoords="offset points",
                    arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=2.5),
                    bbox=dict(boxstyle="round,pad=0.5", facecolor=CHART_BG,
                              edgecolor=ORANGE, linewidth=2, alpha=0.95))

        # Phase bands — colored strips along bottom
        phase_colors = [
            (0, 365, "Year 1 — Post-Halving", GREEN, 0.06),
            (365, 730, "Year 2 — Peak Zone", GOLD, 0.06),
            (730, 1095, "Year 3 — Bear", RED, 0.06),
            (1095, 1461, "Year 4 — Accumulation", BLUE, 0.06),
        ]
        y_bottom = ax.get_ylim()[0]
        band_height = (ax.get_ylim()[1] - y_bottom) * 0.04
        for start, end, label, color, alpha in phase_colors:
            ax.axvspan(start, end, ymin=0, ymax=0.04, alpha=0.5, color=color, zorder=0)
            ax.text((start + end) / 2, y_bottom + band_height * 0.5, label,
                    fontsize=7, color=TEXT_DIM, ha="center", va="center", fontweight="bold")

        ax.set_xlabel("Days Since Halving")
        ax.set_ylabel("Price (Indexed: 100 = Halving Day)")
        ax.set_title(f"Bitcoin Cycles Compared   |   Day {days_since} of Cycle 4",
                      fontsize=16, fontweight="bold", pad=22)
        _styled_legend(ax, loc="upper left", fontsize=9)
        ax.set_xlim(0, max_day)
        _price_badge(fig, current_price)

        path = self.output_dir / filename
        _save(fig, path, "Saved cycle overlay chart")
        return str(path)

    def plot_goal_timeline(self, goal_projections, filename="goal_timeline.png"):
        """BTC accumulation paths toward goal under bear/flat/bull scenarios."""
        if not goal_projections or goal_projections.get("status") == "complete":
            return None

        fig, ax = plt.subplots(figsize=(16, 8))
        _apply_theme(ax, fig)

        target_btc = goal_projections["target_btc"]
        current_btc = goal_projections["current_btc"]
        monthly_dca = goal_projections["monthly_dca"]
        scenarios = goal_projections["scenarios"]
        today = date.today()

        scenario_styles = {
            "bear": (GREEN, GREEN_BRIGHT, "-", 2.5, "Bear — Faster Accumulation"),
            "flat": (GOLD, GOLD, "--", 2, "Flat Price"),
            "bull": (RED, RED, "-", 2.5, "Bull — Slower Accumulation"),
        }

        for name, (color, glow_c, ls, lw, label) in scenario_styles.items():
            if name not in scenarios:
                continue
            scenario = scenarios[name]
            btc_path = scenario.get("monthly_btc_path", [])
            if not btc_path:
                continue
            months_to_goal = scenario.get("months")
            month_dates = [today + timedelta(days=30 * m) for m in range(len(btc_path))]

            display_len = len(btc_path)
            for i, btc in enumerate(btc_path):
                if btc >= target_btc:
                    display_len = i + 1
                    break

            _glow(ax, month_dates[:display_len], btc_path[:display_len], color, lw=lw, glow_color=glow_c)
            ax.plot([], [], color=color, linewidth=lw, label=label)

            # Goal-hit annotation
            if months_to_goal and months_to_goal <= 72:
                goal_date = today + timedelta(days=30 * months_to_goal)
                ax.plot(goal_date, target_btc, marker="o", color=color, markersize=8,
                        zorder=6, markeredgecolor="#FFF", markeredgewidth=1.5)
                ax.annotate(f" {months_to_goal} mo ", xy=(goal_date, target_btc),
                            fontsize=8, color="#FFF", fontweight="bold",
                            xytext=(8, -5 if name == "bull" else 8), textcoords="offset points",
                            bbox=dict(boxstyle="round,pad=0.3", facecolor=color,
                                      edgecolor="none", alpha=0.85))

        # Goal line
        ax.axhline(y=target_btc, color=GOLD, linewidth=2, linestyle="--", alpha=0.7, zorder=2)
        ax.text(0.01, target_btc, f"  GOAL: {target_btc} BTC  ",
                fontsize=12, color=GOLD, fontweight="bold", va="bottom",
                transform=ax.get_yaxis_transform(),
                bbox=dict(boxstyle="round,pad=0.4", facecolor=CHART_BG,
                          edgecolor=GOLD, linewidth=1.5, alpha=0.9))

        # Current BTC marker
        if current_btc > 0:
            ax.axhline(y=current_btc, color=ORANGE, linewidth=0.8, linestyle=":", alpha=0.4)
            ax.plot(today, current_btc, marker="*", color=ORANGE, markersize=18,
                    zorder=10, markeredgecolor="#FFF", markeredgewidth=1)
            ax.annotate(f"NOW: {current_btc:.6f} BTC", xy=(today, current_btc),
                        fontsize=10, fontweight="bold", color=ORANGE,
                        xytext=(12, -22), textcoords="offset points",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor=CHART_BG,
                                  edgecolor=ORANGE, alpha=0.9))

        # Milestone lines
        milestones = [0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
        for m in milestones:
            if current_btc < m < target_btc:
                ax.axhline(y=m, color=GRID, linewidth=0.5, linestyle=":", alpha=0.6)
                ax.text(1.01, m, f"{m} BTC", fontsize=7, color=TEXT_DIM,
                        alpha=0.6, va="center", transform=ax.get_yaxis_transform())

        # Bear market note
        ax.text(0.02, 0.96,
                "In a bear market you accumulate faster —\neach dollar buys more sats",
                transform=ax.transAxes, fontsize=9, color=GREEN, alpha=0.55,
                va="top", fontstyle="italic",
                bbox=dict(boxstyle="round,pad=0.4", facecolor=CHART_BG, edgecolor=GREEN,
                          alpha=0.3, linewidth=0.5))

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
        fig.autofmt_xdate()
        ax.set_ylabel("BTC Accumulated")
        ax.set_title(f"Path to {target_btc} BTC   |   ${monthly_dca}/month DCA",
                      fontsize=16, fontweight="bold", pad=22)
        _styled_legend(ax, loc="center left", fontsize=9)

        path = self.output_dir / filename
        _save(fig, path, "Saved goal timeline chart")
        return str(path)

    def plot_price_with_levels(self, price_history, current_price, key_levels=None,
                               cost_bases=None, filename="price_levels.png"):
        """Price history with support/resistance levels and cost basis references."""
        if not price_history:
            return None

        fig, ax = plt.subplots(figsize=(16, 8))
        _apply_theme(ax, fig)

        dates, prices = [], []
        for ph in price_history:
            d = datetime.strptime(ph["date"], "%Y-%m-%d") if isinstance(ph["date"], str) else ph["date"]
            dates.append(d)
            prices.append(ph["price_usd"])

        # Price line with glow
        _glow(ax, dates, prices, ORANGE, lw=2.5, glow_color=ORANGE_GLOW)
        ax.plot([], [], color=ORANGE, linewidth=2.5, label="BTC Price")

        # Gradient fill under price
        ax.fill_between(dates, prices, alpha=0.05, color=ORANGE)
        if len(prices) > 5:
            mid_prices = [p * 0.85 for p in prices]
            ax.fill_between(dates, mid_prices, prices, alpha=0.04, color=ORANGE)

        # Current price — big star
        ax.plot(dates[-1], current_price, marker="*", color=ORANGE, markersize=20,
                zorder=10, markeredgecolor="#FFF", markeredgewidth=1.5)
        ax.annotate(f"${current_price:,.0f}", xy=(dates[-1], current_price),
                    fontsize=14, fontweight="bold", color=ORANGE,
                    xytext=(12, 18), textcoords="offset points",
                    arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=2),
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=CHART_BG,
                              edgecolor=ORANGE, linewidth=1.5, alpha=0.95))

        # Key levels
        if key_levels:
            for level in key_levels:
                if level < min(prices) * 0.7 or level > max(prices) * 1.3:
                    continue
                is_support = level < current_price
                lcolor = GREEN if is_support else RED
                tag = "Support" if is_support else "Resistance"
                ax.axhline(y=level, color=lcolor, linewidth=0.8, linestyle="--", alpha=0.3, zorder=1)
                ax.text(dates[0], level,
                        f"  ${level/1000:.0f}K  {tag}  ",
                        fontsize=8, color="#FFF", fontweight="bold",
                        va="center",
                        bbox=dict(boxstyle="round,pad=0.25", facecolor=lcolor,
                                  edgecolor="none", alpha=0.65))

        # Cost basis references
        if cost_bases:
            for name, basis in cost_bases.items():
                if basis < min(prices) * 0.7 or basis > max(prices) * 1.3:
                    continue
                ax.axhline(y=basis, color=BLUE, linewidth=1.2, linestyle="-.", alpha=0.4, zorder=2)
                ax.text(dates[-1], basis,
                        f"  {name}  ${basis:,.0f}  ",
                        fontsize=8, color="#FFF", fontweight="bold",
                        va="center",
                        bbox=dict(boxstyle="round,pad=0.25", facecolor=BLUE,
                                  edgecolor="none", alpha=0.7))

        # ATH marker
        ath_price = max(prices)
        ath_idx = prices.index(ath_price)
        if ath_price > current_price * 1.05:
            ax.plot(dates[ath_idx], ath_price, marker="v", color=GOLD, markersize=10,
                    zorder=8, markeredgecolor="#FFF", markeredgewidth=1)
            ax.annotate(f"ATH ${ath_price:,.0f}", xy=(dates[ath_idx], ath_price),
                        fontsize=9, color=GOLD, fontweight="bold",
                        xytext=(0, 15), textcoords="offset points", ha="center",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor=CHART_BG,
                                  edgecolor=GOLD, alpha=0.9))

        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:,.0f}"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        fig.autofmt_xdate()
        ax.set_ylabel("BTC Price (USD)")
        ax.set_title("BTC Price   |   Key Levels & Support / Resistance",
                      fontsize=16, fontweight="bold", pad=22)
        _styled_legend(ax, loc="upper left")
        _price_badge(fig, current_price)

        path = self.output_dir / filename
        _save(fig, path, "Saved price levels chart")
        return str(path)
