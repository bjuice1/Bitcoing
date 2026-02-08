"""Dataclasses for Bitcoin metrics snapshots."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PriceMetrics:
    price_usd: float = 0.0
    market_cap: float = 0.0
    volume_24h: float = 0.0
    change_24h_pct: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OnchainMetrics:
    hash_rate_th: float = 0.0
    difficulty: float = 0.0
    block_time_avg: float = 600.0  # seconds, ~10 min default
    difficulty_change_pct: float = 0.0
    supply_circulating: float = 0.0
    supply_max: float = 21_000_000.0


@dataclass
class SentimentMetrics:
    fear_greed_value: int = 50
    fear_greed_label: str = "Neutral"
    btc_gold_ratio: float = 0.0
    btc_dominance_pct: float = 0.0


@dataclass
class ValuationMetrics:
    mvrv_ratio: Optional[float] = None
    mvrv_z_score: Optional[float] = None
    realized_cap_est: Optional[float] = None
    mvrv_is_estimated: bool = False


@dataclass
class CombinedSnapshot:
    price: PriceMetrics = field(default_factory=PriceMetrics)
    onchain: OnchainMetrics = field(default_factory=OnchainMetrics)
    sentiment: SentimentMetrics = field(default_factory=SentimentMetrics)
    valuation: ValuationMetrics = field(default_factory=ValuationMetrics)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "api"

    def to_dict(self):
        """Flatten all fields into a single dict for DB storage."""
        d = {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            # Price
            "price_usd": self.price.price_usd,
            "market_cap": self.price.market_cap,
            "volume_24h": self.price.volume_24h,
            "change_24h_pct": self.price.change_24h_pct,
            # Onchain
            "hash_rate_th": self.onchain.hash_rate_th,
            "difficulty": self.onchain.difficulty,
            "block_time_avg": self.onchain.block_time_avg,
            "difficulty_change_pct": self.onchain.difficulty_change_pct,
            "supply_circulating": self.onchain.supply_circulating,
            # Sentiment
            "fear_greed_value": self.sentiment.fear_greed_value,
            "fear_greed_label": self.sentiment.fear_greed_label,
            "btc_gold_ratio": self.sentiment.btc_gold_ratio,
            "btc_dominance_pct": self.sentiment.btc_dominance_pct,
            # Valuation
            "mvrv_ratio": self.valuation.mvrv_ratio,
            "mvrv_z_score": self.valuation.mvrv_z_score,
        }
        return d

    @classmethod
    def from_dict(cls, d):
        """Reconstruct from a flat dict (e.g., DB row)."""
        ts = d.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif ts is None:
            ts = datetime.now(timezone.utc)

        return cls(
            price=PriceMetrics(
                price_usd=d.get("price_usd", 0),
                market_cap=d.get("market_cap", 0),
                volume_24h=d.get("volume_24h", 0),
                change_24h_pct=d.get("change_24h_pct", 0),
                timestamp=ts,
            ),
            onchain=OnchainMetrics(
                hash_rate_th=d.get("hash_rate_th", 0),
                difficulty=d.get("difficulty", 0),
                block_time_avg=d.get("block_time_avg", 600),
                difficulty_change_pct=d.get("difficulty_change_pct", 0),
                supply_circulating=d.get("supply_circulating", 0),
            ),
            sentiment=SentimentMetrics(
                fear_greed_value=d.get("fear_greed_value", 50),
                fear_greed_label=d.get("fear_greed_label", "Neutral"),
                btc_gold_ratio=d.get("btc_gold_ratio", 0),
                btc_dominance_pct=d.get("btc_dominance_pct", 0),
            ),
            valuation=ValuationMetrics(
                mvrv_ratio=d.get("mvrv_ratio"),
                mvrv_z_score=d.get("mvrv_z_score"),
            ),
            timestamp=ts,
            source=d.get("source", "db"),
        )
