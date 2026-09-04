"""Initial SentinelFlow schema."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(30), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("source_mode", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(30), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("counter_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_signals_symbol", "signals", ["symbol"])
    op.create_table(
        "trade_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(120), nullable=False, unique=True),
        sa.Column("client_order_id", sa.String(36), nullable=False, unique=True),
        sa.Column("symbol", sa.String(30), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("quote_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_proposals_signal_id", "trade_proposals", ["signal_id"])
    op.create_index("ix_trade_proposals_symbol", "trade_proposals", ["symbol"])
    op.create_index(
        "ix_trade_proposals_idempotency_key", "trade_proposals", ["idempotency_key"], unique=True
    )
    op.create_index(
        "ix_trade_proposals_client_order_id", "trade_proposals", ["client_order_id"], unique=True
    )
    op.create_index("ix_one_active_symbol", "trade_proposals", ["symbol", "status"])
    op.create_table(
        "risk_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trade_proposals.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("observed", sa.String(100), nullable=False),
        sa.Column("required", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_risk_checks_proposal_id", "risk_checks", ["proposal_id"])
    op.create_table(
        "execution_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trade_proposals.id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("external_order_id", sa.String(100)),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_execution_attempts_proposal_id", "execution_attempts", ["proposal_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor", sa.String(60), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_events_aggregate_type", "audit_events", ["aggregate_type"])
    op.create_index("ix_audit_events_aggregate_id", "audit_events", ["aggregate_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("execution_attempts")
    op.drop_table("risk_checks")
    op.drop_table("trade_proposals")
    op.drop_table("signals")
