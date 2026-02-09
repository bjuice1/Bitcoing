# 06 — Interactive Charts (Plotly Migration)

## Overview

The Bitcoin Cycle Monitor generates 11 chart types via Matplotlib, outputting static 200 DPI PNGs. These are effective for terminal use and email embedding, but they lack interactivity — no hover tooltips, no zoom, no date-range selection. For the web dashboard (see `05-web-dashboard.md`), charts must be interactive. This document specifies a Plotly migration for the 4 highest-value charts, while retaining Matplotlib for email and offline use.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Chart System (dual output)                │
│                                                               │
│  ┌─────────────────────────┐    ┌──────────────────────────┐  │
│  │   dca/charts.py         │    │   web/charts.py (NEW)    │  │
│  │   (Matplotlib — keep)   │    │   (Plotly — new)         │  │
│  │                         │    │                          │  │
│  │  11 chart methods       │    │  4 priority charts       │  │
│  │  Output: PNG files      │    │  Output: Plotly JSON     │  │
│  │                         │    │                          │  │
│  │  Used by:               │    │  Used by:                │  │
│  │  - Email digest (03)    │    │  - Web dashboard (05)    │  │
│  │  - Couples HTML report  │    │  - /api/chart/<type>     │  │
│  │  - CLI `charts` command │    │  - Partner view          │  │
│  │  - Offline PNG export   │    │                          │  │
│  └─────────────────────────┘    └──────────────────────────┘  │
│                                                               │
│  Shared: data preparation logic, color palette, scenarios     │
└──────────────────────────────────────────────────────────────┘
```

**Key design decision:** Matplotlib stays. Plotly is added alongside it, not as a replacement. Email clients cannot render JavaScript, so email digests (`03-email-digest.md`) and the couples HTML report will continue using Matplotlib PNGs embedded as base64. The web dashboard (`05-web-dashboard.md`) will use Plotly for interactivity.

**Downstream consumers:**
- `05-web-dashboard.md` — Flask routes serve Plotly JSON via `/api/chart/<type>`, frontend renders with `Plotly.newPlot()`

## Specification

### 1. New Module: `web/charts.py`

```python
"""
Interactive Plotly chart generators for the web dashboard.

Each function returns a Plotly figure (go.Figure) that can be:
  - Serialized to JSON via plotly.io.to_json(fig)
  - Rendered in HTML via fig.to_html(include_plotlyjs=False)
  - Served via Flask API as JSON for client-side rendering

Four priority charts:
  1. scenario_fan    — Forward-looking price scenarios with key levels
  2. cycle_overlay   — Historical cycle comparison (normalized)
  3. goal_timeline   — BTC accumulation paths to goal
  4. price_levels    — Price history with support/resistance levels
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

# Theme — matches existing Matplotlib palette from dca/charts.py
THEME = {
    "bg": "#F0F1F6",
    "plot_bg": "#FFFFFF",
    "grid": "#E4E7ED",
    "text": "#1E272E",
    "text_dim": "#636E72",
    "orange": "#F7931A",
    "green": "#00C853",
    "red": "#FF1744",
    "blue": "#2196F3",
    "gold": "#FFD700",
    "purple": "#9C27B0",
    "cyan": "#00BCD4",
    "pink": "#E91E63",
}
```

### 2. Chart 1: Scenario Fan (`scenario_fan`)

**Current Matplotlib version:** `dca/charts.py` lines 305–430, `plot_scenario_fan()`

**What it shows:** 5 forward-looking price paths (bear $45K, bear $60K, flat, bull $100K, bull $150K) plus a full-cycle path, with key support/resistance levels and the next halving date.

**Plotly implementation:**

```python
def scenario_fan(
    scenarios: list[dict],
    current_price: float,
    key_levels: list[dict],
    next_halving: date,
    monthly_dca: float = 200,
) -> go.Figure:
    """
    Interactive scenario fan chart.

    Args:
        scenarios: list of {"name": str, "dates": list[date], "prices": list[float],
                           "color": str, "dash": str}
        current_price: current BTC price
        key_levels: list of {"price": float, "label": str, "type": "support"|"resistance"}
        next_halving: estimated date of next halving
        monthly_dca: monthly DCA amount (for hover tooltip context)

    Returns:
        go.Figure with:
          - One trace per scenario (line + fill to zero for the full-cycle path)
          - Horizontal lines for key levels (green=support, red=resistance)
          - Vertical line for next halving
          - "Today" marker
          - Hover template: Date | Price | Scenario Name | DCA sats at this price

    Interactivity:
      - Hover: shows price, date, scenario name, and "At $X, $200/mo buys Y sats"
      - Zoom: x/y range zoom with reset button
      - Legend: click to toggle individual scenarios
      - Modebar: minimal (zoom, pan, reset, download PNG)
    """
    fig = go.Figure()

    # Scenario traces
    for s in scenarios:
        hover_text = [
            f"<b>{s['name']}</b><br>"
            f"Date: {d.strftime('%b %Y')}<br>"
            f"Price: ${p:,.0f}<br>"
            f"${monthly_dca}/mo = {int(monthly_dca / p * 1e8):,} sats"
            for d, p in zip(s["dates"], s["prices"])
        ]
        fig.add_trace(go.Scatter(
            x=s["dates"],
            y=s["prices"],
            name=s["name"],
            mode="lines",
            line=dict(color=s["color"], width=2.5, dash=s.get("dash", "solid")),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover_text,
        ))

    # Key levels as horizontal lines
    for level in key_levels:
        color = THEME["green"] if level["type"] == "support" else THEME["red"]
        fig.add_hline(
            y=level["price"],
            line_dash="dot",
            line_color=color,
            opacity=0.5,
            annotation_text=f"{level['label']} ${level['price']:,.0f}",
            annotation_position="right",
            annotation_font_size=10,
            annotation_font_color=THEME["text_dim"],
        )

    # Next halving vertical line
    fig.add_vline(
        x=next_halving,
        line_dash="dash",
        line_color=THEME["gold"],
        opacity=0.6,
        annotation_text=f"Halving ~{next_halving.strftime('%b %Y')}",
        annotation_position="top",
    )

    # Today marker
    fig.add_trace(go.Scatter(
        x=[date.today()],
        y=[current_price],
        mode="markers+text",
        marker=dict(size=14, color=THEME["orange"], symbol="star"),
        text=[f"Today ${current_price:,.0f}"],
        textposition="top center",
        textfont=dict(size=12, color=THEME["orange"]),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Layout
    fig.update_layout(
        title=dict(text="Bitcoin Price Scenarios", font=dict(size=20, color=THEME["text"])),
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["plot_bg"],
        font=dict(family="system-ui, -apple-system, sans-serif", color=THEME["text"]),
        xaxis=dict(gridcolor=THEME["grid"], showgrid=True),
        yaxis=dict(
            gridcolor=THEME["grid"],
            showgrid=True,
            tickprefix="$",
            tickformat=",.0f",
            title="Price (USD)",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(l=60, r=30, t=60, b=80),
        height=500,
    )

    fig.update_xaxes(
        rangeslider_visible=False,
        rangeselector=dict(
            buttons=[
                dict(count=6, label="6m", step="month"),
                dict(count=1, label="1y", step="year"),
                dict(count=2, label="2y", step="year"),
                dict(step="all", label="All"),
            ]
        ),
    )

    return fig
```

### 3. Chart 2: Cycle Overlay (`cycle_overlay`)

**Current Matplotlib version:** `dca/charts.py` lines 432–530, `plot_cycle_overlay()`

**What it shows:** Past Bitcoin cycles (2, 3, 4) overlaid on the same axis, normalized to halving day = 100. Shows where we are in the current cycle relative to history.

**Plotly implementation:**

```python
def cycle_overlay(
    cycles: list[dict],
    current_cycle_day: int,
    current_indexed_value: float,
) -> go.Figure:
    """
    Interactive cycle overlay chart.

    Args:
        cycles: list of {
            "name": str (e.g., "Cycle 2 (2016-2020)"),
            "days_since_halving": list[int],
            "indexed_prices": list[float],  # 100 = halving day price
            "color": str,
        }
        current_cycle_day: days since last halving
        current_indexed_value: current price indexed to halving price (100 = same)

    Returns:
        go.Figure with:
          - One trace per cycle
          - "You are here" marker on current cycle
          - Phase bands (Year 1, 2, 3, 4) as colored background rectangles
          - Hover: Day N | Indexed price | Cycle name

    Interactivity:
      - Hover: shows day since halving, indexed price, % gain from halving
      - Click legend to toggle cycles
      - Zoom to compare specific phases
    """
    fig = go.Figure()

    # Phase bands (background shading)
    phase_colors = [
        ("Year 1: Accumulation", 0, 365, "rgba(0, 200, 83, 0.08)"),
        ("Year 2: Growth", 365, 730, "rgba(255, 215, 0, 0.08)"),
        ("Year 3: Euphoria", 730, 1095, "rgba(255, 23, 68, 0.08)"),
        ("Year 4: Reset", 1095, 1460, "rgba(33, 150, 243, 0.08)"),
    ]
    for label, x0, x1, color in phase_colors:
        fig.add_vrect(x0=x0, x1=x1, fillcolor=color, layer="below", line_width=0,
                      annotation_text=label, annotation_position="top left",
                      annotation_font_size=10, annotation_font_color=THEME["text_dim"])

    # Cycle traces
    for c in cycles:
        hover = [
            f"<b>{c['name']}</b><br>"
            f"Day {d} since halving<br>"
            f"Indexed: {p:.0f} ({p - 100:+.0f}%)"
            for d, p in zip(c["days_since_halving"], c["indexed_prices"])
        ]
        fig.add_trace(go.Scatter(
            x=c["days_since_halving"],
            y=c["indexed_prices"],
            name=c["name"],
            mode="lines",
            line=dict(color=c["color"], width=2.5),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
        ))

    # "You are here" marker
    fig.add_trace(go.Scatter(
        x=[current_cycle_day],
        y=[current_indexed_value],
        mode="markers+text",
        marker=dict(size=16, color=THEME["orange"], symbol="star", line=dict(width=2, color="white")),
        text=[f"Today (Day {current_cycle_day})"],
        textposition="top center",
        textfont=dict(size=12, color=THEME["orange"], family="system-ui"),
        showlegend=False,
        hoverinfo="skip",
    ))

    fig.update_layout(
        title=dict(text="Bitcoin Cycle Comparison (Indexed to Halving = 100)", font=dict(size=18)),
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["plot_bg"],
        font=dict(family="system-ui, -apple-system, sans-serif", color=THEME["text"]),
        xaxis=dict(title="Days Since Halving", gridcolor=THEME["grid"], range=[0, 1460]),
        yaxis=dict(title="Indexed Price (100 = Halving Day)", gridcolor=THEME["grid"],
                   type="log"),  # Log scale for cycle comparison
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        hovermode="x",
        margin=dict(l=60, r=30, t=60, b=80),
        height=500,
    )

    return fig
```

### 4. Chart 3: Goal Timeline (`goal_timeline`)

**Current Matplotlib version:** `dca/charts.py` lines 532–630, `plot_goal_timeline()`

**What it shows:** 3 scenario paths (bear/flat/bull) showing BTC accumulation over time toward a goal, with milestone markers.

**Plotly implementation:**

```python
def goal_timeline(
    scenarios: list[dict],
    goal_btc: float,
    current_btc: float,
    milestones: list[dict],
    monthly_dca: float,
) -> go.Figure:
    """
    Interactive goal timeline chart.

    Args:
        scenarios: list of {
            "name": str ("Bear", "Flat", "Bull"),
            "months": list[int],
            "btc_accumulated": list[float],
            "color": str,
        }
        goal_btc: target BTC amount
        current_btc: current portfolio BTC
        milestones: list of {"btc": float, "label": str} (e.g., 0.01 BTC, 0.1 BTC)
        monthly_dca: monthly DCA amount for hover context

    Returns:
        go.Figure with:
          - One trace per scenario
          - Goal line (horizontal, gold dashed)
          - Current BTC marker
          - Milestone lines
          - Hover: Month N | BTC amount | Sats | $ value at scenario price

    Interactivity:
      - Hover: shows month, BTC accumulated, sats, and estimated value
      - Goal line intersection highlights when goal is reached per scenario
    """
    fig = go.Figure()

    # Scenario traces
    for s in scenarios:
        hover = [
            f"<b>{s['name']} scenario</b><br>"
            f"Month {m}<br>"
            f"BTC: {btc:.6f} ({int(btc * 1e8):,} sats)<br>"
            f"DCA total: ${m * monthly_dca:,.0f}"
            for m, btc in zip(s["months"], s["btc_accumulated"])
        ]
        fig.add_trace(go.Scatter(
            x=s["months"],
            y=s["btc_accumulated"],
            name=s["name"],
            mode="lines",
            line=dict(color=s["color"], width=2.5),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
        ))

    # Goal line
    max_months = max(max(s["months"]) for s in scenarios)
    fig.add_hline(
        y=goal_btc,
        line_dash="dash",
        line_color=THEME["gold"],
        line_width=2,
        annotation_text=f"Goal: {goal_btc} BTC",
        annotation_position="right",
        annotation_font=dict(size=13, color=THEME["gold"]),
    )

    # Milestone lines
    for ms in milestones:
        if ms["btc"] < goal_btc:
            fig.add_hline(
                y=ms["btc"],
                line_dash="dot",
                line_color=THEME["text_dim"],
                opacity=0.3,
                annotation_text=ms["label"],
                annotation_position="left",
                annotation_font_size=9,
            )

    # Current BTC marker
    fig.add_trace(go.Scatter(
        x=[0], y=[current_btc],
        mode="markers+text",
        marker=dict(size=14, color=THEME["orange"], symbol="star"),
        text=[f"Now: {current_btc:.6f} BTC"],
        textposition="middle right",
        textfont=dict(size=11, color=THEME["orange"]),
        showlegend=False,
        hoverinfo="skip",
    ))

    fig.update_layout(
        title=dict(text="Path to Your Bitcoin Goal", font=dict(size=18)),
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["plot_bg"],
        font=dict(family="system-ui, -apple-system, sans-serif", color=THEME["text"]),
        xaxis=dict(title="Months from Now", gridcolor=THEME["grid"]),
        yaxis=dict(title="BTC Accumulated", gridcolor=THEME["grid"], tickformat=".4f"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(l=70, r=30, t=60, b=80),
        height=500,
    )

    # Add annotation box: "In a bear market, your sats stack faster"
    fig.add_annotation(
        x=0.02, y=0.98,
        xref="paper", yref="paper",
        text="Bear markets = cheaper sats = faster stacking",
        showarrow=False,
        font=dict(size=11, color=THEME["green"]),
        bgcolor="rgba(0,200,83,0.1)",
        bordercolor=THEME["green"],
        borderwidth=1,
        borderpad=6,
        xanchor="left", yanchor="top",
    )

    return fig
```

### 5. Chart 4: Price with Levels (`price_levels`)

**Current Matplotlib version:** `dca/charts.py` lines 632–691, `plot_price_with_levels()`

**What it shows:** Historical BTC price with key support/resistance levels, cost basis references, ATH marker, and current price.

**Plotly implementation:**

```python
def price_levels(
    dates: list,
    prices: list[float],
    key_levels: list[dict],
    cost_bases: list[dict],
    ath_price: float,
    ath_date,
    current_price: float,
) -> go.Figure:
    """
    Interactive price chart with support/resistance levels.

    Args:
        dates: list of date objects
        prices: list of daily close prices
        key_levels: list of {"price": float, "label": str, "type": "support"|"resistance"}
        cost_bases: list of {"price": float, "label": str} (e.g., MicroStrategy avg)
        ath_price: all-time high price
        ath_date: date of ATH
        current_price: latest price

    Returns:
        go.Figure with:
          - Price line with area fill
          - Support levels (green horizontal)
          - Resistance levels (red horizontal)
          - Cost basis references (blue dash-dot)
          - ATH marker (gold triangle)
          - Current price marker (orange star)
          - Range slider for date selection

    Interactivity:
      - Hover: date, price, % from ATH, % from nearest support
      - Range slider at bottom for date selection
      - Log scale toggle button
      - Zoom and pan
    """
    # Calculate hover metadata
    hover_texts = [
        f"<b>{d.strftime('%b %d, %Y')}</b><br>"
        f"Price: ${p:,.0f}<br>"
        f"From ATH: {((p - ath_price) / ath_price) * 100:+.1f}%"
        for d, p in zip(dates, prices)
    ]

    fig = go.Figure()

    # Price area fill
    fig.add_trace(go.Scatter(
        x=dates, y=prices,
        name="BTC Price",
        mode="lines",
        line=dict(color=THEME["orange"], width=2),
        fill="tozeroy",
        fillcolor="rgba(247, 147, 26, 0.1)",
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_texts,
    ))

    # Support levels
    for level in key_levels:
        if level["type"] == "support":
            fig.add_hline(
                y=level["price"], line_dash="dot", line_color=THEME["green"], opacity=0.5,
                annotation_text=f"{level['label']} ${level['price']:,.0f}",
                annotation_position="right",
                annotation_font=dict(size=9, color=THEME["green"]),
            )

    # Resistance levels
    for level in key_levels:
        if level["type"] == "resistance":
            fig.add_hline(
                y=level["price"], line_dash="dot", line_color=THEME["red"], opacity=0.5,
                annotation_text=f"{level['label']} ${level['price']:,.0f}",
                annotation_position="right",
                annotation_font=dict(size=9, color=THEME["red"]),
            )

    # Cost basis references
    for cb in cost_bases:
        fig.add_hline(
            y=cb["price"], line_dash="dashdot", line_color=THEME["blue"], opacity=0.4,
            annotation_text=f"{cb['label']} ${cb['price']:,.0f}",
            annotation_position="left",
            annotation_font=dict(size=9, color=THEME["blue"]),
        )

    # ATH marker
    fig.add_trace(go.Scatter(
        x=[ath_date], y=[ath_price],
        mode="markers+text",
        marker=dict(size=12, color=THEME["gold"], symbol="triangle-up"),
        text=[f"ATH ${ath_price:,.0f}"],
        textposition="top center",
        textfont=dict(size=11, color=THEME["gold"]),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Current price marker
    fig.add_trace(go.Scatter(
        x=[dates[-1]], y=[current_price],
        mode="markers+text",
        marker=dict(size=14, color=THEME["orange"], symbol="star"),
        text=[f"Now ${current_price:,.0f}"],
        textposition="middle left",
        textfont=dict(size=12, color=THEME["orange"]),
        showlegend=False,
        hoverinfo="skip",
    ))

    fig.update_layout(
        title=dict(text="Bitcoin Price & Key Levels", font=dict(size=18)),
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["plot_bg"],
        font=dict(family="system-ui, -apple-system, sans-serif", color=THEME["text"]),
        xaxis=dict(
            gridcolor=THEME["grid"],
            rangeslider=dict(visible=True, thickness=0.05),
            rangeselector=dict(
                buttons=[
                    dict(count=3, label="3m", step="month"),
                    dict(count=6, label="6m", step="month"),
                    dict(count=1, label="1y", step="year"),
                    dict(count=2, label="2y", step="year"),
                    dict(step="all", label="All"),
                ]
            ),
        ),
        yaxis=dict(
            title="Price (USD)",
            gridcolor=THEME["grid"],
            tickprefix="$",
            tickformat=",.0f",
        ),
        hovermode="x",
        showlegend=False,
        margin=dict(l=70, r=30, t=60, b=40),
        height=550,
    )

    # Log scale toggle button
    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                x=0.01, y=1.08,
                xanchor="left", yanchor="top",
                buttons=[
                    dict(label="Linear", method="relayout", args=[{"yaxis.type": "linear"}]),
                    dict(label="Log", method="relayout", args=[{"yaxis.type": "log"}]),
                ],
                font=dict(size=11),
                bgcolor="white",
                bordercolor=THEME["grid"],
            )
        ]
    )

    return fig
```

### 6. Data Preparation Layer: `web/chart_data.py`

The data preparation logic currently lives inside `dca/charts.py` interleaved with Matplotlib rendering. Extract it into a shared module so both Matplotlib and Plotly can consume the same data.

```python
"""
Chart data preparation — shared between Matplotlib (dca/charts.py) and Plotly (web/charts.py).

Each function takes engine objects and returns plain dicts/lists ready for charting.
No rendering framework dependency.
"""

def prepare_scenario_fan_data(
    projector, cycle_analyzer, db, config, monthly_dca: float
) -> dict:
    """
    Prepare scenario fan data.

    Returns:
        {
            "scenarios": [{"name", "dates", "prices", "color", "dash"}, ...],
            "current_price": float,
            "key_levels": [{"price", "label", "type"}, ...],
            "next_halving": date,
            "monthly_dca": float,
        }
    """

def prepare_cycle_overlay_data(
    cycle_analyzer, db
) -> dict:
    """
    Prepare cycle overlay data.

    Returns:
        {
            "cycles": [{"name", "days_since_halving", "indexed_prices", "color"}, ...],
            "current_cycle_day": int,
            "current_indexed_value": float,
        }
    """

def prepare_goal_timeline_data(
    goal_tracker, projector, current_price: float, monthly_dca: float
) -> dict:
    """
    Prepare goal timeline data.

    Returns:
        {
            "scenarios": [{"name", "months", "btc_accumulated", "color"}, ...],
            "goal_btc": float,
            "current_btc": float,
            "milestones": [{"btc", "label"}, ...],
            "monthly_dca": float,
        }
    """

def prepare_price_levels_data(
    db, cycle_analyzer, config
) -> dict:
    """
    Prepare price with levels data.

    Returns:
        {
            "dates": list[date],
            "prices": list[float],
            "key_levels": [{"price", "label", "type"}, ...],
            "cost_bases": [{"price", "label"}, ...],
            "ath_price": float,
            "ath_date": date,
            "current_price": float,
        }
    """
```

### 7. Frontend Rendering

Charts are rendered client-side using Plotly.js loaded from CDN. The web dashboard templates (defined in `05-web-dashboard.md`) will include:

```html
<!-- In base template <head> -->
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js" charset="utf-8"></script>

<!-- Chart container -->
<div id="chart-scenario-fan" class="chart-container"></div>

<!-- Load chart data from API -->
<script>
  async function loadChart(chartType, divId) {
    const resp = await fetch(`/api/chart/${chartType}`);
    const fig = await resp.json();
    Plotly.newPlot(divId, fig.data, fig.layout, {
      responsive: true,
      displayModeBar: true,
      modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
      displaylogo: false,
      toImageButtonOptions: {
        format: 'png',
        filename: `btc-${chartType}`,
        height: 800,
        width: 1400,
        scale: 2,
      },
    });
  }

  // Load all charts on page load
  document.addEventListener('DOMContentLoaded', () => {
    loadChart('scenario_fan', 'chart-scenario-fan');
    loadChart('cycle_overlay', 'chart-cycle-overlay');
    loadChart('goal_timeline', 'chart-goal-timeline');
    loadChart('price_levels', 'chart-price-levels');
  });
</script>
```

### 8. Flask API Endpoints (consumed by `05-web-dashboard.md`)

```python
# In web/app.py (defined in 05-web-dashboard.md)
@app.route("/api/chart/<chart_type>")
def chart_api(chart_type):
    """
    Serve Plotly chart as JSON.

    Valid chart_type values: scenario_fan, cycle_overlay, goal_timeline, price_levels

    Response: JSON object with "data" and "layout" keys (Plotly figure format).
    Cache: 5-minute TTL (chart data doesn't change faster than fetch interval).
    """
    generators = {
        "scenario_fan": lambda: web_charts.scenario_fan(**prepare_scenario_fan_data(...)),
        "cycle_overlay": lambda: web_charts.cycle_overlay(**prepare_cycle_overlay_data(...)),
        "goal_timeline": lambda: web_charts.goal_timeline(**prepare_goal_timeline_data(...)),
        "price_levels": lambda: web_charts.price_levels(**prepare_price_levels_data(...)),
    }

    if chart_type not in generators:
        return {"error": f"Unknown chart type: {chart_type}"}, 404

    fig = generators[chart_type]()
    return json.loads(pio.to_json(fig))
```

### 9. Plotly.js Delivery Strategy

| Option | Size | Pros | Cons |
|--------|------|------|------|
| **CDN (recommended)** | 0 KB bundled | Cached across sites, always latest | Requires internet on first load |
| Self-hosted minified | ~3.5 MB | Works offline | Large file in repo |
| Partial bundle (basic) | ~1.2 MB | Smaller, offline | Manual rebuild on updates |

**Decision:** Use CDN with a local fallback. The web dashboard is on a local network that has internet access (the monitor fetches API data). If CDN fails, charts degrade to "loading..." with a retry button.

```html
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"
        onerror="document.getElementById('chart-fallback').style.display='block'">
</script>
<noscript><p>Charts require JavaScript.</p></noscript>
<div id="chart-fallback" style="display:none">
  <p>Could not load chart library. <a href="javascript:location.reload()">Retry</a></p>
</div>
```

### 10. Modified: `requirements.txt`

Add:
```
plotly>=5.18.0          # Interactive charts for web dashboard
```

Note: Plotly has no required system dependencies. It's pure Python + JavaScript.

### 11. Chart Migration Matrix

| Chart | Matplotlib (keep) | Plotly (new) | Notes |
|-------|-------------------|-------------|-------|
| Scenario Fan | `dca/charts.py` | `web/charts.py` | Both active |
| Cycle Overlay | `dca/charts.py` | `web/charts.py` | Both active |
| Goal Timeline | `dca/charts.py` | `web/charts.py` | Both active |
| Price with Levels | `dca/charts.py` | `web/charts.py` | Both active |
| DCA Equity Curve | `dca/charts.py` | — | Matplotlib only (future migration candidate) |
| DCA vs Lumpsum | `dca/charts.py` | — | Matplotlib only |
| Cost Basis vs Price | `dca/charts.py` | — | Matplotlib only |
| BTC Accumulation | `dca/charts.py` | — | Matplotlib only |
| Projection Scenarios | `dca/charts.py` | — | Matplotlib only |

The remaining 5 charts stay Matplotlib-only. They can be migrated to Plotly later if needed, but 4 interactive charts cover the primary web dashboard use case.

## Benefits

| Decision | Why | Alternative Considered |
|----------|-----|----------------------|
| **Plotly over D3.js** | Python API for data prep, JavaScript renderer for interactivity. No custom JS required. | D3.js — maximum flexibility but requires writing JavaScript from scratch |
| **Plotly over Chart.js** | Better for financial data (log scales, range sliders, unified hover). | Chart.js — simpler but lacks financial chart features |
| **Dual output (keep Matplotlib)** | Email clients can't run JavaScript. Matplotlib PNGs are necessary for email digests. | Plotly-only with server-side image export — adds complexity (Kaleido dependency) |
| **CDN for Plotly.js** | Zero-config, fast, cached. Dashboard runs on local network with internet. | Self-hosting — adds 3.5 MB to repo, manual version management |
| **4 charts, not 11** | Diminishing returns. The 4 priority charts cover the main dashboard panels. Other 7 are DCA-specific and less frequently viewed. | Migrate all 11 — triple the work, marginal user benefit |

## Expectations

- **Chart render time (client-side):** Under 300ms per chart after data loads
- **API response time (`/api/chart/<type>`):** Under 500ms including data preparation
- **Hover tooltip delay:** Under 50ms (Plotly default)
- **Chart responsiveness:** Charts resize correctly on window resize and mobile viewports
- **PNG download:** Each chart has a download button that exports at 2x resolution
- **Plotly.js CDN load time:** Under 2 seconds on first visit (cached on subsequent)

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Plotly.js CDN unavailable | Very low | Medium — charts don't render | Fallback message with retry button. Consider self-hosting if this becomes frequent. |
| Plotly figure JSON too large | Low (typical figure is 50-200 KB) | Low — slower load | Data compression at API level. Reduce point density for long time series (downsample to ~500 points). |
| Color theme mismatch between Matplotlib and Plotly | Medium | Low — cosmetic | Shared THEME dict in `web/charts.py` mirrors `dca/charts.py` palette exactly |
| Mobile touch interactions awkward | Medium | Low | Plotly has built-in touch support. Set `scrollZoom: false` to prevent accidental zoom on mobile scroll. |

## Results Criteria

1. **`/api/chart/scenario_fan`** returns valid Plotly JSON (has `data` and `layout` keys)
2. **Hover on scenario line** shows: scenario name, date, price, and sats per $200
3. **Zoom into 6-month window** on price_levels chart works with range selector buttons
4. **Toggle log/linear scale** button on price_levels works
5. **Click legend entry** on cycle_overlay hides/shows that cycle trace
6. **Charts render on mobile Safari** (iPhone viewport, 375px width) without horizontal scroll
7. **Download PNG** button produces a high-resolution image
8. **Matplotlib charts still generate** — `python main.py charts` produces the same 4 PNGs as before

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `web/charts.py` | **NEW** | 4 Plotly chart generator functions |
| `web/chart_data.py` | **NEW** | Shared data preparation layer (extracted from `dca/charts.py`) |
| `web/__init__.py` | **NEW** | Package init |
| `requirements.txt` | **MODIFY** | Add `plotly>=5.18.0` |
| `dca/charts.py` | **MODIFY** | Refactor data preparation into `web/chart_data.py`, keep rendering logic. Import shared data functions. |
| `tests/test_web_charts.py` | **NEW** | Tests for Plotly chart generation (valid figure structure, correct trace count, hover data) |
