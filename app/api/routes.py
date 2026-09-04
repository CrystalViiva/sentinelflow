import uuid
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models import Signal
from app.database.repositories import ProposalRepository, SignalRepository
from app.database.session import get_db
from app.replay.loader import load_replay
from app.services.proposals import create_and_evaluate, decide
from app.services.scanner import analyze_and_save

router = APIRouter()
DBSession = Annotated[Session, Depends(get_db)]


class ProposalRequest(BaseModel):
    request_id: uuid.UUID
    signal_id: uuid.UUID
    quote_amount: Decimal = Field(gt=0)
    min_notional: Decimal = Field(default=Decimal(5), gt=0)
    available_balance: Decimal = Field(default=Decimal(100), ge=0)


class DecisionRequest(BaseModel):
    expected_version: int
    approved: bool


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "mode": settings.app_mode.value,
        "live_trading_enabled": settings.live_trading_enabled,
    }


@router.post("/replay/analyze")
def analyze_replay(db: DBSession, dataset: str = "sol_accumulation.json") -> dict:
    safe_name = Path(dataset).name
    path = Path("data/replay_samples") / safe_name
    if not path.exists():
        raise HTTPException(404, "Replay dataset not found")
    signal = analyze_and_save(db, load_replay(path), "replay")
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "score": signal.score,
        "classification": signal.classification,
        "evidence": signal.evidence,
        "counter_evidence": signal.counter_evidence,
    }


@router.get("/signals")
def list_signals(db: DBSession) -> list[dict]:
    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "score": row.score,
            "classification": row.classification,
            "created_at": row.created_at,
        }
        for row in SignalRepository(db).list_recent()
    ]


@router.post("/proposals")
def create_proposal(payload: ProposalRequest, db: DBSession) -> dict:
    signal = db.get(Signal, payload.signal_id)
    if signal is None:
        raise HTTPException(404, "Signal not found")
    try:
        proposal, risk = create_and_evaluate(
            db,
            get_settings(),
            signal,
            payload.quote_amount,
            payload.min_notional,
            payload.available_balance,
            payload.request_id,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "id": proposal.id,
        "status": proposal.status,
        "version": proposal.version,
        "expires_at": proposal.expires_at,
        "risk": risk.model_dump(mode="json"),
    }


@router.post("/proposals/{proposal_id}/decision")
def proposal_decision(proposal_id: uuid.UUID, payload: DecisionRequest, db: DBSession) -> dict:
    try:
        proposal = decide(db, proposal_id, payload.expected_version, payload.approved)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": proposal.id, "status": proposal.status, "version": proposal.version}


@router.get("/proposals")
def list_proposals(db: DBSession) -> list[dict]:
    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "amount": str(row.quote_amount),
            "status": row.status,
            "version": row.version,
            "expires_at": row.expires_at,
        }
        for row in ProposalRepository(db).list_recent()
    ]


@router.get("/proposals/{proposal_id}/audit")
def proposal_audit(proposal_id: uuid.UUID, db: DBSession) -> list[dict]:
    return [
        {
            "event": row.event_type,
            "actor": row.actor,
            "payload": row.payload,
            "created_at": row.created_at,
        }
        for row in ProposalRepository(db).timeline(proposal_id)
    ]
