import hashlib
import json
from pathlib import Path

from app.analytics.schemas import MarketObservation


def load_replay(path: str | Path) -> list[MarketObservation]:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    events = [MarketObservation.model_validate(item) for item in payload["events"]]
    if len(events) < 5:
        raise ValueError("Replay dataset requires at least five events")
    if any(event.symbol != events[0].symbol for event in events):
        raise ValueError("A replay dataset must contain one symbol")
    return sorted(events, key=lambda event: event.event_time)


def dataset_checksum(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
