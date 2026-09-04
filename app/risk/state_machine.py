from app.database.models import ProposalStatus

TRANSITIONS = {
    ProposalStatus.CREATED: {ProposalStatus.RISK_REJECTED, ProposalStatus.AWAITING_APPROVAL},
    ProposalStatus.AWAITING_APPROVAL: {
        ProposalStatus.APPROVED,
        ProposalStatus.REJECTED,
        ProposalStatus.EXPIRED,
    },
    ProposalStatus.APPROVED: {ProposalStatus.EXECUTING, ProposalStatus.EXPIRED},
    ProposalStatus.EXECUTING: {
        ProposalStatus.EXECUTED,
        ProposalStatus.FAILED,
        ProposalStatus.UNKNOWN_REQUIRES_RECONCILIATION,
    },
    ProposalStatus.UNKNOWN_REQUIRES_RECONCILIATION: {
        ProposalStatus.EXECUTED,
        ProposalStatus.FAILED,
    },
}


def assert_transition(current: ProposalStatus, target: ProposalStatus) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid proposal transition: {current.value} -> {target.value}")
