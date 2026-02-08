"""Dataclasses for alert rules and records."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AlertRule:
    id: str = ""
    name: str = ""
    metric: str = ""
    operator: str = "<"
    threshold: float = 0.0
    severity: str = "INFO"
    cooldown_seconds: int = 3600
    enabled: bool = True
    description: str = ""


@dataclass
class CompositeSignal:
    id: str = ""
    name: str = ""
    description: str = ""
    required_rules: list = field(default_factory=list)
    severity: str = "WARNING"
    cooldown_seconds: int = 86400


@dataclass
class AlertRecord:
    id: Optional[int] = None
    rule_id: str = ""
    rule_name: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    severity: str = "INFO"
    message: str = ""
    triggered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False
