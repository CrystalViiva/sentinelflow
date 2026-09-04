from datetime import UTC, datetime, timedelta
import pytest
from app.services.execution import (assert_live_execution_source, assert_live_signal_fresh,)

@pytest.mark.parametrize("source_mode", ["replay", "paper", "REPLAY", ""])
def test_non_live_sources_cannot_execute(source_mode):
    with pytest.raises(ValueError, match="Live execution requires a live signal"):
        assert_live_execution_source(source_mode)


def test_live_source_can_execute():
    assert_live_execution_source("live")
def test_recent_live_signal_can_execute():
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    observed_at = now - timedelta(seconds=30)

    assert_live_signal_fresh(observed_at, max_age_seconds=120, now=now)


def test_stale_live_signal_is_rejected():
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    observed_at = now - timedelta(seconds=121)

    with pytest.raises(ValueError, match="Live signal is stale"):
        assert_live_signal_fresh(observed_at, max_age_seconds=120, now=now)


def test_future_live_signal_is_rejected():
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    observed_at = now + timedelta(seconds=1)

    with pytest.raises(ValueError, match="cannot be in the future"):
        assert_live_signal_fresh(observed_at, max_age_seconds=120, now=now)


def test_naive_live_signal_timestamp_is_rejected():
    observed_at = datetime(2026, 9, 4, 12, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        assert_live_signal_fresh(observed_at, max_age_seconds=120)