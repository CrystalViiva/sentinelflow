import json
import uuid
from datetime import UTC
from decimal import Decimal
from pathlib import Path

from mcp.server import MCPServer

from app.config import get_settings
from app.database.repositories import ProposalRepository
from app.database.session import SessionLocal
from app.replay.loader import load_replay
from app.services.execution import begin_execution, finish_execution
from app.services.proposals import create_and_evaluate, decide
from app.services.scanner import analyze_and_save


mcp = MCPServer(
    "SentinelFlow",
    instructions=(
        "Use SentinelFlow for explainable analysis and proposal risk controls. "
        "Approval never executes a Binance order. Use the separately "
        "authenticated official Binance MCP only after SentinelFlow returns "
        "an approved, unexpired proposal. Replay and paper signals can never "
        "enter live execution. Execution reservation requires an exact copy "
        "of every human-approved order field."
    ),
)


@mcp.tool()
def analyze_replay(
    dataset: str = "sol_accumulation.json",
) -> str:
    """Analyze historical data; replay mode can never execute an order."""
    path = Path("data/replay_samples") / Path(dataset).name

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
    """Create and risk-check a paper proposal; never place an order."""
    settings = get_settings()

    with SessionLocal() as db:
        from app.database.models import Signal

        signal = db.get(Signal, uuid.UUID(signal_id))

        if signal is None:
            raise ValueError("Signal not found")

        proposal, risk = create_and_evaluate(
            db,
            settings,
            signal,
            Decimal(quote_amount),
            Decimal(min_notional),
            Decimal(available_balance),
            uuid.UUID(request_id),
        )

        return json.dumps(
            {
                "proposal_id": str(proposal.id),
                "status": proposal.status,
                "version": proposal.version,
                "expires_at": proposal.expires_at,
                "source_mode": signal.source_mode,
                "execution_allowed": signal.source_mode == "live",
                "risk": risk.model_dump(mode="json"),
            },
            default=str,
        )


@mcp.tool()
def approve_proposal(
    proposal_id: str,
    expected_version: int,
) -> str:
    """Record human approval; this never executes or contacts Binance."""
    with SessionLocal() as db:
        proposal = decide(
            db,
            uuid.UUID(proposal_id),
            expected_version,
            True,
            actor="mcp_user",
        )

        return json.dumps(
            {
                "proposal_id": str(proposal.id),
                "status": proposal.status,
                "version": proposal.version,
                "client_order_id": proposal.client_order_id,
                "source_mode": proposal.signal.source_mode,
                "execution_allowed": proposal.signal.source_mode == "live",
            }
        )


@mcp.tool()
def get_approved_proposal(
    proposal_id: str,
) -> str:
    """Return an approved, unexpired proposal for human inspection."""
    from datetime import datetime

    from app.database.models import ProposalStatus

    with SessionLocal() as db:
        proposal = ProposalRepository(db).get(
            uuid.UUID(proposal_id)
        )

        if proposal is None:
            raise ValueError("Proposal not found")

        if proposal.status != ProposalStatus.APPROVED.value:
            raise ValueError(
                f"Proposal is not approved; status={proposal.status}"
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
                "quote_amount": str(proposal.quote_amount),
                "client_order_id": proposal.client_order_id,
                "source_mode": source_mode,
                "execution_allowed": source_mode == "live",
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
    Reserve an exact approved live proposal before calling Binance MCP.

    Every supplied execution field must exactly match the stored,
    human-approved proposal. Replay and paper proposals are rejected.
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
                "quote_amount": str(proposal.quote_amount),
                "client_order_id": proposal.client_order_id,
                "source_mode": proposal.signal.source_mode,
                "next_step": (
                    "Show these exact details to the user. Then use the "
                    "official Binance MCP and obtain its separate confirmation."
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

    Outcome must be executed, failed, or unknown. Unknown outcomes require
    reconciliation and must never trigger a blind retry.
    """
    try:
        response_payload = json.loads(response_json)
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