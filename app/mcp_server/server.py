import json
import uuid
from datetime import UTC
from decimal import Decimal, InvalidOperation
from pathlib import Path

from mcp.server import MCPServer

from app.config import get_settings
from app.database.repositories import ProposalRepository
from app.database.session import SessionLocal
from app.replay.loader import load_replay
from app.security.redaction import redact_text
from app.services.execution import (
    assert_live_signal_fresh,
    begin_execution,
    finish_execution,
)
from app.services.live_constraints import (
    derive_live_constraints,
)
from app.services.live_market import (
    assert_live_snapshot_fresh,
    build_live_observations,
    parse_json_array,
    parse_json_object,
)
from app.services.proposals import (
    assert_live_proposal_source,
    assert_paper_proposal_source,
    create_and_evaluate,
    decide,
)
from app.services.scanner import analyze_and_save


mcp = MCPServer(
    "SentinelFlow",
    instructions=(
        "Use SentinelFlow for explainable analysis and deterministic "
        "risk controls. Approval never executes a Binance order. "
        "Use the separately authenticated official Binance MCP only "
        "after SentinelFlow returns an approved, unexpired proposal. "
        "Replay and paper signals can never enter live execution. "
        "Live proposals must use account balances and trading rules "
        "supplied from read-only Binance MCP responses. Execution "
        "reservation requires an exact copy of every human-approved "
        "order field."
    ),
)


def validation_rejection(
    error: Exception,
    stage: str,
) -> str:
    return json.dumps(
        {
            "accepted": False,
            "stage": stage,
            "error": redact_text(str(error)),
            "signal_created": False,
            "proposal_created": False,
            "safety": {
                "approved": False,
                "execution_reserved": False,
                "binance_order_called": False,
            },
        }
    )


@mcp.tool()
def analyze_live_snapshot(
    symbol: str,
    ticker: dict,
    klines: list,
    depth: dict,
) -> str:
    """
    Analyze fresh read-only market data returned by Binance MCP.

    Inputs use native MCP objects rather than double-encoded JSON.
    Validation rejections return structured results. This tool cannot
    create, approve, reserve, or execute an order.
    """
    try:
        ticker_payload = parse_json_object(
            json.dumps(
                ticker,
                separators=(",", ":"),
            ),
            "ticker",
        )
        klines_payload = parse_json_array(
            json.dumps(
                klines,
                separators=(",", ":"),
            ),
            "klines",
        )
        depth_payload = parse_json_object(
            json.dumps(
                depth,
                separators=(",", ":"),
            ),
            "depth",
        )

        settings = get_settings()

        assert_live_snapshot_fresh(
            ticker_payload,
            settings.max_live_signal_age_seconds,
        )

        observations = build_live_observations(
            symbol=symbol,
            ticker_payload=ticker_payload,
            klines_payload=klines_payload,
            depth_payload=depth_payload,
        )
    except (TypeError, ValueError) as exc:
        return validation_rejection(
            exc,
            "live_market_validation",
        )

    with SessionLocal() as db:
        signal = analyze_and_save(
            db,
            observations,
            "live",
        )

        return json.dumps(
            {
                "accepted": True,
                "signal_id": str(signal.id),
                "symbol": signal.symbol,
                "source_mode": signal.source_mode,
                "observed_at": signal.observed_at,
                "score": signal.score,
                "classification": signal.classification,
                "evidence": signal.evidence,
                "counter_evidence": signal.counter_evidence,
                "completed_klines_used": len(observations),
                "safety": {
                    "proposal_created": False,
                    "approved": False,
                    "execution_reserved": False,
                    "binance_order_called": False,
                },
            },
            default=str,
        )


@mcp.tool()
def analyze_replay(
    dataset: str = "sol_accumulation.json",
) -> str:
    """Analyze historical data; replay can never execute."""
    path = (
        Path("data/replay_samples")
        / Path(dataset).name
    )

    if not path.exists():
        raise ValueError("Replay dataset not found")

    with SessionLocal() as db:
        signal = analyze_and_save(
            db,
            load_replay(path),
            "replay",
        )

        return json.dumps(
            {
                "signal_id": str(signal.id),
                "symbol": signal.symbol,
                "score": signal.score,
                "classification": signal.classification,
                "source_mode": signal.source_mode,
                "evidence": signal.evidence,
                "counter_evidence": signal.counter_evidence,
            },
            default=str,
        )


@mcp.tool()
def create_paper_proposal(
    signal_id: str,
    quote_amount: str,
    request_id: str,
    min_notional: str = "5",
    available_balance: str = "100",
) -> str:
    """
    Create and risk-check a non-executable paper proposal.

    Live signals are rejected and must use create_live_proposal.
    """
    settings = get_settings()

    with SessionLocal() as db:
        from app.database.models import Signal

        try:
            parsed_signal_id = uuid.UUID(signal_id)
            parsed_request_id = uuid.UUID(request_id)
            parsed_quote_amount = Decimal(quote_amount)
            parsed_min_notional = Decimal(min_notional)
            parsed_available_balance = Decimal(
                available_balance
            )

            signal = db.get(
                Signal,
                parsed_signal_id,
            )

            if signal is None:
                raise LookupError("Signal not found")

            assert_paper_proposal_source(signal)

            proposal, risk = create_and_evaluate(
                db,
                settings,
                signal,
                parsed_quote_amount,
                parsed_min_notional,
                parsed_available_balance,
                parsed_request_id,
            )
        except (
            InvalidOperation,
            LookupError,
            TypeError,
            ValueError,
        ) as exc:
            return validation_rejection(
                exc,
                "paper_proposal_validation",
            )

        return json.dumps(
            {
                "accepted": True,
                "proposal_id": str(proposal.id),
                "status": proposal.status,
                "version": proposal.version,
                "expires_at": proposal.expires_at,
                "source_mode": signal.source_mode,
                "execution_allowed": False,
                "risk": risk.model_dump(mode="json"),
            },
            default=str,
        )


@mcp.tool()
def create_live_proposal(
    signal_id: str,
    quote_amount: str,
    request_id: str,
    account: dict,
    exchange_info: dict,
) -> str:
    """
    Create a live proposal using read-only Binance MCP constraints.

    The account balance and exchange rules are derived from native
    Binance getAccount and exchangeInfo responses. This tool never
    approves, reserves, or executes an order.
    """
    settings = get_settings()

    try:
        account_payload = parse_json_object(
            json.dumps(
                account,
                separators=(",", ":"),
            ),
            "account",
        )
        exchange_payload = parse_json_object(
            json.dumps(
                exchange_info,
                separators=(",", ":"),
            ),
            "exchange_info",
        )
        parsed_signal_id = uuid.UUID(signal_id)
        parsed_request_id = uuid.UUID(request_id)
        parsed_quote_amount = Decimal(quote_amount)
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ) as exc:
        return validation_rejection(
            exc,
            "live_proposal_input_validation",
        )

    with SessionLocal() as db:
        from app.database.models import Signal

        try:
            signal = db.get(
                Signal,
                parsed_signal_id,
            )

            if signal is None:
                raise LookupError("Signal not found")

            assert_live_proposal_source(signal)

            assert_live_signal_fresh(
                observed_at=signal.observed_at,
                max_age_seconds=(
                    settings.max_live_signal_age_seconds
                ),
            )

            constraints = derive_live_constraints(
                symbol=signal.symbol,
                account=account_payload,
                exchange_info=exchange_payload,
            )

            proposal, risk = create_and_evaluate(
                db,
                settings,
                signal,
                parsed_quote_amount,
                constraints.min_notional,
                constraints.available_balance,
                parsed_request_id,
            )
        except (
            InvalidOperation,
            LookupError,
            TypeError,
            ValueError,
        ) as exc:
            return validation_rejection(
                exc,
                "live_proposal_validation",
            )

        return json.dumps(
            {
                "accepted": True,
                "proposal_created": True,
                "proposal_id": str(proposal.id),
                "status": proposal.status,
                "version": proposal.version,
                "expires_at": proposal.expires_at,
                "source_mode": signal.source_mode,
                "risk_passed": risk.passed,
                "execution_allowed": False,
                "constraints": {
                    "symbol": constraints.symbol,
                    "base_asset": constraints.base_asset,
                    "quote_asset": constraints.quote_asset,
                    "available_balance": str(
                        constraints.available_balance
                    ),
                    "min_notional": str(
                        constraints.min_notional
                    ),
                    "min_quantity": str(
                        constraints.min_quantity
                    ),
                    "quantity_step_size": str(
                        constraints.quantity_step_size
                    ),
                    "quote_order_qty_market_allowed": (
                        constraints
                        .quote_order_qty_market_allowed
                    ),
                },
                "risk": risk.model_dump(mode="json"),
                "safety": {
                    "approved": False,
                    "execution_reserved": False,
                    "binance_order_called": False,
                },
            },
            default=str,
        )


@mcp.tool()
def approve_proposal(
    proposal_id: str,
    expected_version: int,
) -> str:
    """Record human approval; never execute or contact Binance."""
    with SessionLocal() as db:
        proposal = decide(
            db,
            uuid.UUID(proposal_id),
            expected_version,
            True,
            actor="mcp_user",
        )

        source_mode = proposal.signal.source_mode

        return json.dumps(
            {
                "proposal_id": str(proposal.id),
                "status": proposal.status,
                "version": proposal.version,
                "client_order_id": proposal.client_order_id,
                "source_mode": source_mode,
                "execution_allowed": (
                    source_mode == "live"
                    and proposal.status == "APPROVED"
                ),
            }
        )


@mcp.tool()
def get_approved_proposal(
    proposal_id: str,
) -> str:
    """Return an approved, unexpired proposal for inspection."""
    from datetime import datetime

    from app.database.models import ProposalStatus

    with SessionLocal() as db:
        proposal = ProposalRepository(db).get(
            uuid.UUID(proposal_id)
        )

        if proposal is None:
            raise ValueError("Proposal not found")

        if (
            proposal.status
            != ProposalStatus.APPROVED.value
        ):
            raise ValueError(
                "Proposal is not approved; "
                f"status={proposal.status}"
            )

        if proposal.expires_at <= datetime.now(UTC):
            raise ValueError("Proposal has expired")

        source_mode = proposal.signal.source_mode

        return json.dumps(
            {
                "proposal_id": str(proposal.id),
                "symbol": proposal.symbol,
                "side": proposal.side,
                "order_type": proposal.order_type,
                "quote_amount": str(
                    proposal.quote_amount
                ),
                "client_order_id": (
                    proposal.client_order_id
                ),
                "source_mode": source_mode,
                "execution_allowed": (
                    source_mode == "live"
                ),
            }
        )


@mcp.tool()
def reserve_approved_execution(
    proposal_id: str,
    symbol: str,
    side: str,
    order_type: str,
    quote_amount: str,
    client_order_id: str,
) -> str:
    """
    Reserve an exact approved live proposal before Binance MCP.

    Every field must match the stored human-approved proposal.
    Replay and paper proposals are rejected.
    """
    requested_payload = {
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "quote_amount": quote_amount,
        "client_order_id": client_order_id,
    }

    with SessionLocal() as db:
        proposal, attempt = begin_execution(
            db,
            uuid.UUID(proposal_id),
            requested_payload,
        )

        return json.dumps(
            {
                "proposal_id": str(proposal.id),
                "attempt_id": str(attempt.id),
                "symbol": proposal.symbol,
                "side": proposal.side,
                "order_type": proposal.order_type,
                "quote_amount": str(
                    proposal.quote_amount
                ),
                "client_order_id": (
                    proposal.client_order_id
                ),
                "source_mode": (
                    proposal.signal.source_mode
                ),
                "next_step": (
                    "Show these exact details to the user. "
                    "Then use the official Binance MCP and "
                    "obtain its separate confirmation."
                ),
            }
        )


@mcp.tool()
def record_execution_result(
    proposal_id: str,
    attempt_id: str,
    outcome: str,
    external_order_id: str = "",
    response_json: str = "{}",
    error: str = "",
) -> str:
    """
    Record a verified Binance result.

    Unknown outcomes require reconciliation and never a blind retry.
    """
    try:
        response_payload = json.loads(
            response_json
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "response_json must be valid JSON"
        ) from exc

    if not isinstance(response_payload, dict):
        raise ValueError(
            "response_json must contain a JSON object"
        )

    with SessionLocal() as db:
        proposal, attempt = finish_execution(
            db,
            uuid.UUID(proposal_id),
            uuid.UUID(attempt_id),
            outcome,
            external_order_id or None,
            response_payload,
            error or None,
        )

        return json.dumps(
            {
                "proposal_id": str(proposal.id),
                "attempt_id": str(attempt.id),
                "status": proposal.status,
            }
        )


@mcp.tool()
def get_audit_timeline(
    proposal_id: str,
) -> str:
    """Return the immutable audit timeline for a proposal."""
    with SessionLocal() as db:
        events = ProposalRepository(db).timeline(
            uuid.UUID(proposal_id)
        )

        return json.dumps(
            [
                {
                    "event": item.event_type,
                    "actor": item.actor,
                    "payload": item.payload,
                    "created_at": item.created_at,
                }
                for item in events
            ],
            default=str,
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")