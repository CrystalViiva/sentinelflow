import json
from pathlib import Path

from mcp.server import MCPServer

from app.config import get_settings
from app.database.session import SessionLocal
from app.replay.loader import load_replay
from app.security.redaction import redact_text
from app.services.live_market import (
    assert_live_snapshot_fresh,
    build_live_observations,
    parse_json_array,
    parse_json_object,
)
from app.services.scanner import analyze_and_save


mcp = MCPServer(
    "SentinelFlow Analysis",
    instructions=(
        "Read-only market-surveillance MCP server. "
        "This server analyzes replay or live Binance market data. "
        "It cannot create proposals, approve actions, reserve "
        "execution, access account balances, or place orders."
    ),
)


def validation_rejection(
    error: Exception,
) -> str:
    return json.dumps(
        {
            "accepted": False,
            "stage": "live_market_validation",
            "error": redact_text(str(error)),
            "signal_created": False,
            "safety": {
                "proposal_created": False,
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
    Analyze fresh native Binance ticker, kline and depth objects.

    This is analysis-only and cannot create or execute a trade.
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
        return validation_rejection(exc)

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
    """
    Analyze a bundled historical dataset.

    Replay signals can never enter live execution.
    """
    path = (
        Path("data/replay_samples")
        / Path(dataset).name
    )

    if not path.exists():
        raise ValueError(
            "Replay dataset not found"
        )

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
                "source_mode": signal.source_mode,
                "score": signal.score,
                "classification": signal.classification,
                "evidence": signal.evidence,
                "counter_evidence": signal.counter_evidence,
                "safety": {
                    "proposal_created": False,
                    "approved": False,
                    "execution_reserved": False,
                    "binance_order_called": False,
                },
            },
            default=str,
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")