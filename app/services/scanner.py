from sqlalchemy.orm import Session

from app.analytics.features import calculate_features
from app.analytics.schemas import MarketObservation
from app.analytics.scoring import score_accumulation
from app.database.repositories import SignalRepository


def analyze_and_save(db: Session, observations: list[MarketObservation], source_mode: str):
    features = calculate_features(observations)
    result = score_accumulation(features)
    repository = SignalRepository(db)
    signal = repository.create(
        symbol=features.symbol,
        score=result.score,
        classification=result.classification,
        source_mode=source_mode,
        evidence={
            "features": features.model_dump(mode="json"),
            "components": result.components,
            "supporting_evidence": result.supporting_evidence,
        },
        counter_evidence=result.counter_evidence,
        observed_at=features.event_time,
    )
    db.commit()
    db.refresh(signal)
    return signal
