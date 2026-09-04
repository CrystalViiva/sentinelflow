import pytest

from app.database.models import ProposalStatus
from app.risk.state_machine import assert_transition


def test_valid_transition():
    assert_transition(ProposalStatus.CREATED, ProposalStatus.AWAITING_APPROVAL)


def test_executed_proposal_cannot_execute_again():
    with pytest.raises(ValueError):
        assert_transition(ProposalStatus.EXECUTED, ProposalStatus.EXECUTING)
