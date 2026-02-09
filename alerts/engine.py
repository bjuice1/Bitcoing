"""Alert evaluation engine."""
import logging
from datetime import datetime, timezone
from models.alerts import AlertRecord
from models.enums import MetricName

logger = logging.getLogger("btcmonitor.alerts.engine")

OPERATOR_MAP = {
    "<": lambda v, t: v < t,
    ">": lambda v, t: v > t,
    "<=": lambda v, t: v <= t,
    ">=": lambda v, t: v >= t,
    "==": lambda v, t: v == t,
    "!=": lambda v, t: v != t,
}


class AlertEngine:
    def __init__(self, rules_manager, db, channels=None):
        self.rules_manager = rules_manager
        self.db = db
        self.channels = channels or []

    def _extract_metric_value(self, snapshot, metric_name, derived=None):
        """Get metric value from snapshot or derived metrics dict."""
        derived = derived or {}
        if metric_name in derived:
            return derived[metric_name]

        # Map metric names to snapshot fields
        field_map = {
            "PRICE": snapshot.price.price_usd,
            "price_usd": snapshot.price.price_usd,
            "MARKET_CAP": snapshot.price.market_cap,
            "market_cap": snapshot.price.market_cap,
            "VOLUME": snapshot.price.volume_24h,
            "CHANGE_24H": snapshot.price.change_24h_pct,
            "HASH_RATE": snapshot.onchain.hash_rate_th,
            "hash_rate_th": snapshot.onchain.hash_rate_th,
            "DIFFICULTY": snapshot.onchain.difficulty,
            "BLOCK_TIME": snapshot.onchain.block_time_avg,
            "DIFFICULTY_CHANGE": snapshot.onchain.difficulty_change_pct,
            "SUPPLY_CIRCULATING": snapshot.onchain.supply_circulating,
            "FEAR_GREED": snapshot.sentiment.fear_greed_value,
            "fear_greed_value": snapshot.sentiment.fear_greed_value,
            "MVRV": snapshot.valuation.mvrv_ratio,
            "mvrv_ratio": snapshot.valuation.mvrv_ratio,
            "BTC_GOLD_RATIO": snapshot.sentiment.btc_gold_ratio,
            "DOMINANCE": snapshot.sentiment.btc_dominance_pct,
            "btc_dominance_pct": snapshot.sentiment.btc_dominance_pct,
        }
        return field_map.get(metric_name)

    def _evaluate_condition(self, value, operator, threshold):
        if value is None:
            return False
        func = OPERATOR_MAP.get(operator)
        if func is None:
            return False
        return func(value, threshold)

    def _check_cooldown(self, rule_id, cooldown_seconds):
        last_time = self.db.get_last_alert_time(rule_id)
        if last_time is None:
            return True
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
        return elapsed >= cooldown_seconds

    def compute_derived_metrics(self, snapshot):
        """Compute derived metrics not directly in the snapshot."""
        derived = {}

        # Drawdown from ATH (from price history)
        history = self.db.get_price_history()
        if history:
            ath = max(r["price_usd"] for r in history)
            current = snapshot.price.price_usd or (history[-1]["price_usd"] if history else 0)
            if ath > 0:
                derived["DRAWDOWN_FROM_ATH"] = ((ath - current) / ath) * 100
                derived["drawdown_from_ath"] = derived["DRAWDOWN_FROM_ATH"]

            # Price changes
            if len(history) >= 7:
                old_7 = history[-7]["price_usd"]
                if old_7 > 0:
                    derived["PRICE_CHANGE_7D"] = ((current - old_7) / old_7) * 100
                    derived["price_change_7d"] = derived["PRICE_CHANGE_7D"]
            if len(history) >= 30:
                old_30 = history[-30]["price_usd"]
                if old_30 > 0:
                    derived["PRICE_CHANGE_30D"] = ((current - old_30) / old_30) * 100
                    derived["price_change_30d"] = derived["PRICE_CHANGE_30D"]

        # Hash rate change (use difficulty change as proxy from snapshot)
        derived["HASH_RATE_CHANGE_30D"] = snapshot.onchain.difficulty_change_pct
        derived["hash_rate_change_30d"] = snapshot.onchain.difficulty_change_pct

        # BTC/Gold 30d change from historical snapshots
        btc_gold_change = self._compute_btc_gold_change_30d(snapshot)
        derived["BTC_GOLD_CHANGE_30D"] = btc_gold_change
        derived["btc_gold_change_30d"] = btc_gold_change

        return derived

    def _compute_btc_gold_change_30d(self, snapshot) -> float:
        """Compare current BTC/Gold ratio to 30-day-old snapshot."""
        try:
            from datetime import timedelta
            thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            old_snapshot = self.db.get_nearest_snapshot(thirty_days_ago)
            if old_snapshot and old_snapshot.get("btc_gold_ratio"):
                current = snapshot.sentiment.btc_gold_ratio
                old = old_snapshot["btc_gold_ratio"]
                if old > 0 and current > 0:
                    return ((current - old) / old) * 100
        except Exception as e:
            logger.debug(f"BTC/Gold 30d calculation failed: {e}")
        return 0.0

    def evaluate_rules(self, snapshot, ignore_cooldowns=False):
        """Evaluate all enabled rules against current snapshot."""
        derived = self.compute_derived_metrics(snapshot)
        triggered = []

        for rule in self.rules_manager.get_enabled_rules():
            value = self._extract_metric_value(snapshot, rule.metric, derived)
            if value is None:
                continue

            if not self._evaluate_condition(value, rule.operator, rule.threshold):
                continue

            if not ignore_cooldowns and not self._check_cooldown(rule.id, rule.cooldown_seconds):
                continue

            record = AlertRecord(
                rule_id=rule.id,
                rule_name=rule.name,
                metric_value=value,
                threshold=rule.threshold,
                severity=rule.severity,
                message=f"{rule.name}: {rule.metric} = {value:.2f} {rule.operator} {rule.threshold} | {rule.description}",
                triggered_at=datetime.now(timezone.utc),
            )
            triggered.append(record)

            if not ignore_cooldowns:
                self.db.save_alert(record)
                self._dispatch(record)

        return triggered

    def evaluate_composites(self, snapshot, triggered_rules):
        """Evaluate composite signals based on which individual rules fired."""
        triggered_ids = {r.rule_id for r in triggered_rules}
        composite_alerts = []

        for composite in self.rules_manager.get_composites():
            if all(rid in triggered_ids for rid in composite.required_rules):
                if not self._check_cooldown(composite.id, composite.cooldown_seconds):
                    continue

                record = AlertRecord(
                    rule_id=composite.id,
                    rule_name=composite.name,
                    metric_value=0,
                    threshold=0,
                    severity=composite.severity,
                    message=f"COMPOSITE: {composite.name} - {composite.description}",
                    triggered_at=datetime.now(timezone.utc),
                )
                composite_alerts.append(record)
                self.db.save_alert(record)
                self._dispatch(record)

        return composite_alerts

    def check(self, snapshot):
        """Main entry point: evaluate all rules and composites."""
        triggered = self.evaluate_rules(snapshot)
        composites = self.evaluate_composites(snapshot, triggered)
        return triggered + composites

    def test_rules(self, snapshot):
        """Evaluate ALL rules ignoring cooldowns, for testing/validation."""
        derived = self.compute_derived_metrics(snapshot)
        results = []

        for rule in self.rules_manager.get_all_rules():
            value = self._extract_metric_value(snapshot, rule.metric, derived)
            would_fire = self._evaluate_condition(value, rule.operator, rule.threshold) if value is not None else False

            results.append({
                "rule_id": rule.id,
                "name": rule.name,
                "metric": rule.metric,
                "operator": rule.operator,
                "threshold": rule.threshold,
                "current_value": value,
                "would_fire": would_fire,
                "severity": rule.severity,
                "enabled": rule.enabled,
            })
        return results

    def get_alert_stats(self, days=30):
        return self.db.get_alert_stats(days)

    def format_alert_summary(self, alerts):
        """Format alerts for display."""
        if not alerts:
            return "All clear - no alerts triggered."
        lines = []
        for a in alerts:
            icon = {"CRITICAL": "!!!", "WARNING": "!!", "INFO": "i"}.get(a.severity, "?")
            lines.append(f"[{icon}] [{a.severity}] {a.message}")
        return "\n".join(lines)

    def _dispatch(self, record):
        for channel in self.channels:
            try:
                channel.send(record)
                if record.severity == "CRITICAL" and hasattr(channel, "send_sound"):
                    channel.send_sound()
            except Exception as e:
                logger.warning(f"Channel dispatch error: {e}")
