from pathlib import Path

from app.analytics.features import calculate_features
from app.analytics.scoring import score_accumulation
from app.replay.loader import dataset_checksum, load_replay


def test_accumulation_replay_scores_strongly():
    events = load_replay(Path("data/replay_samples/sol_accumulation.json"))
    result = score_accumulation(calculate_features(events))
    assert result.score >= 75
    assert result.classification in {"strong_accumulation", "extreme_anomaly"}


def test_normal_replay_is_not_strong():
    events = load_replay(Path("data/replay_samples/btc_normal.json"))
    result = score_accumulation(calculate_features(events))
    assert result.score < 75


def test_replay_is_deterministic():
    path = Path("data/replay_samples/sol_accumulation.json")
    first = score_accumulation(calculate_features(load_replay(path)))
    second = score_accumulation(calculate_features(load_replay(path)))
    assert first == second
    assert len(dataset_checksum(path)) == 64
