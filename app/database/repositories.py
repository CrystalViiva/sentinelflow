import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import AuditEvent, ProposalStatus, RiskCheck, Signal, TradeProposal
from app.risk.state_machine import assert_transition


class SignalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        symbol: str,
        score: int,
        classification: str,
        source_mode: str,
        evidence: dict,
        counter_evidence: list,
        observed_at: datetime,
    ) -> Signal:
        signal = Signal(
            symbol=symbol,
            score=score,
            classification=classification,
            source_mode=source_mode,
            evidence=evidence,
            counter_evidence=counter_evidence,
            observed_at=observed_at,
        )
        self.db.add(signal)
        self.db.flush()
        self.audit(signal.id, "SIGNAL_CREATED", {"symbol": symbol, "score": score})
        return signal

    def list_recent(self, limit: int = 50) -> list[Signal]:
        return list(self.db.scalars(select(Signal).order_by(Signal.created_at.desc()).limit(limit)))

    def audit(
        self, aggregate_id: uuid.UUID, event_type: str, payload: dict, actor: str = "system"
    ) -> None:
        self.db.add(
            AuditEvent(
                aggregate_type="signal",
                aggregate_id=aggregate_id,
                event_type=event_type,
                actor=actor,
                payload=payload,
            )
        )


class ProposalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, proposal_id: uuid.UUID, *, lock: bool = False) -> TradeProposal | None:
        statement = select(TradeProposal).where(TradeProposal.id == proposal_id)
        if lock:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_by_idempotency_key(self, key: str) -> TradeProposal | None:
        return self.db.scalar(select(TradeProposal).where(TradeProposal.idempotency_key == key))

    def create(
        self,
        *,
        signal_id: uuid.UUID,
        symbol: str,
        quote_amount: Decimal,
        expires_at: datetime,
        idempotency_key: str,
    ) -> tuple[TradeProposal, bool]:
        existing = self.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing, False
        proposal_id = uuid.uuid4()
        proposal = TradeProposal(
            id=proposal_id,
            signal_id=signal_id,
            idempotency_key=idempotency_key,
            client_order_id=f"sf-{proposal_id.hex[:29]}",
            symbol=symbol,
            quote_amount=quote_amount,
            expires_at=expires_at,
        )
        try:
            with self.db.begin_nested():
                self.db.add(proposal)
                self.db.flush()
        except IntegrityError:
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            return existing, False
        self.audit(proposal.id, "PROPOSAL_CREATED", {"amount": str(quote_amount)})
        return proposal, True

    def transition(
        self,
        proposal: TradeProposal,
        target: ProposalStatus,
        *,
        actor: str,
        payload: dict | None = None,
    ) -> TradeProposal:
        current = ProposalStatus(proposal.status)
        assert_transition(current, target)
        proposal.status = target.value
        proposal.version += 1
        self.audit(proposal.id, f"PROPOSAL_{target.value}", payload or {}, actor)
        self.db.flush()
        return proposal

    def add_checks(self, proposal: TradeProposal, checks: list[dict]) -> None:
        for item in checks:
            self.db.add(RiskCheck(proposal_id=proposal.id, **item))

    def list_recent(self, limit: int = 50) -> list[TradeProposal]:
        return list(
            self.db.scalars(
                select(TradeProposal).order_by(TradeProposal.created_at.desc()).limit(limit)
            )
        )

    def audit(
        self, proposal_id: uuid.UUID, event_type: str, payload: dict, actor: str = "system"
    ) -> None:
        self.db.add(
            AuditEvent(
                aggregate_type="proposal",
                aggregate_id=proposal_id,
                event_type=event_type,
                actor=actor,
                payload=payload,
            )
        )

    def timeline(self, proposal_id: uuid.UUID) -> list[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.aggregate_id == proposal_id)
            .order_by(AuditEvent.created_at.asc())
        )
        return list(self.db.scalars(statement))
