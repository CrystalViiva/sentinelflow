from datetime import UTC, datetime

from app.config import Settings
from app.risk.schemas import Check, ProposalInput, RiskDecision


def evaluate_risk(
    proposal: ProposalInput, settings: Settings, now: datetime | None = None
) -> RiskDecision:
    now = now or datetime.now(UTC)
    checks = [
        Check(
            name="spot_buy_only",
            passed=proposal.side == "BUY" and proposal.order_type == "MARKET",
            observed=f"{proposal.side} {proposal.order_type}",
            required="BUY MARKET",
        ),
        Check(
            name="score_threshold",
            passed=proposal.score >= settings.min_accumulation_score,
            observed=str(proposal.score),
            required=f">={settings.min_accumulation_score}",
        ),
        Check(
            name="minimum_notional",
            passed=proposal.quote_amount >= proposal.min_notional,
            observed=str(proposal.quote_amount),
            required=f">={proposal.min_notional}",
        ),
        Check(
            name="position_limit",
            passed=proposal.quote_amount <= settings.max_position_usdt,
            observed=str(proposal.quote_amount),
            required=f"<={settings.max_position_usdt}",
        ),
        Check(
            name="available_balance",
            passed=proposal.quote_amount <= proposal.available_balance,
            observed=str(proposal.available_balance),
            required=f">={proposal.quote_amount}",
        ),
        Check(
            name="daily_loss_limit",
            passed=proposal.daily_loss_so_far < settings.max_daily_loss_usdt,
            observed=str(proposal.daily_loss_so_far),
            required=f"<{settings.max_daily_loss_usdt}",
        ),
        Check(
            name="maximum_spread",
            passed=proposal.spread_percent <= settings.max_spread_percent,
            observed=str(proposal.spread_percent),
            required=f"<={settings.max_spread_percent}",
        ),
        Check(
            name="signal_freshness",
            passed=proposal.created_at <= now < proposal.expires_at,
            observed=now.isoformat(),
            required=f"before {proposal.expires_at.isoformat()}",
        ),
        Check(
            name="duplicate_order",
            passed=not proposal.equivalent_order_exists,
            observed=str(proposal.equivalent_order_exists),
            required="False",
        ),
    ]
    return RiskDecision(passed=all(item.passed for item in checks), checks=checks)
