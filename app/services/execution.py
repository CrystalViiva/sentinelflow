import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models import ExecutionAttempt, ProposalStatus
from app.database.repositories import ProposalRepository
from app.security.redaction import redact_sensitive, redact_text

EXECUTION_FIELDS = (
    "symbol",
    "side",
    "order_type",
    "quote_amount",
    "client_order_id",
)


def assert_live_execution_source(source_mode: str) -> None:
    """Block historical replay and paper signals from entering real execution."""
    if source_mode != "live":
        raise ValueError(
            f"Live execution requires a live signal; received source_mode={source_mode}"
        )


def assert_live_signal_fresh(
    observed_at: datetime,
    max_age_seconds: int,
    now: datetime | None = None,
) -> None:
    """Require timezone-aware, recent market data before execution."""
    if observed_at.tzinfo is None:
        raise ValueError("Live signal timestamp must be timezone-aware")

    current_time = now or datetime.now(UTC)
    age_seconds = (current_time - observed_at).total_seconds()

    if age_seconds < 0:
        raise ValueError("Live signal timestamp cannot be in the future")

    if age_seconds > max_age_seconds:
        raise ValueError(
            f"Live signal is stale: age={age_seconds:.1f}s, "
            f"maximum={max_age_seconds}s"
        )


def assert_execution_payload_matches(
    approved_payload: dict,
    requested_payload: dict,
) -> None:
    """Reject execution if any requested field differs from the approved proposal."""
    missing = [
        field
        for field in EXECUTION_FIELDS
        if field not in requested_payload
    ]
    if missing:
        raise ValueError(
            "Execution payload is missing approved fields: "
            + ", ".join(missing)
        )

    mismatches: list[str] = []

    for field in ("symbol", "side", "order_type", "client_order_id"):
        if requested_payload[field] != approved_payload[field]:
            mismatches.append(field)

    try:
        approved_amount = Decimal(str(approved_payload["quote_amount"]))
        requested_amount = Decimal(str(requested_payload["quote_amount"]))
    except (InvalidOperation, ValueError):
        raise ValueError(
            "Execution quote_amount must be a valid decimal"
        ) from None

    if requested_amount != approved_amount:
        mismatches.append("quote_amount")

    if mismatches:
        raise ValueError(
            "Execution payload does not match human-approved proposal: "
            + ", ".join(mismatches)
        )


def begin_execution(
    db: Session,
    proposal_id: uuid.UUID,
    requested_payload: dict,
):
    """Atomically reserve one exact, approved live proposal for Binance MCP."""
    repo = ProposalRepository(db)
    proposal = repo.get(proposal_id, lock=True)

    if proposal is None:
        raise LookupError("Proposal not found")

    assert_live_execution_source(proposal.signal.source_mode)

    settings = get_settings()
    assert_live_signal_fresh(
        observed_at=proposal.signal.observed_at,
        max_age_seconds=settings.max_live_signal_age_seconds,
    )

    approved_payload = {
        "symbol": proposal.symbol,
        "side": proposal.side,
        "order_type": proposal.order_type,
        "quote_amount": str(proposal.quote_amount),
        "client_order_id": proposal.client_order_id,
    }
    assert_execution_payload_matches(approved_payload, requested_payload)

    completed = db.scalar(
        select(func.count(ExecutionAttempt.id)).where(
            ExecutionAttempt.proposal_id == proposal.id,
            ExecutionAttempt.status == ProposalStatus.EXECUTED.value,
        )
    )
    if completed:
        raise ValueError("Proposal was already executed")

    repo.transition(
        proposal,
        ProposalStatus.EXECUTING,
        actor="mcp_host",
    )

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
        request_payload=approved_payload,
    )

    db.add(attempt)
    db.flush()

    repo.audit(
        proposal.id,
        "EXECUTION_RESERVED",
        {"attempt": attempt_number},
        "mcp_host",
    )

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
    """Record a verified result; unknown outcomes require reconciliation."""
    targets = {
        "executed": ProposalStatus.EXECUTED,
        "failed": ProposalStatus.FAILED,
        "unknown": ProposalStatus.UNKNOWN_REQUIRES_RECONCILIATION,
    }

    if outcome not in targets:
        raise ValueError(
            "Outcome must be executed, failed, or unknown"
        )

    repo = ProposalRepository(db)
    proposal = repo.get(proposal_id, lock=True)
    attempt = db.get(ExecutionAttempt, attempt_id)

    if (
        proposal is None
        or attempt is None
        or attempt.proposal_id != proposal.id
    ):
        raise LookupError("Proposal or execution attempt not found")

    target = targets[outcome]

    repo.transition(
        proposal,
        target,
        actor="mcp_host",
        payload={"attempt_id": str(attempt.id)},
    )

    attempt.status = target.value
    attempt.external_order_id = external_order_id
    attempt.response_payload = redact_sensitive(response_payload or {})
    attempt.error = redact_text(error) if error else None

    db.commit()

    return proposal, attempt