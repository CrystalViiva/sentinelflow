import numpy as np
from sklearn.ensemble import IsolationForest

from app.analytics.schemas import FeatureSet

FEATURE_NAMES = (
    "relative_volume",
    "volume_z_score",
    "price_change_percent",
    "realized_volatility",
    "bid_ask_ratio",
    "spread_percent",
)


class AnomalyDetector:
    """Optional secondary signal. It never changes risk limits or approves trades."""

    def __init__(self, contamination: float = 0.05) -> None:
        self.model = IsolationForest(contamination=contamination, random_state=42)
        self.fitted = False

    @staticmethod
    def vector(features: FeatureSet) -> list[float]:
        return [float(getattr(features, name)) for name in FEATURE_NAMES]

    def fit(self, baseline: list[FeatureSet]) -> None:
        if len(baseline) < 20:
            raise ValueError("At least 20 baseline feature sets are required")
        self.model.fit(np.asarray([self.vector(item) for item in baseline]))
        self.fitted = True

    def predict(self, features: FeatureSet) -> dict[str, float | bool]:
        if not self.fitted:
            return {"available": False, "is_anomaly": False, "anomaly_score": 0.0}
        data = np.asarray([self.vector(features)])
        return {
            "available": True,
            "is_anomaly": bool(self.model.predict(data)[0] == -1),
            "anomaly_score": round(float(-self.model.decision_function(data)[0]), 6),
        }
