"""Enums for metrics, severity, frequency, and cycle phases."""
from enum import Enum


class MetricName(str, Enum):
    PRICE = "price_usd"
    MARKET_CAP = "market_cap"
    VOLUME = "volume_24h"
    CHANGE_24H = "change_24h_pct"
    HASH_RATE = "hash_rate_th"
    DIFFICULTY = "difficulty"
    BLOCK_TIME = "block_time_avg"
    DIFFICULTY_CHANGE = "difficulty_change_pct"
    SUPPLY_CIRCULATING = "supply_circulating"
    FEAR_GREED = "fear_greed_value"
    MVRV = "mvrv_ratio"
    BTC_GOLD_RATIO = "btc_gold_ratio"
    DOMINANCE = "btc_dominance_pct"
    # Derived metrics (computed, not stored directly)
    DRAWDOWN_FROM_ATH = "drawdown_from_ath"
    HASH_RATE_CHANGE_30D = "hash_rate_change_30d"
    BTC_GOLD_CHANGE_30D = "btc_gold_change_30d"
    PRICE_CHANGE_7D = "price_change_7d"
    PRICE_CHANGE_30D = "price_change_30d"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Frequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class CyclePhase(str, Enum):
    ACCUMULATION = "Accumulation"
    EARLY_BULL = "Early Bull"
    MID_BULL = "Mid Bull"
    LATE_BULL = "Late Bull"
    DISTRIBUTION = "Distribution"
    EARLY_BEAR = "Early Bear"
    MID_BEAR = "Mid Bear"
    CAPITULATION = "Capitulation"


class SignalStatus(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class LTHProxy(str, Enum):
    DISTRIBUTING = "DISTRIBUTING"
    EARLY_ACCUMULATION = "EARLY_ACCUMULATION"
    ACCUMULATING = "ACCUMULATING"
    NEUTRAL = "NEUTRAL"


class ReflexivityState(str, Enum):
    FUD_INTENSIFYING = "FUD_INTENSIFYING"
    FUD_EXHAUSTING = "FUD_EXHAUSTING"
    NARRATIVE_SHIFTING = "NARRATIVE_SHIFTING"
    NEUTRAL = "NEUTRAL"
