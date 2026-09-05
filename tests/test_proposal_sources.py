from types import SimpleNamespace

import pytest

from app.services.proposals import (
    assert_live_proposal_source,
    assert_paper_proposal_source,
)


def signal(source_mode: str):
    return SimpleNamespace(
        source_mode=source_mode,
    )


@pytest.mark.parametrize(
    "source_mode",
    [
        "replay",
        "paper",
    ],
)
def test_paper_proposal_accepts_non_live_sources(
    source_mode: str,
):
    assert_paper_proposal_source(
        signal(source_mode)
    )


def test_paper_proposal_rejects_live_signal():
    with pytest.raises(
        ValueError,
        match="Paper proposals require",
    ):
        assert_paper_proposal_source(
            signal("live")
        )


def test_live_proposal_accepts_live_signal():
    assert_live_proposal_source(
        signal("live")
    )


@pytest.mark.parametrize(
    "source_mode",
    [
        "replay",
        "paper",
    ],
)
def test_live_proposal_rejects_non_live_sources(
    source_mode: str,
):
    with pytest.raises(
        ValueError,
        match="Live proposals require",
    ):
        assert_live_proposal_source(
            signal(source_mode)
        )