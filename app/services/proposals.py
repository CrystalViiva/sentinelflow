import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import (
    ProposalStatus,
    Signal,
)
from app.database.repositories import ProposalRepository
from app.risk.gate import evaluate_risk
from app.risk.idempotency import (
    proposal_idempotency_key,
)
from app.risk.schemas import (
    Check,
    ProposalInput,
    RiskDecision,
)


def assert_paper_proposal_source(
    signal: Signal,
) -> None:
    """
    Prevent replay and paper signals from live proposal creation.

    Paper proposals may use replay or explicitly paper-sourced signals,
    but they can never become executable.
    """
    if signal.source_mode not in {
        "replay",
        "paper",
    }:
        raise ValueError(
            "Paper proposals require a replay or paper signal; "
            f"received source_mode={signal.source_mode}"
        )


def assert_live_proposal_source(
    signal: Signal,
) -> None:
    """
    Require a genuinely live-ingested signal for live proposals.
    """
    if signal.source_mode != "live":
        raise ValueError(
            "Live proposals require a live signal; "
            f"received source_mode={signal.source_mode}"
        )


def create_and_evaluate(
    db: Session,
    settings: Settings,
    signal: Signal,
    quote_amount: Decimal,
    min_notional: Decimal,
    available_balance: Decimal,
    request_id: uuid.UUID,
    daily_loss_so_far: Decimal = Decimal(0),
):
    now = datetime.now(UTC)
    expires_at = now + timedelta(
        seconds=settings.signal_expiry_seconds
    )

    repo = ProposalRepository(db)
    proposal, created = repo.create(
        signal_id=signal.id,
        symbol=signal.symbol,
        quote_amount=quote_amount,
        expires_at=expires_at,
        idempotency_key=proposal_idempotency_key(
            request_id
        ),
    )

    if not created:
        if (
            proposal.signal_id != signal.id
            or proposal.quote_amount != quote_amount
        ):
            raise ValueError(
                "Idempotency request_id was already used "
                "with a different payload"
            )

        checks = [
            Check(
                name=item.name,
                passed=item.passed,
                observed=item.observed,
                required=item.required,
            )
            for item in proposal.checks
        ]

        return proposal, RiskDecision(
            passed=(
                bool(checks)
                and all(
                    item.passed
                    for item in checks
                )
            ),
            checks=checks,
        )

    features = signal.evidence.get(
        "features",
        {},
    )

    risk_input = ProposalInput(
        signal_id=signal.id,
        symbol=signal.symbol,
        quote_amount=quote_amount,
        score=signal.score,
        spread_percent=Decimal(
            str(
                features.get(
                    "spread_percent",
                    999,
                )
            )
        ),
        min_notional=min_notional,
        available_balance=available_balance,
        daily_loss_so_far=daily_loss_so_far,
        created_at=now,
        expires_at=expires_at,
    )

    decision = evaluate_risk(
        risk_input,
        settings,
        now,
    )

    repo.add_checks(
        proposal,
        [
            item.model_dump()
            for item in decision.checks
        ],
    )

    target = (
        ProposalStatus.AWAITING_APPROVAL
        if decision.passed
        else ProposalStatus.RISK_REJECTED
    )

    repo.transition(
        proposal,
        target,
        actor="risk_gate",
        payload={
            "passed": decision.passed,
        },
    )

    db.commit()
    db.refresh(proposal)

    return proposal, decision


def decide(
    db: Session,
    proposal_id: uuid.UUID,
    expected_version: int,
    approved: bool,
    actor: str = "dashboard",
):
    repo = ProposalRepository(db)
    proposal = repo.get(
        proposal_id,
        lock=True,
    )

    if proposal is None:
        raise LookupError(
            "Proposal not found"
        )

    if proposal.version != expected_version:
        raise ValueError(
            "Proposal changed; refresh before deciding"
        )

    if proposal.expires_at <= datetime.now(UTC):
        repo.transition(
            proposal,
            ProposalStatus.EXPIRED,
            actor="system",
        )
    else:
        target = (
            ProposalStatus.APPROVED
            if approved
            else ProposalStatus.REJECTED
        )

        repo.transition(
            proposal,
            target,
            actor=actor,
        )

    db.commit()
    db.refresh(proposal)

    return proposal