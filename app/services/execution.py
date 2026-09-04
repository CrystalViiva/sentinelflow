import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import ExecutionAttempt, ProposalStatus
from app.database.repositories import ProposalRepository


def begin_execution(db: Session, proposal_id: uuid.UUID):
    """Atomically reserve an approved proposal for one external Binance MCP call."""
    repo = ProposalRepository(db)
    proposal = repo.get(proposal_id, lock=True)
    if proposal is None:
        raise LookupError("Proposal not found")
    completed = db.scalar(
        select(func.count(ExecutionAttempt.id)).where(
            ExecutionAttempt.proposal_id == proposal.id,
            ExecutionAttempt.status == ProposalStatus.EXECUTED.value,
        )
    )
    if completed:
        raise ValueError("Proposal was already executed")
    repo.transition(proposal, ProposalStatus.EXECUTING, actor="mcp_host")
    attempt_number = (
        int(
            db.scalar(
                select(func.count(ExecutionAttempt.id)).where(
                    ExecutionAttempt.proposal_id == proposal.id
                )
            )
            or 0
        )
        + 1
    )
    attempt = ExecutionAttempt(
        proposal_id=proposal.id,
        attempt_number=attempt_number,
        status=ProposalStatus.EXECUTING.value,
        request_payload={
            "symbol": proposal.symbol,
            "side": proposal.side,
            "order_type": proposal.order_type,
            "quote_amount": str(proposal.quote_amount),
            "client_order_id": proposal.client_order_id,
        },
    )
    db.add(attempt)
    db.flush()
    repo.audit(proposal.id, "EXECUTION_RESERVED", {"attempt": attempt_number}, "mcp_host")
    db.commit()
    db.refresh(attempt)
    return proposal, attempt


def finish_execution(
    db: Session,
    proposal_id: uuid.UUID,
    attempt_id: uuid.UUID,
    outcome: str,
    external_order_id: str | None = None,
    response_payload: dict | None = None,
    error: str | None = None,
):
    """Record a verified result. Unknown outcomes require reconciliation, never blind retry."""
    targets = {
        "executed": ProposalStatus.EXECUTED,
        "failed": ProposalStatus.FAILED,
        "unknown": ProposalStatus.UNKNOWN_REQUIRES_RECONCILIATION,
    }
    if outcome not in targets:
        raise ValueError("Outcome must be executed, failed, or unknown")
    repo = ProposalRepository(db)
    proposal = repo.get(proposal_id, lock=True)
    attempt = db.get(ExecutionAttempt, attempt_id)
    if proposal is None or attempt is None or attempt.proposal_id != proposal.id:
        raise LookupError("Proposal or execution attempt not found")
    target = targets[outcome]
    repo.transition(proposal, target, actor="mcp_host", payload={"attempt_id": str(attempt.id)})
    attempt.status = target.value
    attempt.external_order_id = external_order_id
    attempt.response_payload = response_payload or {}
    attempt.error = error
    db.commit()
    return proposal, attempt
