from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.config import Settings
from app.risk.gate import evaluate_risk
from app.risk.idempotency import proposal_idempotency_key
from app.risk.schemas import ProposalInput


def proposal(**overrides):
    now = datetime.now(UTC)
    values = {
        "signal_id": uuid4(),
        "symbol": "SOLUSDT",
        "quote_amount": Decimal(10),
        "score": 85,
        "spread_percent": Decimal("0.04"),
        "min_notional": Decimal(5),
        "available_balance": Decimal(100),
        "daily_loss_so_far": Decimal(0),
        "created_at": now,
        "expires_at": now + timedelta(minutes=1),
    }
    values.update(overrides)
    return ProposalInput(**values)


def test_safe_proposal_passes():
    assert evaluate_risk(proposal(), Settings()).passed


def test_oversized_proposal_is_blocked():
    decision = evaluate_risk(proposal(quote_amount=Decimal(50)), Settings())
    assert not decision.passed
    assert any(item.name == "position_limit" and not item.passed for item in decision.checks)


def test_expired_proposal_is_blocked():
    now = datetime.now(UTC)
    decision = evaluate_risk(
        proposal(created_at=now - timedelta(minutes=2), expires_at=now - timedelta(minutes=1)),
        Settings(),
        now,
    )
    assert not decision.passed


def test_duplicate_is_blocked():
    decision = evaluate_risk(proposal(equivalent_order_exists=True), Settings())
    assert not decision.passed


def test_idempotency_key_is_caller_controlled_and_repeatable():
    request_id = uuid4()
    assert proposal_idempotency_key(request_id) == proposal_idempotency_key(request_id)
    assert proposal_idempotency_key(request_id) != proposal_idempotency_key(uuid4())
