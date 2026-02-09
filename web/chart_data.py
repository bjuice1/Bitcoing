"""
Chart data preparation — shared between Matplotlib (dca/charts.py) and Plotly (web/charts.py).

Each function takes engine objects / raw data and returns plain dicts/lists
ready for charting. No rendering framework dependency.
"""
import logging
from datetime import date, timedelta, datetime

from utils.constants import (
    HALVING_DATES, HALVING_PRICES, CYCLE_ATH,
    KEY_LEVELS, REFERENCE_COST_BASES,
)

logger = logging.getLogger("btcmonitor.web.chart_data")

# Shared color definitions (match dca/charts.py palette)
COLORS = {
    "green_bright": "#55EFC4",
    "green": "#00B894",
    "gold": "#F9CA24",
    "red": "#FF6B6B",
    "red_deep": "#E17055",
    "blue_light": "#74B9FF",
    "purple": "#6C5CE7",
    "orange": "#F7931A",
    "cyan": "#00CEC9",
}


def prepare_scenario_fan_data(projections, current_price, config=None, monthly_dca=200):
    """
    Prepare scenario fan data from DCAProjector.compare_projections() output.

    Args:
        projections: dict from DCAProjector.compare_projections()
        current_price: current BTC price
        config: optional config dict with reference_levels
        monthly_dca: monthly DCA amount

    Returns:
        dict with keys: scenarios, current_price, key_levels, next_halving, monthly_dca
    """
    today = date.today()

    scenario_meta = {
        "bull_150k": {"color": COLORS["green_bright"], "dash": "solid", "order": 0},
        "bull_100k": {"color": COLORS["green"], "dash": "solid", "order": 1},
        "flat":      {"color": COLORS["gold"], "dash": "dash", "order": 2},
        "bear_60k":  {"color": COLORS["red"], "dash": "solid", "order": 3},
        "bear_45k":  {"color": COLORS["red_deep"], "dash": "solid", "order": 4},
    }

    scenarios = []
    for name, proj in projections.items():
        if name == "full_cycle" or name not in scenario_meta:
            continue
        months = proj["months"]
        target = proj["target_price"]
        step = (target - current_price) / max(months, 1)
        price_path = [current_price + step * m for m in range(months + 1)]
        month_dates = [today + timedelta(days=30 * m) for m in range(len(price_path))]

        meta = scenario_meta[name]
        scenarios.append({
            "name": name.replace("_", " ").title(),
            "dates": month_dates,
            "prices": price_path,
            "color": meta["color"],
            "dash": meta["dash"],
            "order": meta["order"],
        })

    # Full cycle path
    if "full_cycle" in projections:
        fc = projections["full_cycle"]
        bear_months = fc["at_bottom"]["months"]
        bull_months = fc["at_top"]["months"]
        bottom = fc["at_bottom"]["target_price"]
        top = fc["at_top"]["target_price"]

        bear_step = (bottom - current_price) / max(bear_months, 1)
        bear_path = [current_price + bear_step * m for m in range(bear_months + 1)]
        bull_step = (top - bottom) / max(bull_months, 1)
        bull_path = [bottom + bull_step * m for m in range(1, bull_months + 1)]
        full_path = bear_path + bull_path
        full_dates = [today + timedelta(days=30 * m) for m in range(len(full_path))]

        scenarios.append({
            "name": f"Full Cycle (${bottom / 1000:.0f}K -> ${top / 1000:.0f}K)",
            "dates": full_dates,
            "prices": full_path,
            "color": COLORS["cyan"],
            "dash": "dashdot",
            "order": 5,
        })

    scenarios.sort(key=lambda s: s["order"])

    # Key levels from config or defaults
    key_levels = []
    cfg_levels = config or {}
    ref = cfg_levels.get("reference_levels", {})
    support = ref.get("support", [60000, 65000, 70000, 75000, 80000])
    resistance = ref.get("resistance", [85000, 95000, 100000, 110000, 126000])

    for s in support:
        key_levels.append({"price": s, "label": "Support", "type": "support"})
    for r in resistance:
        key_levels.append({"price": r, "label": "Resistance", "type": "resistance"})

    next_halving = HALVING_DATES.get(5, date(2028, 4, 17))

    return {
        "scenarios": scenarios,
        "current_price": current_price,
        "key_levels": key_levels,
        "next_halving": next_halving,
        "monthly_dca": monthly_dca,
    }


def prepare_cycle_overlay_data(price_history, current_price, halving_info=None):
    """
    Prepare cycle overlay data from price history.

    Args:
        price_history: list of {"date": str, "price_usd": float}
        current_price: current BTC price
        halving_info: optional dict with "days_since" key

    Returns:
        dict with keys: cycles, current_cycle_day, current_indexed_value
    """
    import numpy as np

    cycle_definitions = {
        2: {
            "name": "Cycle 2 (2016-2020)",
            "color": COLORS["blue_light"],
            "halving_price": HALVING_PRICES[2],
            "ath_price": CYCLE_ATH[2]["price"],
            "ath_day": 527,
            "bottom_price": 3200,
            "bottom_day": 1090,
            "end_price": HALVING_PRICES[3],
            "end_day": 1402,
        },
        3: {
            "name": "Cycle 3 (2020-2024)",
            "color": COLORS["purple"],
            "halving_price": HALVING_PRICES[3],
            "ath_price": CYCLE_ATH[3]["price"],
            "ath_day": 549,
            "bottom_price": 15500,
            "bottom_day": 1100,
            "end_price": HALVING_PRICES[4],
            "end_day": 1441,
        },
    }

    cycles = []
    for era, cd in cycle_definitions.items():
        keyframe_days = [0, cd["ath_day"], cd["bottom_day"], cd["end_day"]]
        keyframe_prices = [cd["halving_price"], cd["ath_price"], cd["bottom_price"], cd["end_price"]]
        base = cd["halving_price"]
        keyframe_indexed = [p / base * 100 for p in keyframe_prices]

        all_days = list(range(0, cd["end_day"] + 1))
        all_indexed = list(np.interp(all_days, keyframe_days, keyframe_indexed))

        cycles.append({
            "name": cd["name"],
            "days_since_halving": all_days,
            "indexed_prices": all_indexed,
            "color": cd["color"],
        })

    # Current cycle (Cycle 4) from actual price history
    halving_date = HALVING_DATES[4]
    halving_price = HALVING_PRICES.get(4, 63963)

    if halving_info:
        days_since = halving_info.get("days_since", 0)
    else:
        days_since = (date.today() - halving_date).days

    if price_history and len(price_history) > 1:
        cycle_days = []
        cycle_indexed = []
        for ph in price_history:
            ph_date = ph["date"]
            if isinstance(ph_date, str):
                ph_date = datetime.strptime(ph_date, "%Y-%m-%d").date()
            day_num = (ph_date - halving_date).days
            if day_num >= 0:
                cycle_days.append(day_num)
                cycle_indexed.append(ph["price_usd"] / halving_price * 100)
        if cycle_days:
            cycles.append({
                "name": "Cycle 4 (Current)",
                "days_since_halving": cycle_days,
                "indexed_prices": cycle_indexed,
                "color": COLORS["orange"],
            })

    current_indexed = current_price / halving_price * 100

    return {
        "cycles": cycles,
        "current_cycle_day": days_since,
        "current_indexed_value": current_indexed,
    }


def prepare_goal_timeline_data(goal_projections, monthly_dca=200):
    """
    Prepare goal timeline data from GoalTracker.project_completion() output.

    Args:
        goal_projections: dict from GoalTracker.project_completion()
        monthly_dca: monthly DCA amount

    Returns:
        dict with keys: scenarios, goal_btc, current_btc, milestones, monthly_dca
        Returns None if goal is complete or data is missing.
    """
    if not goal_projections or goal_projections.get("status") == "complete":
        return None

    target_btc = goal_projections["target_btc"]
    current_btc = goal_projections["current_btc"]
    gp_monthly = goal_projections.get("monthly_dca", monthly_dca)

    scenario_meta = {
        "bear": {"color": COLORS["green"], "name": "Bear (cheaper sats)"},
        "flat": {"color": COLORS["gold"], "name": "Flat Price"},
        "bull": {"color": COLORS["red"], "name": "Bull (pricier sats)"},
    }

    scenarios = []
    for key in ["bear", "flat", "bull"]:
        raw = goal_projections.get("scenarios", {}).get(key)
        if not raw:
            continue
        btc_path = raw.get("monthly_btc_path", [])
        if not btc_path:
            continue
        meta = scenario_meta[key]
        scenarios.append({
            "name": meta["name"],
            "months": list(range(len(btc_path))),
            "btc_accumulated": btc_path,
            "color": meta["color"],
        })

    # Milestones
    milestones = []
    for m in [0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0]:
        if current_btc < m < target_btc:
            milestones.append({"btc": m, "label": f"{m} BTC"})

    return {
        "scenarios": scenarios,
        "goal_btc": target_btc,
        "current_btc": current_btc,
        "milestones": milestones,
        "monthly_dca": gp_monthly,
    }


def prepare_price_levels_data(price_history, current_price, config=None):
    """
    Prepare price with levels data from price history.

    Args:
        price_history: list of {"date": str, "price_usd": float}
        current_price: current BTC price
        config: optional config dict with reference_levels

    Returns:
        dict with keys: dates, prices, key_levels, cost_bases, ath_price, ath_date, current_price
    """
    dates = []
    prices = []
    for ph in price_history:
        d = ph["date"]
        if isinstance(d, str):
            d = datetime.strptime(d, "%Y-%m-%d").date()
        dates.append(d)
        prices.append(ph["price_usd"])

    if not prices:
        return None

    # ATH
    ath_price = max(prices)
    ath_idx = prices.index(ath_price)
    ath_date = dates[ath_idx]

    # Key levels from config or defaults
    cfg = config or {}
    ref = cfg.get("reference_levels", {})
    support = ref.get("support", [60000, 65000, 70000, 75000, 80000])
    resistance = ref.get("resistance", [85000, 95000, 100000, 110000, 126000])

    key_levels = []
    price_min = min(prices) * 0.7
    price_max = max(prices) * 1.3
    for s in support:
        if price_min <= s <= price_max:
            key_levels.append({"price": s, "label": "Support", "type": "support"})
    for r in resistance:
        if price_min <= r <= price_max:
            key_levels.append({"price": r, "label": "Resistance", "type": "resistance"})

    # Cost bases
    raw_bases = ref.get("cost_bases", REFERENCE_COST_BASES)
    if isinstance(raw_bases, dict):
        cost_bases = [
            {"price": v, "label": k}
            for k, v in raw_bases.items()
            if price_min <= v <= price_max
        ]
    else:
        cost_bases = []

    return {
        "dates": dates,
        "prices": prices,
        "key_levels": key_levels,
        "cost_bases": cost_bases,
        "ath_price": ath_price,
        "ath_date": ath_date,
        "current_price": current_price,
    }
