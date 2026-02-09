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
from datetime import date

# Theme — matches existing Matplotlib palette from dca/charts.py
THEME = {
    "bg": "#F0F1F6",
    "plot_bg": "#FFFFFF",
    "grid": "#E4E7ED",
    "text": "#1E272E",
    "text_dim": "#636E72",
    "orange": "#F7931A",
    "green": "#00B894",
    "green_bright": "#55EFC4",
    "red": "#FF6B6B",
    "red_deep": "#E17055",
    "blue": "#0984E3",
    "blue_light": "#74B9FF",
    "gold": "#F9CA24",
    "purple": "#6C5CE7",
    "cyan": "#00CEC9",
    "pink": "#FD79A8",
}

FONT_FAMILY = "system-ui, -apple-system, sans-serif"


def _base_layout(title, height=500, **overrides):
    """Shared layout defaults for all charts."""
    layout = dict(
        title=dict(text=title, font=dict(size=18, color=THEME["text"])),
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["plot_bg"],
        font=dict(family=FONT_FAMILY, color=THEME["text"]),
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        margin=dict(l=60, r=30, t=60, b=80),
        height=height,
    )
    layout.update(overrides)
    return layout


def scenario_fan(scenarios, current_price, key_levels, next_halving,
                 monthly_dca=200):
    """
    Interactive scenario fan chart.

    Args:
        scenarios: list of {"name", "dates", "prices", "color", "dash"}
        current_price: current BTC price
        key_levels: list of {"price", "label", "type": "support"|"resistance"}
        next_halving: date of next halving
        monthly_dca: monthly DCA amount for hover context
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

    # Next halving vertical line (shape + separate annotation to avoid date arithmetic issues)
    fig.add_shape(
        type="line",
        x0=next_halving, x1=next_halving, y0=0, y1=1,
        yref="paper",
        line=dict(dash="dash", color=THEME["gold"], width=1.5),
        opacity=0.6,
    )
    fig.add_annotation(
        x=next_halving, y=1, yref="paper",
        text=f"Halving ~{next_halving.strftime('%b %Y')}",
        showarrow=False,
        yanchor="bottom",
        font=dict(size=11, color=THEME["gold"]),
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

    fig.update_layout(**_base_layout(
        "Bitcoin Price Scenarios",
        height=500,
        hovermode="x unified",
        xaxis=dict(
            gridcolor=THEME["grid"],
            showgrid=True,
            rangeslider_visible=False,
            rangeselector=dict(buttons=[
                dict(count=6, label="6m", step="month"),
                dict(count=1, label="1y", step="year"),
                dict(count=2, label="2y", step="year"),
                dict(step="all", label="All"),
            ]),
        ),
        yaxis=dict(
            gridcolor=THEME["grid"],
            showgrid=True,
            tickprefix="$",
            tickformat=",.0f",
            title="Price (USD)",
        ),
    ))

    return fig


def cycle_overlay(cycles, current_cycle_day, current_indexed_value):
    """
    Interactive cycle overlay chart.

    Args:
        cycles: list of {"name", "days_since_halving", "indexed_prices", "color"}
        current_cycle_day: days since last halving
        current_indexed_value: current price indexed to halving price (100 = same)
    """
    fig = go.Figure()

    # Phase bands (background shading)
    phase_colors = [
        ("Year 1: Accumulation", 0, 365, "rgba(0, 184, 148, 0.08)"),
        ("Year 2: Growth", 365, 730, "rgba(249, 202, 36, 0.08)"),
        ("Year 3: Euphoria", 730, 1095, "rgba(255, 107, 107, 0.08)"),
        ("Year 4: Reset", 1095, 1460, "rgba(9, 132, 227, 0.08)"),
    ]
    for label, x0, x1, color in phase_colors:
        fig.add_vrect(
            x0=x0, x1=x1, fillcolor=color, layer="below", line_width=0,
            annotation_text=label, annotation_position="top left",
            annotation_font_size=10, annotation_font_color=THEME["text_dim"],
        )

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
        marker=dict(size=16, color=THEME["orange"], symbol="star",
                    line=dict(width=2, color="white")),
        text=[f"Today (Day {current_cycle_day})"],
        textposition="top center",
        textfont=dict(size=12, color=THEME["orange"], family=FONT_FAMILY),
        showlegend=False,
        hoverinfo="skip",
    ))

    fig.update_layout(**_base_layout(
        "Bitcoin Cycle Comparison (Indexed to Halving = 100)",
        height=500,
        hovermode="x",
        xaxis=dict(
            title="Days Since Halving",
            gridcolor=THEME["grid"],
            range=[0, 1460],
        ),
        yaxis=dict(
            title="Indexed Price (100 = Halving Day)",
            gridcolor=THEME["grid"],
            type="log",
        ),
    ))

    return fig


def goal_timeline(scenarios, goal_btc, current_btc, milestones, monthly_dca):
    """
    Interactive goal timeline chart.

    Args:
        scenarios: list of {"name", "months", "btc_accumulated", "color"}
        goal_btc: target BTC amount
        current_btc: current portfolio BTC
        milestones: list of {"btc", "label"}
        monthly_dca: monthly DCA amount for hover context
    """
    fig = go.Figure()

    # Scenario traces
    for s in scenarios:
        hover = [
            f"<b>{s['name']}</b><br>"
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

    fig.update_layout(**_base_layout(
        "Path to Your Bitcoin Goal",
        height=500,
        hovermode="x unified",
        xaxis=dict(title="Months from Now", gridcolor=THEME["grid"]),
        yaxis=dict(title="BTC Accumulated", gridcolor=THEME["grid"], tickformat=".4f"),
    ))

    # Bear market annotation
    fig.add_annotation(
        x=0.02, y=0.98,
        xref="paper", yref="paper",
        text="Bear markets = cheaper sats = faster stacking",
        showarrow=False,
        font=dict(size=11, color=THEME["green"]),
        bgcolor="rgba(0,184,148,0.1)",
        bordercolor=THEME["green"],
        borderwidth=1,
        borderpad=6,
        xanchor="left", yanchor="top",
    )

    return fig


def price_levels(dates, prices, key_levels, cost_bases, ath_price, ath_date,
                 current_price):
    """
    Interactive price chart with support/resistance levels.

    Args:
        dates: list of date objects
        prices: list of daily close prices
        key_levels: list of {"price", "label", "type": "support"|"resistance"}
        cost_bases: list of {"price", "label"}
        ath_price: all-time high price
        ath_date: date of ATH
        current_price: latest price
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

    fig.update_layout(**_base_layout(
        "Bitcoin Price & Key Levels",
        height=550,
        hovermode="x",
        showlegend=False,
        xaxis=dict(
            gridcolor=THEME["grid"],
            rangeslider=dict(visible=True, thickness=0.05),
            rangeselector=dict(buttons=[
                dict(count=3, label="3m", step="month"),
                dict(count=6, label="6m", step="month"),
                dict(count=1, label="1y", step="year"),
                dict(count=2, label="2y", step="year"),
                dict(step="all", label="All"),
            ]),
        ),
        yaxis=dict(
            title="Price (USD)",
            gridcolor=THEME["grid"],
            tickprefix="$",
            tickformat=",.0f",
        ),
    ))

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
