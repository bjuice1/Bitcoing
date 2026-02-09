# 05 — Web Dashboard (Flask)

## Overview

The Bitcoin Cycle Monitor has a Rich terminal dashboard that works well for developers at a keyboard. But it can't be checked from a phone, shared with a partner, or run headlessly on a server. This document specifies a Flask web application with two views — a full-detail dashboard for the primary user and a simplified partner-friendly view — accessible on the local network.

No build tools, no npm, no frontend framework. Server-rendered Jinja2 templates with Plotly.js for interactive charts and vanilla JavaScript for auto-refresh.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Flask Application                            │
│                     (web/app.py — NEW)                           │
│                                                                  │
│  Routes:                                                         │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  GET /              → Full dashboard (Jinja2 template)   │    │
│  │  GET /partner       → Partner view (simplified)          │    │
│  │  GET /api/snapshot  → JSON: latest metrics + signals     │    │
│  │  GET /api/chart/<t> → JSON: Plotly figure (see 06)       │    │
│  │  GET /api/history   → JSON: price history for charts     │    │
│  │  GET /api/alerts    → JSON: recent alerts                │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Templates:                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐    │
│  │  base.html     │  │  dashboard.html│  │  partner.html   │    │
│  │  (layout +     │  │  (full view)   │  │  (simplified)   │    │
│  │   shared CSS)  │  │                │  │                 │    │
│  └────────────────┘  └────────────────┘  └─────────────────┘    │
│                                                                  │
│  Static:                                                         │
│  ┌────────────────┐                                              │
│  │  style.css     │  (single CSS file, no framework)             │
│  └────────────────┘                                              │
│                                                                  │
│  Data layer (reuse existing engines):                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Monitor  │ │ Cycle    │ │ Alert    │ │ DCA      │           │
│  │          │ │ Analyzer │ │ Engine   │ │ Tracker  │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

**Dependencies:**
- `06-interactive-charts.md` — Plotly charts served via `/api/chart/<type>`
- `04-historical-data.md` — Full price history for charts
- All existing engine classes (Monitor, CycleAnalyzer, AlertEngine, NadeauSignalEvaluator, etc.)

## Specification

### 1. New Module: `web/app.py`

```python
"""
Flask web dashboard for Bitcoin Cycle Monitor.

Two views:
  GET /         — Full dashboard: all metrics, charts, alerts, cycle info, DCA status
  GET /partner  — Partner-friendly: traffic light, plain English, goal progress, 2 charts

API endpoints (consumed by frontend JavaScript):
  GET /api/snapshot        — Latest metrics + signals (JSON, auto-refreshed every 60s)
  GET /api/chart/<type>    — Plotly chart JSON (see 06-interactive-charts.md)
  GET /api/history         — Price history for custom charting
  GET /api/alerts          — Recent alert records

Started via: python main.py web [--port 5000] [--host 0.0.0.0]
"""

from flask import Flask, render_template, jsonify
import json
import plotly.io as pio

def create_app(config: dict, engines: dict) -> Flask:
    """
    Factory function. Receives initialized engines from main.py CLI.

    Args:
        config: Application config dict
        engines: {
            "monitor": BitcoinMonitor,
            "cycle": CycleAnalyzer,
            "alert_engine": AlertEngine,
            "nadeau": NadeauSignalEvaluator,
            "action_engine": ActionEngine,
            "db": Database,
            "dca_portfolio": PortfolioTracker,
            "goal_tracker": GoalTracker,
            "projector": DCAProjector,
        }

    Returns:
        Configured Flask app, ready to run.
    """
    app = Flask(__name__,
                template_folder="templates",
                static_folder="static")

    # Cache for snapshot data (refreshed by background thread or on request)
    _cache = {"snapshot": None, "timestamp": 0}
    CACHE_TTL = 300  # 5 minutes

    def get_fresh_data() -> dict:
        """
        Collect all data needed for dashboard rendering.
        Reuses the same data collection logic as dashboard/app.py._refresh_data().

        Returns dict with keys:
          snapshot, cycle_phase, halving_info, drawdown, nadeau_signals,
          nadeau_assessment, recent_alerts, action, traffic_light,
          portfolio_status, goal_progress, price_history
        """

    @app.route("/")
    def dashboard():
        """Full dashboard view."""
        data = get_fresh_data()
        return render_template("dashboard.html", **data)

    @app.route("/partner")
    def partner():
        """Partner-friendly simplified view."""
        data = get_fresh_data()
        return render_template("partner.html", **data)

    @app.route("/api/snapshot")
    def api_snapshot():
        """
        JSON API: current snapshot + derived signals.

        Response:
        {
            "price": {"usd": float, "change_24h_pct": float, "market_cap": float},
            "signal": {"color": "GREEN"|"YELLOW"|"RED", "label": str, "action": str},
            "fear_greed": {"value": int, "label": str},
            "mvrv": {"ratio": float, "zone": str},
            "cycle": {"phase": str, "days_since_halving": int, "pct": float},
            "halving": {"days_until": int, "date": str},
            "action": {"recommendation": str, "confidence": str, "explanation": str},
            "alerts_active": int,
            "portfolio": {"total_btc": float, "roi_pct": float, "value_usd": float},
            "timestamp": str (ISO 8601),
            "data_age_seconds": int,
        }

        Cache: Returns cached data if less than CACHE_TTL seconds old.
        """

    @app.route("/api/chart/<chart_type>")
    def api_chart(chart_type):
        """
        Plotly chart JSON. See 06-interactive-charts.md for chart specifications.

        Valid types: scenario_fan, cycle_overlay, goal_timeline, price_levels
        Returns: {"data": [...], "layout": {...}} (Plotly figure format)
        Cache: 5-minute TTL.
        """

    @app.route("/api/history")
    def api_history():
        """
        Price history for custom charting.

        Query params:
          days: int (default 365, max 5000)

        Response:
        {
            "dates": ["2024-01-01", ...],
            "prices": [42000.0, ...],
            "count": int,
        }
        """

    @app.route("/api/alerts")
    def api_alerts():
        """
        Recent alerts.

        Query params:
          limit: int (default 20, max 100)

        Response:
        {
            "alerts": [
                {"rule_name": str, "severity": str, "message": str,
                 "triggered_at": str, "metric_value": float},
                ...
            ],
            "count": int,
        }
        """

    return app
```

### 2. CLI Integration: `main.py`

```python
@cli.command()
@click.option("--port", default=5000, type=int, help="Port to bind to")
@click.option("--host", default="0.0.0.0", type=str, help="Host to bind to")
@click.pass_context
def web(ctx, port, host):
    """Launch the web dashboard."""
    from web.app import create_app
    import socket

    c = ctx.obj
    engines = {
        "monitor": c["monitor"],
        "cycle": c["cycle"],
        "alert_engine": c["alert_engine"],
        "nadeau": c["nadeau"],
        "action_engine": c["action_engine"],
        "db": c["db"],
        "dca_portfolio": c.get("dca_portfolio"),
        "goal_tracker": c.get("goal_tracker"),
        "projector": c["projector"],
    }

    app = create_app(c["config"], engines)

    # Show access URLs
    local_ip = socket.gethostbyname(socket.gethostname())
    console.print(f"\n[btc]Bitcoin Cycle Monitor — Web Dashboard[/]\n")
    console.print(f"  Local:    http://localhost:{port}")
    console.print(f"  Network:  http://{local_ip}:{port}")
    console.print(f"  Partner:  http://{local_ip}:{port}/partner")
    console.print(f"\n  Press Ctrl+C to stop.\n")

    app.run(host=host, port=port, debug=False)
```

### 3. Template: `web/templates/base.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Bitcoin Monitor{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    <script src="https://cdn.plot.ly/plotly-2.35.0.min.js" charset="utf-8"></script>
    {% block head %}{% endblock %}
</head>
<body>
    <header class="app-header">
        <div class="header-left">
            <h1 class="logo">&#x20BF; Bitcoin Monitor</h1>
            <span class="phase-badge phase-{{ cycle_phase|lower|replace(' ', '-') }}">
                {{ cycle_phase }}
            </span>
        </div>
        <div class="header-right">
            <span class="data-age" id="data-age">{{ data_age }}</span>
            <nav>
                <a href="/" class="nav-link {% if request.path == '/' %}active{% endif %}">Dashboard</a>
                <a href="/partner" class="nav-link {% if request.path == '/partner' %}active{% endif %}">Partner</a>
            </nav>
        </div>
    </header>

    <main class="container">
        {% block content %}{% endblock %}
    </main>

    <footer class="app-footer">
        <p>Bitcoin Cycle Monitor v1.0 &mdash; Data refreshes every 60s</p>
    </footer>

    <script>
        // Auto-refresh data every 60 seconds
        setInterval(async () => {
            try {
                const resp = await fetch('/api/snapshot');
                const data = await resp.json();
                updateDashboard(data);
            } catch (e) {
                console.warn('Refresh failed:', e);
            }
        }, 60000);

        function updateDashboard(data) {
            // Update price
            const priceEl = document.getElementById('current-price');
            if (priceEl) priceEl.textContent = '$' + data.price.usd.toLocaleString();

            // Update signal
            const signalEl = document.getElementById('signal-badge');
            if (signalEl) {
                signalEl.textContent = data.signal.label;
                signalEl.className = 'signal-badge signal-' + data.signal.color.toLowerCase();
            }

            // Update data age
            const ageEl = document.getElementById('data-age');
            if (ageEl) {
                const secs = data.data_age_seconds;
                ageEl.textContent = secs < 60 ? 'Just now' :
                    secs < 3600 ? Math.floor(secs/60) + 'm ago' :
                    Math.floor(secs/3600) + 'h ago';
            }

            // Update Fear & Greed
            const fgEl = document.getElementById('fear-greed-value');
            if (fgEl) fgEl.textContent = data.fear_greed.value + ' — ' + data.fear_greed.label;

            // Update other elements by id pattern
            for (const [key, value] of Object.entries(data)) {
                const el = document.getElementById('metric-' + key);
                if (el && typeof value === 'object' && value !== null) {
                    // Skip complex objects
                } else if (el) {
                    el.textContent = value;
                }
            }
        }
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

### 4. Template: `web/templates/dashboard.html`

```html
{% extends "base.html" %}
{% block title %}Bitcoin Dashboard{% endblock %}

{% block content %}
<div class="dashboard-grid">

    <!-- Row 1: Price Hero + Signal -->
    <section class="card card-hero">
        <div class="price-display">
            <span class="price-label">Bitcoin</span>
            <span class="price-value" id="current-price">${{ price_usd | format_usd }}</span>
            <span class="price-change {{ 'up' if change_24h >= 0 else 'down' }}">
                {{ change_24h | format_pct }}
            </span>
        </div>
        <div class="signal-display">
            <span class="signal-badge signal-{{ signal_color | lower }}" id="signal-badge">
                {{ signal_label }}
            </span>
            <p class="signal-action">{{ signal_action }}</p>
        </div>
    </section>

    <!-- Row 2: Key Metrics (4 cards) -->
    <section class="card metric-card">
        <h3>Fear & Greed</h3>
        <div class="metric-value" id="fear-greed-value">{{ fear_greed_value }} &mdash; {{ fear_greed_label }}</div>
        <div class="metric-bar">
            <div class="metric-bar-fill fg-{{ fear_greed_zone }}" style="width: {{ fear_greed_value }}%"></div>
        </div>
    </section>

    <section class="card metric-card">
        <h3>MVRV Ratio</h3>
        <div class="metric-value">{{ mvrv_ratio | round(2) }}</div>
        <div class="metric-subtitle">{{ mvrv_zone }}</div>
    </section>

    <section class="card metric-card">
        <h3>Cycle Position</h3>
        <div class="metric-value">Day {{ days_since_halving }}</div>
        <div class="metric-bar">
            <div class="metric-bar-fill cycle-bar" style="width: {{ cycle_pct }}%"></div>
        </div>
        <div class="metric-subtitle">{{ cycle_pct | round(1) }}% through cycle</div>
    </section>

    <section class="card metric-card">
        <h3>Drawdown from ATH</h3>
        <div class="metric-value drawdown">{{ drawdown_pct | format_pct }}</div>
        <div class="metric-subtitle">ATH: ${{ ath_price | format_usd }}</div>
    </section>

    <!-- Row 3: Charts (2 columns) -->
    <section class="card card-chart">
        <h3>Price & Key Levels</h3>
        <div id="chart-price-levels" class="chart-container"></div>
    </section>

    <section class="card card-chart">
        <h3>Cycle Comparison</h3>
        <div id="chart-cycle-overlay" class="chart-container"></div>
    </section>

    <!-- Row 4: More Charts -->
    <section class="card card-chart">
        <h3>Price Scenarios</h3>
        <div id="chart-scenario-fan" class="chart-container"></div>
    </section>

    <section class="card card-chart">
        <h3>Path to Goal</h3>
        <div id="chart-goal-timeline" class="chart-container"></div>
    </section>

    <!-- Row 5: Nadeau Signals + Alerts + Action -->
    <section class="card">
        <h3>Nadeau Signals</h3>
        <div class="signal-grid">
            {% for signal in nadeau_signals %}
            <div class="signal-row">
                <span class="signal-name">{{ signal.name }}</span>
                <span class="signal-status signal-{{ signal.status | lower }}">
                    {{ signal.status }}
                </span>
            </div>
            {% endfor %}
        </div>
    </section>

    <section class="card">
        <h3>Recent Alerts</h3>
        <div class="alerts-list" id="alerts-list">
            {% for alert in recent_alerts[:5] %}
            <div class="alert-item alert-{{ alert.severity | lower }}">
                <span class="alert-time">{{ alert.triggered_at | time_ago }}</span>
                <span class="alert-name">{{ alert.rule_name }}</span>
                <span class="alert-severity">{{ alert.severity }}</span>
            </div>
            {% endfor %}
            {% if not recent_alerts %}
            <p class="empty-state">No recent alerts</p>
            {% endif %}
        </div>
    </section>

    <section class="card card-action">
        <h3>What Should I Do?</h3>
        <div class="action-recommendation">
            <span class="action-badge action-{{ action_type | lower }}">{{ action_type }}</span>
            <p class="action-explanation">{{ action_explanation }}</p>
        </div>
    </section>

    <!-- Row 6: Portfolio (if exists) -->
    {% if portfolio %}
    <section class="card card-wide">
        <h3>DCA Portfolio</h3>
        <div class="portfolio-grid">
            <div class="portfolio-stat">
                <span class="stat-label">Total BTC</span>
                <span class="stat-value">{{ portfolio.total_btc | format_btc }}</span>
            </div>
            <div class="portfolio-stat">
                <span class="stat-label">Invested</span>
                <span class="stat-value">${{ portfolio.total_invested | format_usd }}</span>
            </div>
            <div class="portfolio-stat">
                <span class="stat-label">Current Value</span>
                <span class="stat-value">${{ portfolio.current_value | format_usd }}</span>
            </div>
            <div class="portfolio-stat">
                <span class="stat-label">ROI</span>
                <span class="stat-value {{ 'up' if portfolio.roi_pct >= 0 else 'down' }}">
                    {{ portfolio.roi_pct | format_pct }}
                </span>
            </div>
        </div>
    </section>
    {% endif %}

</div>
{% endblock %}

{% block scripts %}
<script>
    // Load all interactive charts
    async function loadChart(type, divId) {
        try {
            const resp = await fetch(`/api/chart/${type}`);
            if (!resp.ok) return;
            const fig = await resp.json();
            Plotly.newPlot(divId, fig.data, fig.layout, {
                responsive: true,
                displayModeBar: true,
                modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
                displaylogo: false,
                scrollZoom: false,
            });
        } catch (e) {
            document.getElementById(divId).innerHTML =
                '<p class="chart-error">Chart unavailable. <a href="javascript:location.reload()">Retry</a></p>';
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        loadChart('price_levels', 'chart-price-levels');
        loadChart('cycle_overlay', 'chart-cycle-overlay');
        loadChart('scenario_fan', 'chart-scenario-fan');
        loadChart('goal_timeline', 'chart-goal-timeline');
    });
</script>
{% endblock %}
```

### 5. Template: `web/templates/partner.html`

The partner view reuses the existing couples report design language (traffic light, plain English, progress bar) but as a live web page instead of a static HTML export.

```html
{% extends "base.html" %}
{% block title %}Bitcoin Update — Partner View{% endblock %}

{% block content %}
<div class="partner-container">

    <!-- Traffic Light Signal -->
    <section class="traffic-light-hero traffic-{{ signal_color | lower }}">
        <div class="traffic-circle"></div>
        <h2 class="traffic-label">{{ signal_label }}</h2>
        <p class="traffic-action">{{ signal_action }}</p>
    </section>

    <!-- Price Summary (plain English) -->
    <section class="card partner-card">
        <h3>What's Happening</h3>
        <ul class="plain-list">
            <li>Bitcoin is at <strong>${{ price_usd | format_usd }}</strong>
                ({{ 'up' if change_24h >= 0 else 'down' }} {{ change_24h | abs | format_pct }} today)</li>
            <li>The market mood is <strong>{{ fear_greed_label }}</strong> ({{ fear_greed_value }}/100)</li>
            <li>{{ cycle_explanation }}</li>
        </ul>
    </section>

    <!-- Goal Progress (if exists) -->
    {% if goal_progress %}
    <section class="card partner-card">
        <h3>Our Bitcoin Goal</h3>
        <div class="goal-progress">
            <div class="progress-bar-container">
                <div class="progress-bar-fill" style="width: {{ goal_progress.pct_complete }}%">
                    {{ goal_progress.pct_complete | round(1) }}%
                </div>
            </div>
            <div class="goal-stats">
                <div class="goal-stat">
                    <span class="stat-label">Stacked</span>
                    <span class="stat-value">{{ (goal_progress.total_btc * 100000000) | int | format_sats }} sats</span>
                </div>
                <div class="goal-stat">
                    <span class="stat-label">Worth</span>
                    <span class="stat-value">${{ goal_progress.current_value | format_usd }}</span>
                </div>
                <div class="goal-stat">
                    <span class="stat-label">Remaining</span>
                    <span class="stat-value">~{{ goal_progress.months_remaining }} months</span>
                </div>
            </div>
        </div>
    </section>
    {% endif %}

    <!-- DCA Explanation -->
    <section class="card partner-card">
        <h3>Our Strategy</h3>
        <p>{{ strategy_explanation }}</p>
        <p class="dca-detail">
            At today's price, our ${{ monthly_dca }}/month buys
            <strong>{{ sats_per_month | format_sats }} sats</strong>.
        </p>
    </section>

    <!-- Two Charts -->
    <section class="card partner-card">
        <h3>Where This Could Go</h3>
        <div id="chart-scenario-fan-partner" class="chart-container"></div>
    </section>

    <section class="card partner-card">
        <h3>Path to Our Goal</h3>
        <div id="chart-goal-timeline-partner" class="chart-container"></div>
    </section>

    <!-- Educational Tidbit -->
    <section class="card partner-card fun-fact">
        <h3>Did You Know?</h3>
        <p>{{ education_content }}</p>
    </section>

</div>
{% endblock %}

{% block scripts %}
<script>
    document.addEventListener('DOMContentLoaded', () => {
        loadChart('scenario_fan', 'chart-scenario-fan-partner');
        loadChart('goal_timeline', 'chart-goal-timeline-partner');
    });
</script>
{% endblock %}
```

### 6. Stylesheet: `web/static/style.css`

Single CSS file. No framework. CSS Grid for layout. CSS custom properties for theming. Mobile-first responsive.

```css
/* Root theme — matches dashboard/theme.py and dca/charts.py */
:root {
    --bg: #F0F1F6;
    --card-bg: #FFFFFF;
    --text: #1E272E;
    --text-dim: #636E72;
    --grid: #E4E7ED;
    --orange: #F7931A;
    --green: #00C853;
    --red: #FF1744;
    --blue: #2196F3;
    --gold: #FFD700;
    --radius: 12px;
    --shadow: 0 2px 8px rgba(0,0,0,0.06);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
}

/* Header */
.app-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 24px;
    background: white; border-bottom: 1px solid var(--grid);
    position: sticky; top: 0; z-index: 100;
}
.logo { font-size: 18px; font-weight: 700; color: var(--orange); }
.nav-link { margin-left: 16px; text-decoration: none; color: var(--text-dim); font-size: 14px; }
.nav-link.active { color: var(--orange); font-weight: 600; }

/* Container */
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }

/* Cards */
.card {
    background: var(--card-bg); border-radius: var(--radius);
    padding: 20px; box-shadow: var(--shadow);
}
.card h3 { font-size: 14px; color: var(--text-dim); text-transform: uppercase;
            letter-spacing: 0.5px; margin-bottom: 12px; }

/* Dashboard Grid */
.dashboard-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 16px;
}
.card-hero { grid-column: 1 / -1; display: flex; justify-content: space-between;
             align-items: center; flex-wrap: wrap; }
.card-chart { grid-column: span 1; min-height: 400px; }
.card-wide { grid-column: 1 / -1; }
.card-action { border-left: 4px solid var(--orange); }

/* Chart containers */
.chart-container { width: 100%; min-height: 350px; }

/* Price display */
.price-value { font-size: 36px; font-weight: 800; color: var(--text); }
.price-change { font-size: 18px; margin-left: 12px; font-weight: 600; }
.price-change.up { color: var(--green); }
.price-change.down { color: var(--red); }

/* Signal badges */
.signal-badge {
    display: inline-block; padding: 6px 16px; border-radius: 20px;
    font-weight: 700; font-size: 14px; text-transform: uppercase;
}
.signal-green { background: #E8F5E9; color: #2E7D32; }
.signal-yellow { background: #FFF8E1; color: #F57F17; }
.signal-red { background: #FFEBEE; color: #C62828; }

/* Metric bars */
.metric-bar {
    height: 8px; background: var(--grid); border-radius: 4px;
    overflow: hidden; margin-top: 8px;
}
.metric-bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
.fg-extreme-fear { background: var(--red); }
.fg-fear { background: #FF6B6B; }
.fg-neutral { background: var(--gold); }
.fg-greed { background: #66BB6A; }
.fg-extreme-greed { background: var(--green); }
.cycle-bar { background: var(--orange); }

/* Alerts */
.alert-item {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 0; border-bottom: 1px solid var(--grid);
    font-size: 13px;
}
.alert-item:last-child { border-bottom: none; }
.alert-severity { font-size: 11px; font-weight: 700; text-transform: uppercase;
                   padding: 2px 8px; border-radius: 4px; }
.alert-critical { color: white; background: var(--red); }
.alert-warning { color: #333; background: var(--gold); }
.alert-info { color: white; background: var(--blue); }

/* Partner view */
.partner-container { max-width: 600px; margin: 0 auto; }
.partner-card { margin-bottom: 16px; }
.traffic-light-hero {
    text-align: center; padding: 40px 20px; border-radius: var(--radius);
    margin-bottom: 20px;
}
.traffic-green { background: linear-gradient(135deg, #E8F5E9, #C8E6C9); }
.traffic-yellow { background: linear-gradient(135deg, #FFF8E1, #FFECB3); }
.traffic-red { background: linear-gradient(135deg, #FFEBEE, #FFCDD2); }
.traffic-circle {
    width: 60px; height: 60px; border-radius: 50%; margin: 0 auto 16px;
}
.traffic-green .traffic-circle { background: var(--green); box-shadow: 0 0 20px rgba(0,200,83,0.4); }
.traffic-yellow .traffic-circle { background: var(--gold); box-shadow: 0 0 20px rgba(255,215,0,0.4); }
.traffic-red .traffic-circle { background: var(--red); box-shadow: 0 0 20px rgba(255,23,68,0.4); }

/* Progress bar */
.progress-bar-container {
    height: 24px; background: var(--grid); border-radius: 12px;
    overflow: hidden; margin-bottom: 16px;
}
.progress-bar-fill {
    height: 100%; background: linear-gradient(90deg, var(--orange), var(--gold));
    border-radius: 12px; text-align: center;
    color: white; font-size: 12px; font-weight: 700; line-height: 24px;
    min-width: 40px; transition: width 0.5s ease;
}
.goal-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; text-align: center; }
.stat-label { display: block; font-size: 12px; color: var(--text-dim); }
.stat-value { display: block; font-size: 16px; font-weight: 700; }

/* Portfolio grid */
.portfolio-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }
.portfolio-stat { text-align: center; }

/* Responsive */
@media (max-width: 768px) {
    .dashboard-grid { grid-template-columns: 1fr; }
    .card-hero { flex-direction: column; text-align: center; }
    .price-value { font-size: 28px; }
    .card-chart { min-height: 300px; }
    .app-header { flex-direction: column; gap: 8px; }
}

@media (max-width: 480px) {
    .container { padding: 12px; }
    .card { padding: 16px; }
    .goal-stats { grid-template-columns: 1fr; }
}
```

### 7. Jinja2 Custom Filters

Register in `create_app()`:

```python
@app.template_filter('format_usd')
def format_usd_filter(value):
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value:,.0f}"
    else:
        return f"{value:.2f}"

@app.template_filter('format_pct')
def format_pct_filter(value):
    return f"{value:+.1f}%"

@app.template_filter('format_btc')
def format_btc_filter(value):
    return f"{value:.8f}"

@app.template_filter('format_sats')
def format_sats_filter(value):
    return f"{int(value):,}"

@app.template_filter('time_ago')
def time_ago_filter(timestamp):
    from datetime import datetime
    if isinstance(timestamp, str):
        dt = datetime.fromisoformat(timestamp)
    else:
        dt = timestamp
    delta = datetime.now() - dt
    seconds = delta.total_seconds()
    if seconds < 60: return "just now"
    if seconds < 3600: return f"{int(seconds // 60)}m ago"
    if seconds < 86400: return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"
```

### 8. Data Refresh Strategy

The web dashboard does NOT fetch fresh data from APIs on every page load. Instead:

1. **Page load:** Renders with the latest data from `metrics_snapshots` table (whatever the last `fetch_and_store()` produced)
2. **Auto-refresh (60s):** JavaScript polls `/api/snapshot` which reads from the database
3. **Data freshness:** Depends on the launchd fetch job (see `01-automation-launchd.md`) or manual `python main.py monitor fetch`
4. **Chart data:** Cached for 5 minutes at the Flask level. Charts change slowly (price history, scenarios).

This means the web server itself makes zero external API calls. It's a pure read layer on top of the SQLite database.

### 9. Local Network Access

The Flask server binds to `0.0.0.0` by default, making it accessible from any device on the local network. The CLI prints both `localhost` and the machine's local IP address on startup.

**Typical usage:**
- User's Mac: `http://localhost:5000`
- User's phone (same WiFi): `http://192.168.1.X:5000`
- Partner's phone: `http://192.168.1.X:5000/partner`

**Security model:** No authentication. Assumes trusted home network. The dashboard is read-only (no POST endpoints, no mutations). No sensitive data exposed beyond what the terminal dashboard already shows.

### 10. Modified: `requirements.txt`

Add:
```
flask>=3.0.0            # Web dashboard
```

## Benefits

| Decision | Why | Alternative Considered |
|----------|-----|----------------------|
| **Flask over FastAPI** | Simpler for server-rendered templates. No async needed (all reads from SQLite). Huge ecosystem. | FastAPI — better for pure APIs but overkill for Jinja2 templates |
| **Jinja2 templates over React/Vue** | Zero build step. No npm. Server-rendered pages load fast. Plotly.js handles interactivity. | React SPA — adds npm, webpack, build complexity for marginal benefit |
| **Single CSS file over Tailwind** | No build step. Small file (~200 lines). Easy to maintain. | Tailwind — powerful but requires PostCSS build pipeline |
| **CSS Grid over Bootstrap** | Modern, lightweight, no dependency. Responsive without a framework. | Bootstrap — adds 200KB, opinionated styling |
| **Read-only from SQLite** | Zero API calls from web server. Fast, simple, no rate limit concerns. | Direct API calls — would duplicate the fetch logic and risk rate limits |
| **0.0.0.0 binding** | Phone access on same WiFi network. Primary use case is "check from the couch." | localhost only — would require SSH tunnel for phone access |

## Expectations

- **Page load (full dashboard):** Under 800ms including all 4 chart API calls
- **Page load (partner view):** Under 500ms (2 charts, less data)
- **API response (`/api/snapshot`):** Under 100ms (SQLite read only)
- **API response (`/api/chart/<type>`):** Under 500ms (data preparation + Plotly serialization)
- **Mobile rendering:** Dashboard usable on 375px viewport (iPhone SE). Partner view optimized for mobile.
- **Auto-refresh:** Data updates every 60s without page reload. No visible flicker.
- **Concurrent users:** Supports 5+ simultaneous viewers (Flask dev server is fine for home use)

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Flask dev server crashes under load | Very low (home use, <5 users) | Low — restart `python main.py web` | Document: "For persistent operation, use launchd (see 01-automation-launchd.md)" |
| Phone can't reach Mac on network | Medium (firewall, different subnet) | Medium — partner view inaccessible | Print troubleshooting in CLI: "If phone can't connect, check macOS Firewall settings" |
| SQLite locked during write | Low (WAL mode handles this) | Low — brief read delay | WAL mode already enabled. Flask reads are fast. |
| Plotly.js CDN fails on phone | Very low | Medium — charts don't render | Fallback text: "Charts unavailable." Data tables still work. |
| Stale data if launchd fetch isn't running | Medium | Medium — user sees old prices | Show "data age" prominently. Flash warning if data is > 30 minutes old. |

## Results Criteria

1. **`python main.py web`** starts Flask server and prints local + network URLs
2. **`http://localhost:5000`** renders full dashboard with price, metrics, 4 charts, signals, alerts
3. **`http://localhost:5000/partner`** renders simplified view with traffic light, plain English, goal progress, 2 charts
4. **Phone on same WiFi** can access `http://<mac-ip>:5000/partner` and see the partner view
5. **Auto-refresh** updates price and signal badge every 60s without page reload
6. **All 4 charts** are interactive: hover shows data, zoom works, legend toggles work
7. **Mobile viewport (375px)** renders without horizontal scroll on both views
8. **No external API calls** made by the Flask server (all data from SQLite)
9. **All 165 existing tests still pass** — web module is additive, no regressions

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `web/__init__.py` | **NEW** | Package init |
| `web/app.py` | **NEW** | Flask application factory with routes and API endpoints |
| `web/templates/base.html` | **NEW** | Base template with header, footer, auto-refresh JS |
| `web/templates/dashboard.html` | **NEW** | Full dashboard template |
| `web/templates/partner.html` | **NEW** | Partner-friendly template |
| `web/static/style.css` | **NEW** | Complete stylesheet (CSS Grid, responsive, themed) |
| `main.py` | **MODIFY** | Add `web` command with `--port` and `--host` options |
| `requirements.txt` | **MODIFY** | Add `flask>=3.0.0` |
| `tests/test_web.py` | **NEW** | Tests for Flask routes (status codes, JSON responses, template rendering) |
