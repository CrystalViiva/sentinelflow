from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ProposalInput(BaseModel):
    signal_id: UUID
    symbol: str = Field(pattern=r"^[A-Z0-9]{5,30}$")
    side: str = Field(default="BUY", pattern=r"^BUY$")
    order_type: str = Field(default="MARKET", pattern=r"^MARKET$")
    quote_amount: Decimal = Field(gt=0)
    score: int = Field(ge=0, le=100)
    spread_percent: Decimal = Field(ge=0)
    min_notional: Decimal = Field(gt=0)
    available_balance: Decimal = Field(ge=0)
    daily_loss_so_far: Decimal = Field(ge=0)
    created_at: datetime
    expires_at: datetime
    equivalent_order_exists: bool = False


class Check(BaseModel):
    name: str
    passed: bool
    observed: str
    required: str


class RiskDecision(BaseModel):
    passed: bool
    checks: list[Check]
