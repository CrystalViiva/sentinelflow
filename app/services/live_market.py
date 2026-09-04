import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.analytics.schemas import MarketObservation


SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{5,20}$")

MAX_JSON_PAYLOAD_BYTES = 512_000
MAX_KLINES = 200
MAX_DEPTH_LEVELS_PER_SIDE = 500


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a valid decimal"
        ) from exc

    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")

    return result


def _integer(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a valid integer"
        ) from exc


def assert_live_snapshot_fresh(
    ticker_payload: dict,
    max_age_seconds: int,
    now: datetime | None = None,
) -> None:
    """
    Reject stale or future-dated Binance snapshots at ingestion.

    A five-second future tolerance permits minor clock differences.
    """
    snapshot_ms = _integer(
        ticker_payload.get("closeTime"),
        "ticker.closeTime",
    )

    if snapshot_ms <= 0:
        raise ValueError("ticker.closeTime must be positive")

    snapshot_time = datetime.fromtimestamp(
        snapshot_ms / 1000,
        tz=UTC,
    )
    current_time = now or datetime.now(UTC)
    age_seconds = (
        current_time - snapshot_time
    ).total_seconds()

    if age_seconds < -5:
        raise ValueError(
            "Live snapshot timestamp cannot be in the future"
        )

    if age_seconds > max_age_seconds:
        raise ValueError(
            f"Live snapshot is stale: age={age_seconds:.1f}s, "
            f"maximum={max_age_seconds}s"
        )


def _validate_payload_size(
    payload: str,
    field_name: str,
) -> None:
    if not isinstance(payload, str):
        raise ValueError(
            f"{field_name} must be a JSON string"
        )

    payload_size = len(payload.encode("utf-8"))

    if payload_size > MAX_JSON_PAYLOAD_BYTES:
        raise ValueError(
            f"{field_name} exceeds the "
            f"{MAX_JSON_PAYLOAD_BYTES}-byte limit"
        )


def parse_json_object(
    payload: str,
    field_name: str,
) -> dict:
    _validate_payload_size(payload, field_name)

    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{field_name} must be valid JSON"
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(
            f"{field_name} must contain a JSON object"
        )

    return value


def parse_json_array(
    payload: str,
    field_name: str,
) -> list:
    _validate_payload_size(payload, field_name)

    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{field_name} must be valid JSON"
        ) from exc

    if not isinstance(value, list):
        raise ValueError(
            f"{field_name} must contain a JSON array"
        )

    return value


def _validate_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()

    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Symbol must contain 5-20 uppercase letters or digits"
        )

    return normalized


def _parse_book_side(
    levels: Any,
    side_name: str,
) -> list[tuple[Decimal, Decimal]]:
    if not isinstance(levels, list) or not levels:
        raise ValueError(
            f"depth.{side_name} must contain at least one level"
        )

    if len(levels) > MAX_DEPTH_LEVELS_PER_SIDE:
        raise ValueError(
            f"depth.{side_name} exceeds the "
            f"{MAX_DEPTH_LEVELS_PER_SIDE}-level limit"
        )

    parsed: list[tuple[Decimal, Decimal]] = []

    for index, level in enumerate(levels):
        if not isinstance(level, list) or len(level) < 2:
            raise ValueError(
                f"depth.{side_name}[{index}] must contain "
                "price and quantity"
            )

        price = _decimal(
            level[0],
            f"depth.{side_name}[{index}].price",
        )
        quantity = _decimal(
            level[1],
            f"depth.{side_name}[{index}].quantity",
        )

        if price <= 0:
            raise ValueError(
                f"depth.{side_name}[{index}].price "
                "must be positive"
            )

        if quantity < 0:
            raise ValueError(
                f"depth.{side_name}[{index}].quantity "
                "cannot be negative"
            )

        parsed.append((price, quantity))

    return parsed


def build_live_observations(
    symbol: str,
    ticker_payload: dict,
    klines_payload: list,
    depth_payload: dict,
) -> list[MarketObservation]:
    """
    Convert read-only Binance MCP responses into observations.

    The ticker closeTime acts as the snapshot clock. Klines whose
    close time is later than that clock are still open and excluded.
    """
    normalized_symbol = _validate_symbol(symbol)

    ticker_symbol = str(
        ticker_payload.get("symbol", "")
    ).upper()

    if ticker_symbol != normalized_symbol:
        raise ValueError(
            f"Ticker symbol mismatch: expected {normalized_symbol}, "
            f"received {ticker_symbol or 'missing'}"
        )

    snapshot_ms = _integer(
        ticker_payload.get("closeTime"),
        "ticker.closeTime",
    )

    if snapshot_ms <= 0:
        raise ValueError("ticker.closeTime must be positive")

    if not isinstance(klines_payload, list):
        raise ValueError(
            "klines must contain a JSON array"
        )

    if len(klines_payload) > MAX_KLINES:
        raise ValueError(
            f"klines exceeds the {MAX_KLINES}-row limit"
        )

    if not isinstance(depth_payload, dict):
        raise ValueError(
            "depth must contain a JSON object"
        )

    _integer(
        depth_payload.get("lastUpdateId"),
        "depth.lastUpdateId",
    )

    bids = _parse_book_side(
        depth_payload.get("bids"),
        "bids",
    )
    asks = _parse_book_side(
        depth_payload.get("asks"),
        "asks",
    )

    best_bid = max(price for price, _ in bids)
    best_ask = min(price for price, _ in asks)

    if best_bid >= best_ask:
        raise ValueError(
            f"Invalid order book: best bid {best_bid} "
            f"must be below best ask {best_ask}"
        )

    bid_depth = sum(
        (
            price * quantity
            for price, quantity in bids
        ),
        start=Decimal("0"),
    )
    ask_depth = sum(
        (
            price * quantity
            for price, quantity in asks
        ),
        start=Decimal("0"),
    )

    completed_rows: list[tuple[int, list]] = []

    for index, row in enumerate(klines_payload):
        if not isinstance(row, list) or len(row) < 12:
            raise ValueError(
                f"klines[{index}] must contain at least 12 fields"
            )

        open_time_ms = _integer(
            row[0],
            f"klines[{index}].openTime",
        )
        close_time_ms = _integer(
            row[6],
            f"klines[{index}].closeTime",
        )

        if open_time_ms > close_time_ms:
            raise ValueError(
                f"klines[{index}] open time cannot be after "
                "its close time"
            )

        if close_time_ms <= snapshot_ms:
            completed_rows.append(
                (close_time_ms, row)
            )

    completed_rows.sort(
        key=lambda item: item[0]
    )

    if len(completed_rows) < 5:
        raise ValueError(
            "At least five completed klines are required; "
            "request a larger Binance kline limit"
        )

    close_times = [
        close_time
        for close_time, _ in completed_rows
    ]

    if len(close_times) != len(set(close_times)):
        raise ValueError(
            "Completed klines contain duplicate close times"
        )

    observations: list[MarketObservation] = []

    for close_time_ms, row in completed_rows:
        observation = MarketObservation(
            symbol=normalized_symbol,
            event_time=datetime.fromtimestamp(
                close_time_ms / 1000,
                tz=UTC,
            ),
            open=_decimal(row[1], "kline.open"),
            high=_decimal(row[2], "kline.high"),
            low=_decimal(row[3], "kline.low"),
            close=_decimal(row[4], "kline.close"),
            volume=_decimal(row[5], "kline.volume"),
            best_bid=best_bid,
            best_ask=best_ask,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
        )
        observations.append(observation)

    return observations