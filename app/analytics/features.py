import math
from itertools import pairwise
from statistics import fmean, pstdev

from app.analytics.schemas import FeatureSet, MarketObservation


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


def calculate_features(history: list[MarketObservation]) -> FeatureSet:
    """Calculate explainable features from chronological observations."""
    if len(history) < 5:
        raise ValueError("At least five observations are required")
    latest = history[-1]
    baseline = history[:-1]
    volumes = [float(item.volume) for item in baseline]
    closes = [float(item.close) for item in history]
    volume_mean = fmean(volumes)
    volume_std = pstdev(volumes) or 1.0
    relative_volume = _safe_ratio(float(latest.volume), volume_mean)
    volume_z_score = (float(latest.volume) - volume_mean) / volume_std
    price_change = _safe_ratio(closes[-1] - closes[-2], closes[-2]) * 100
    previous_change = _safe_ratio(closes[-2] - closes[-3], closes[-3]) * 100
    returns = [_safe_ratio(b - a, a) for a, b in pairwise(closes)]
    realized_volatility = (
        (pstdev(returns) if len(returns) > 1 else 0.0) * math.sqrt(len(returns)) * 100
    )
    total_volume = sum(float(item.volume) for item in history)
    vwap = _safe_ratio(
        sum(float(item.close) * float(item.volume) for item in history), total_volume, closes[-1]
    )
    vwap_distance = _safe_ratio(closes[-1] - vwap, vwap) * 100
    bid_ask_ratio = _safe_ratio(float(latest.bid_depth), float(latest.ask_depth), 99.0)
    midpoint = (float(latest.best_bid) + float(latest.best_ask)) / 2
    spread_percent = _safe_ratio(float(latest.best_ask - latest.best_bid), midpoint) * 100
    return FeatureSet(
        symbol=latest.symbol,
        event_time=latest.event_time,
        relative_volume=round(relative_volume, 4),
        volume_z_score=round(volume_z_score, 4),
        price_change_percent=round(price_change, 4),
        price_acceleration=round(price_change - previous_change, 4),
        realized_volatility=round(realized_volatility, 4),
        vwap_distance_percent=round(vwap_distance, 4),
        bid_ask_ratio=round(bid_ask_ratio, 4),
        spread_percent=round(spread_percent, 4),
        liquidity_depth=round(float(latest.bid_depth + latest.ask_depth), 4),
    )
