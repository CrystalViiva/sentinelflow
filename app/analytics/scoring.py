from app.analytics.schemas import FeatureSet, ScoreResult


def _scaled(value: float, low: float, high: float, maximum: int) -> int:
    if value <= low:
        return 0
    if value >= high:
        return maximum
    return round((value - low) / (high - low) * maximum)


def score_accumulation(features: FeatureSet) -> ScoreResult:
    components = {
        "relative_volume": _scaled(features.relative_volume, 1.0, 4.0, 25),
        "volume_z_score": _scaled(features.volume_z_score, 0.5, 4.0, 20),
        "order_book_imbalance": _scaled(features.bid_ask_ratio, 1.0, 2.5, 20),
        "price_volume_divergence": _scaled(
            features.relative_volume - max(features.price_change_percent, 0), 0.5, 3.0, 15
        ),
        "volatility": _scaled(features.realized_volatility, 0.1, 2.0, 10),
        "liquidity_quality": max(0, 10 - _scaled(features.spread_percent, 0.03, 0.25, 10)),
    }
    score = min(100, sum(components.values()))
    if score >= 90:
        classification = "extreme_anomaly"
    elif score >= 75:
        classification = "strong_accumulation"
    elif score >= 60:
        classification = "moderate_anomaly"
    elif score >= 40:
        classification = "watch"
    else:
        classification = "normal"

    supporting = []
    counter = []
    if features.relative_volume >= 2:
        supporting.append(f"Relative volume is {features.relative_volume:.2f}x baseline")
    else:
        counter.append("Relative volume is below 2x baseline")
    if features.volume_z_score >= 2:
        supporting.append(f"Volume z-score is {features.volume_z_score:+.2f}")
    if features.bid_ask_ratio >= 1.5:
        supporting.append(f"Bid depth is {features.bid_ask_ratio:.2f}x ask depth")
    else:
        counter.append("Order-book imbalance does not strongly favour bids")
    if features.spread_percent > 0.2:
        counter.append(f"Spread is elevated at {features.spread_percent:.3f}%")
    if abs(features.price_change_percent) < 0.25 and features.relative_volume >= 2:
        supporting.append("Volume expanded before a large price move")
    return ScoreResult(
        score=score,
        classification=classification,
        components=components,
        supporting_evidence=supporting,
        counter_evidence=counter,
    )
