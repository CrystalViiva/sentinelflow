import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ProposalStatus(StrEnum):
    CREATED = "CREATED"
    RISK_REJECTED = "RISK_REJECTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    UNKNOWN_REQUIRES_RECONCILIATION = "UNKNOWN_REQUIRES_RECONCILIATION"


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    score: Mapped[int] = mapped_column(Integer)
    classification: Mapped[str] = mapped_column(String(40))
    source_mode: Mapped[str] = mapped_column(String(20))
    model_version: Mapped[str] = mapped_column(String(30), default="deterministic-v1")
    evidence: Mapped[dict] = mapped_column(JSONB)
    counter_evidence: Mapped[list] = mapped_column(JSONB, default=list)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    proposals: Mapped[list["TradeProposal"]] = relationship(back_populates="signal")


class TradeProposal(Base):
    __tablename__ = "trade_proposals"
    __table_args__ = (Index("ix_one_active_symbol", "symbol", "status"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    client_order_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    side: Mapped[str] = mapped_column(String(8), default="BUY")
    order_type: Mapped[str] = mapped_column(String(20), default="MARKET")
    quote_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    status: Mapped[str] = mapped_column(String(50), default=ProposalStatus.CREATED.value)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal: Mapped[Signal] = relationship(back_populates="proposals")
    checks: Mapped[list["RiskCheck"]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan"
    )
    attempts: Mapped[list["ExecutionAttempt"]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan"
    )


class RiskCheck(Base):
    __tablename__ = "risk_checks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    passed: Mapped[bool]
    observed: Mapped[str] = mapped_column(String(100))
    required: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    proposal: Mapped[TradeProposal] = relationship(back_populates="checks")


class ExecutionAttempt(Base):
    __tablename__ = "execution_attempts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50))
    external_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    proposal: Mapped[TradeProposal] = relationship(back_populates="attempts")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(40), index=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(60), default="system")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
