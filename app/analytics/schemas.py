from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MarketObservation(BaseModel):
    symbol: str
    event_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Field(ge=0)
    best_bid: Decimal = Field(gt=0)
    best_ask: Decimal = Field(gt=0)
    bid_depth: Decimal = Field(ge=0)
    ask_depth: Decimal = Field(ge=0)


class FeatureSet(BaseModel):
    symbol: str
    event_time: datetime
    relative_volume: float
    volume_z_score: float
    price_change_percent: float
    price_acceleration: float
    realized_volatility: float
    vwap_distance_percent: float
    bid_ask_ratio: float
    spread_percent: float
    liquidity_depth: float


class ScoreResult(BaseModel):
    score: int = Field(ge=0, le=100)
    classification: str
    components: dict[str, int]
    supporting_evidence: list[str]
    counter_evidence: list[str]
