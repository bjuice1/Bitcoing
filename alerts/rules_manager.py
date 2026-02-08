"""Alert rules loading and management."""
import logging
import yaml
from pathlib import Path
from models.alerts import AlertRule, CompositeSignal

logger = logging.getLogger("btcmonitor.alerts.rules")


class RulesManager:
    def __init__(self, rules_path="config/alerts_rules.yaml"):
        self.rules_path = Path(rules_path)
        self.rules = []
        self.composites = []
        self.load()

    def load(self):
        if not self.rules_path.exists():
            logger.warning(f"Alert rules file not found: {self.rules_path}")
            return
        with open(self.rules_path) as f:
            data = yaml.safe_load(f) or {}
        self.rules = self._parse_rules(data.get("rules", []))
        self.composites = self._parse_composites(data.get("composites", []))
        logger.info(f"Loaded {len(self.rules)} rules, {len(self.composites)} composites")

    def _parse_rules(self, raw_rules):
        rules = []
        valid_operators = {"<", ">", "<=", ">=", "==", "!="}
        for r in raw_rules:
            if r.get("operator") not in valid_operators:
                logger.warning(f"Invalid operator in rule {r.get('id')}: {r.get('operator')}")
                continue
            rules.append(AlertRule(
                id=r["id"],
                name=r.get("name", r["id"]),
                metric=r["metric"],
                operator=r["operator"],
                threshold=float(r["threshold"]),
                severity=r.get("severity", "INFO"),
                cooldown_seconds=r.get("cooldown_seconds", 3600),
                enabled=r.get("enabled", True),
                description=r.get("description", ""),
            ))
        return rules

    def _parse_composites(self, raw_composites):
        rule_ids = {r.id for r in self.rules}
        composites = []
        for c in raw_composites:
            required = c.get("required_rules", [])
            missing = [r for r in required if r not in rule_ids]
            if missing:
                logger.warning(f"Composite {c.get('id')} references unknown rules: {missing}")
            composites.append(CompositeSignal(
                id=c["id"],
                name=c.get("name", c["id"]),
                description=c.get("description", ""),
                required_rules=required,
                severity=c.get("severity", "WARNING"),
                cooldown_seconds=c.get("cooldown_seconds", 86400),
            ))
        return composites

    def get_enabled_rules(self):
        return [r for r in self.rules if r.enabled]

    def get_rule(self, rule_id):
        for r in self.rules:
            if r.id == rule_id:
                return r
        return None

    def get_all_rules(self):
        return self.rules

    def get_composites(self):
        return self.composites
