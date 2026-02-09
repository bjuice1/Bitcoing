"""
Flask web dashboard for Bitcoin Cycle Monitor.

Two views:
  GET /         — Full dashboard: all metrics, charts, alerts, cycle info, DCA status
  GET /partner  — Partner-friendly: traffic light, plain English, goal progress, 2 charts

API endpoints (consumed by frontend JavaScript):
  GET /api/snapshot        — Latest metrics + signals (JSON)
  GET /api/chart/<type>    — Plotly chart JSON
  GET /api/history         — Price history for custom charting
  GET /api/alerts          — Recent alert records

Started via: python main.py web [--port 5000] [--host 0.0.0.0]
"""
import json
import time
import logging
from datetime import datetime, timezone

from flask import Flask, render_template, jsonify, request

logger = logging.getLogger("btcmonitor.web.app")


def create_app(config: dict, engines: dict) -> Flask:
    """
    Factory function. Receives initialized engines from main.py CLI.

    Args:
        config: Application config dict
        engines: dict of initialized engine objects (monitor, cycle, alert_engine,
                 nadeau, action_engine, db, dca_portfolio, goal_tracker, projector)
    """
    app = Flask(__name__,
                template_folder="templates",
                static_folder="static")

    # Cache for snapshot data
    _cache = {"snapshot": None, "timestamp": 0}
    CACHE_TTL = 300  # 5 minutes

    # ─── Template Filters ────────────────────────────────

    @app.template_filter("format_usd")
    def format_usd_filter(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return "N/A"
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.1f}B"
        elif value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        elif value >= 1_000:
            return f"{value:,.0f}"
        else:
            return f"{value:.2f}"

    @app.template_filter("format_pct")
    def format_pct_filter(value):
        try:
            return f"{float(value):+.1f}%"
        except (TypeError, ValueError):
            return "N/A"

    @app.template_filter("format_btc")
    def format_btc_filter(value):
        try:
            return f"{float(value):.8f}"
        except (TypeError, ValueError):
            return "N/A"

    @app.template_filter("format_sats")
    def format_sats_filter(value):
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return "N/A"

    @app.template_filter("time_ago")
    def time_ago_filter(timestamp):
        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif isinstance(timestamp, datetime):
                dt = timestamp
            else:
                return str(timestamp)
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = now - dt
            seconds = delta.total_seconds()
            if seconds < 60:
                return "just now"
            if seconds < 3600:
                return f"{int(seconds // 60)}m ago"
            if seconds < 86400:
                return f"{int(seconds // 3600)}h ago"
            return f"{int(seconds // 86400)}d ago"
        except Exception:
            return str(timestamp)

    # ─── Data Collection ─────────────────────────────────

    def get_fresh_data() -> dict:
        """Collect all data needed for dashboard rendering from DB."""
        now = time.time()
        if _cache["snapshot"] and (now - _cache["timestamp"]) < CACHE_TTL:
            return _cache["snapshot"]

        monitor = engines["monitor"]
        cycle = engines["cycle"]
        alert_engine = engines["alert_engine"]
        nadeau = engines["nadeau"]
        db = engines["db"]

        data = {
            "price_usd": 0,
            "change_24h": 0,
            "market_cap": 0,
            "signal_color": "YELLOW",
            "signal_label": "Loading...",
            "signal_action": "",
            "fear_greed_value": 50,
            "fear_greed_label": "Neutral",
            "fear_greed_zone": "neutral",
            "mvrv_ratio": 0,
            "mvrv_zone": "N/A",
            "days_since_halving": 0,
            "cycle_pct": 0,
            "drawdown_pct": 0,
            "ath_price": 0,
            "cycle_phase": "Unknown",
            "cycle_explanation": "",
            "nadeau_signals": [],
            "recent_alerts": [],
            "action_type": "HOLD",
            "action_explanation": "Loading data...",
            "portfolio": None,
            "goal_progress": None,
            "monthly_dca": config.get("default_monthly_dca", config.get("dca", {}).get("default_amount", 200)),
            "sats_per_month": 0,
            "strategy_explanation": "Dollar cost averaging: buying a fixed amount regularly regardless of price.",
            "education_content": "Bitcoin has a fixed supply of 21 million coins. No one can create more.",
            "data_age": "Loading...",
        }

        try:
            snapshot = monitor.get_current_status()
            if snapshot:
                price = snapshot.price.price_usd
                data["price_usd"] = price
                data["change_24h"] = snapshot.price.change_24h_pct
                data["market_cap"] = snapshot.price.market_cap

                # Fear & Greed
                fg = snapshot.sentiment.fear_greed_value
                data["fear_greed_value"] = fg or 50
                data["fear_greed_label"] = snapshot.sentiment.fear_greed_label or "N/A"
                if fg:
                    if fg <= 20:
                        data["fear_greed_zone"] = "extreme-fear"
                    elif fg <= 40:
                        data["fear_greed_zone"] = "fear"
                    elif fg <= 60:
                        data["fear_greed_zone"] = "neutral"
                    elif fg <= 80:
                        data["fear_greed_zone"] = "greed"
                    else:
                        data["fear_greed_zone"] = "extreme-greed"

                # MVRV
                mvrv = snapshot.valuation.mvrv_ratio
                data["mvrv_ratio"] = mvrv or 0
                if mvrv:
                    if mvrv < 1:
                        data["mvrv_zone"] = "Undervalued"
                    elif mvrv < 2.5:
                        data["mvrv_zone"] = "Fair Value"
                    elif mvrv < 3.5:
                        data["mvrv_zone"] = "Elevated"
                    else:
                        data["mvrv_zone"] = "Overheated"

                # Cycle
                halving = cycle.get_halving_info()
                data["days_since_halving"] = halving.get("days_since", 0)
                data["cycle_pct"] = halving.get("cycle_pct_elapsed", 0)

                phase = cycle.get_cycle_phase(snapshot)
                phase_val = phase["phase"]
                data["cycle_phase"] = phase_val.value if hasattr(phase_val, "value") else str(phase_val)

                # Drawdown
                dd = cycle.get_drawdown_analysis()
                data["drawdown_pct"] = dd.get("current_drawdown_pct", 0)
                # Compute ATH from drawdown percentage
                if data["drawdown_pct"] and data["drawdown_pct"] < 100:
                    data["ath_price"] = price / (1 - data["drawdown_pct"] / 100)
                else:
                    data["ath_price"] = price

                # Nadeau signals
                signals = cycle.get_nadeau_signals(snapshot)
                nadeau_list = []
                for name, status, value, interp in signals.get("signals", []):
                    s = status.value if hasattr(status, "value") else str(status)
                    nadeau_list.append({"name": name, "status": s, "value": value, "interp": interp})
                data["nadeau_signals"] = nadeau_list

                # Action engine
                if engines.get("action_engine"):
                    try:
                        rec = engines["action_engine"].get_action(snapshot, signals)
                        act_type = rec.action.value if hasattr(rec.action, "value") else str(rec.action)
                        data["action_type"] = act_type
                        data["action_explanation"] = rec.plain_english or rec.headline
                        data["signal_color"] = rec.traffic_light.upper()
                        data["signal_label"] = act_type
                        data["signal_action"] = rec.plain_english or rec.headline
                    except Exception as e:
                        logger.error(f"Action engine error: {e}")

                # Cycle explanation for partner view
                data["cycle_explanation"] = (
                    f"We're on day {data['days_since_halving']} of this Bitcoin cycle "
                    f"({data['cycle_pct']:.0f}% through)."
                )

                # Sats per month
                monthly_dca = data["monthly_dca"]
                if price > 0:
                    data["sats_per_month"] = int(monthly_dca / price * 1e8)

                # Portfolio
                if engines.get("dca_portfolio"):
                    try:
                        portfolios = engines["dca_portfolio"].list_portfolios()
                        if portfolios:
                            total_btc = sum(p.get("total_btc", 0) for p in portfolios)
                            total_invested = sum(p.get("total_invested", 0) for p in portfolios)
                            current_value = total_btc * price
                            roi_pct = ((current_value - total_invested) / total_invested * 100) if total_invested > 0 else 0
                            data["portfolio"] = {
                                "total_btc": total_btc,
                                "total_invested": total_invested,
                                "current_value": current_value,
                                "roi_pct": roi_pct,
                            }
                    except Exception:
                        pass

                # Goal progress
                if engines.get("goal_tracker"):
                    try:
                        data["goal_progress"] = engines["goal_tracker"].get_progress(price)
                    except Exception:
                        pass

            # Recent alerts
            try:
                alerts = db.get_recent_alerts(limit=10)
                data["recent_alerts"] = alerts or []
            except Exception:
                pass

            data["data_age"] = "just now"

        except Exception as e:
            logger.error(f"Error collecting dashboard data: {e}")

        _cache["snapshot"] = data
        _cache["timestamp"] = now
        return data

    # ─── Routes ──────────────────────────────────────────

    @app.route("/")
    def dashboard():
        data = get_fresh_data()
        return render_template("dashboard.html", **data)

    @app.route("/partner")
    def partner():
        data = get_fresh_data()
        return render_template("partner.html", **data)

    @app.route("/about")
    def about():
        """Serve the architecture diagram page."""
        from pathlib import Path
        diagram_path = Path(__file__).parent.parent / "data" / "architecture_diagram.html"
        if diagram_path.exists():
            with open(diagram_path, 'r') as f:
                diagram_html = f.read()
            return diagram_html
        else:
            return "Architecture diagram not found.", 404

    @app.route("/api/snapshot")
    def api_snapshot():
        data = get_fresh_data()
        # Build JSON-safe response
        resp = {
            "price": {
                "usd": data["price_usd"],
                "change_24h_pct": data["change_24h"],
                "market_cap": data["market_cap"],
            },
            "signal": {
                "color": data["signal_color"],
                "label": data["signal_label"],
                "action": data["signal_action"],
            },
            "fear_greed": {
                "value": data["fear_greed_value"],
                "label": data["fear_greed_label"],
            },
            "mvrv": {
                "ratio": data["mvrv_ratio"],
                "zone": data["mvrv_zone"],
            },
            "cycle": {
                "phase": data["cycle_phase"],
                "days_since_halving": data["days_since_halving"],
                "pct": data["cycle_pct"],
            },
            "action": {
                "recommendation": data["action_type"],
                "explanation": data["action_explanation"],
            },
            "alerts_active": len(data["recent_alerts"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_age_seconds": int(time.time() - _cache.get("timestamp", time.time())),
        }
        return jsonify(resp)

    @app.route("/api/chart/<chart_type>")
    def api_chart(chart_type):
        import plotly.io as pio
        from web import charts as web_charts
        from web.chart_data import (
            prepare_scenario_fan_data,
            prepare_cycle_overlay_data,
            prepare_goal_timeline_data,
            prepare_price_levels_data,
        )

        data = get_fresh_data()
        price = data["price_usd"] or 70000

        # Get query parameters with defaults
        monthly_dca = int(request.args.get('monthly_dca', data["monthly_dca"]))
        goal_btc = float(request.args.get('goal_btc', 0.1))

        try:
            if chart_type == "scenario_fan":
                from dca.projections import DCAProjector
                projector = DCAProjector(price)
                projections = projector.compare_projections(monthly_dca)
                chart_data = prepare_scenario_fan_data(projections, price, config, monthly_dca)
                fig = web_charts.scenario_fan(**chart_data)

            elif chart_type == "cycle_overlay":
                db = engines["db"]
                price_history = db.get_price_history()
                halving = engines["cycle"].get_halving_info()
                chart_data = prepare_cycle_overlay_data(price_history, price, halving)
                fig = web_charts.cycle_overlay(**chart_data)

            elif chart_type == "goal_timeline":
                if engines.get("goal_tracker"):
                    # Use custom goal_btc if provided
                    goal_proj = engines["goal_tracker"].project_completion(price, goal_btc=goal_btc)
                    chart_data = prepare_goal_timeline_data(goal_proj, monthly_dca)
                    if chart_data is None:
                        return jsonify({"error": "No active goal"}), 404
                    fig = web_charts.goal_timeline(**chart_data)
                else:
                    return jsonify({"error": "Goal tracker not available"}), 404

            elif chart_type == "price_levels":
                db = engines["db"]
                price_history = db.get_price_history()
                chart_data = prepare_price_levels_data(price_history, price, config)
                if chart_data is None:
                    return jsonify({"error": "No price history"}), 404
                fig = web_charts.price_levels(**chart_data)

            elif chart_type == "dca_backtest":
                # Get backtest data from API
                from dca.engine import DCAEngine
                start = request.args.get('start', '2020-01-01')
                end = request.args.get('end', datetime.now().date().isoformat())
                amount = float(request.args.get('amount', 200))
                frequency = request.args.get('frequency', 'monthly')

                try:
                    engine = DCAEngine(engines["db"])
                    result = engine.simulate(start, end, amount, frequency)
                    fig = web_charts.dca_backtest_chart(
                        time_series=result.time_series,
                        total_invested=result.total_invested,
                        current_value=result.current_value
                    )
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

            else:
                return jsonify({"error": f"Unknown chart type: {chart_type}"}), 404

            return json.loads(pio.to_json(fig))

        except Exception as e:
            logger.error(f"Chart generation error ({chart_type}): {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/history")
    def api_history():
        days = min(int(request.args.get("days", 365)), 5000)
        db = engines["db"]
        history = db.get_price_history(days=days)
        dates = [h["date"] for h in history]
        prices = [h["price_usd"] for h in history]
        return jsonify({"dates": dates, "prices": prices, "count": len(dates)})

    @app.route("/api/alerts")
    def api_alerts():
        limit = min(int(request.args.get("limit", 20)), 100)
        db = engines["db"]
        alerts = db.get_recent_alerts(limit=limit)
        return jsonify({"alerts": alerts or [], "count": len(alerts or [])})

    @app.route("/api/backtest")
    def api_backtest():
        """Run DCA backtest simulation."""
        from dca.engine import DCAEngine

        start = request.args.get('start', '2020-01-01')
        end = request.args.get('end', datetime.now().date().isoformat())
        amount = float(request.args.get('amount', 200))
        frequency = request.args.get('frequency', 'monthly')

        try:
            engine = DCAEngine(engines["db"])
            result = engine.simulate(start, end, amount, frequency)

            return jsonify({
                "total_invested": result.total_invested,
                "current_value": result.current_value,
                "roi_pct": result.roi_pct,
                "total_btc": result.total_btc,
                "avg_cost_basis": result.avg_cost_basis,
                "num_buys": result.num_buys,
                "max_drawdown_pct": result.max_drawdown_pct,
                "time_series": result.time_series,
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"Backtest error: {e}")
            return jsonify({"error": "Simulation failed"}), 500

    return app
