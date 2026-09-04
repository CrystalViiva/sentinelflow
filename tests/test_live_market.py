import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.live_market import (
    MAX_JSON_PAYLOAD_BYTES,
    assert_live_snapshot_fresh,
    build_live_observations,
    parse_json_object,
)


BASE_TIME_MS = 1_700_000_000_000


def make_kline(
    index: int,
    volume: str = "10",
) -> list:
    open_time = BASE_TIME_MS + (index * 60_000)
    close_time = open_time + 59_999

    return [
        open_time,
        "100.00",
        "102.00",
        "99.00",
        "101.00",
        volume,
        close_time,
        "1010.00",
        25,
        "6.00",
        "606.00",
        "0",
    ]


def ticker(symbol: str = "SOLUSDT") -> dict:
    return {
        "symbol": symbol,
        "closeTime": (
            BASE_TIME_MS
            + (5 * 60_000)
            + 30_000
        ),
        "lastPrice": "101.00",
    }


def depth() -> dict:
    return {
        "lastUpdateId": 123456,
        "bids": [
            ["100.00", "2.00"],
            ["99.00", "3.00"],
        ],
        "asks": [
            ["101.00", "4.00"],
            ["102.00", "1.00"],
        ],
    }


def test_build_live_observations_excludes_open_candle():
    klines = [
        make_kline(index, str(10 + index))
        for index in range(6)
    ]

    observations = build_live_observations(
        "SOLUSDT",
        ticker(),
        klines,
        depth(),
    )

    assert len(observations) == 5
    assert observations[-1].volume == Decimal("14")
    assert observations[-1].best_bid == Decimal("100.00")
    assert observations[-1].best_ask == Decimal("101.00")


def test_depth_is_calculated_as_quote_notional():
    observations = build_live_observations(
        "SOLUSDT",
        ticker(),
        [
            make_kline(index)
            for index in range(6)
        ],
        depth(),
    )

    latest = observations[-1]

    assert latest.bid_depth == Decimal("497.0000")
    assert latest.ask_depth == Decimal("506.0000")


def test_ticker_symbol_must_match_requested_symbol():
    with pytest.raises(
        ValueError,
        match="Ticker symbol mismatch",
    ):
        build_live_observations(
            "SOLUSDT",
            ticker("BTCUSDT"),
            [
                make_kline(index)
                for index in range(6)
            ],
            depth(),
        )


def test_crossed_order_book_is_rejected():
    invalid_depth = depth()
    invalid_depth["bids"][0][0] = "102.00"

    with pytest.raises(
        ValueError,
        match="Invalid order book",
    ):
        build_live_observations(
            "SOLUSDT",
            ticker(),
            [
                make_kline(index)
                for index in range(6)
            ],
            invalid_depth,
        )


def test_at_least_five_completed_klines_are_required():
    with pytest.raises(
        ValueError,
        match="At least five completed klines",
    ):
        build_live_observations(
            "SOLUSDT",
            ticker(),
            [
                make_kline(index)
                for index in range(4)
            ],
            depth(),
        )


def test_malformed_kline_is_rejected():
    malformed = [
        make_kline(index)
        for index in range(5)
    ]
    malformed.append(
        [BASE_TIME_MS, "100.00"]
    )

    with pytest.raises(
        ValueError,
        match="must contain at least 12 fields",
    ):
        build_live_observations(
            "SOLUSDT",
            ticker(),
            malformed,
            depth(),
        )


def test_oversized_json_payload_is_rejected():
    oversized = json.dumps(
        {
            "value": (
                "x" * MAX_JSON_PAYLOAD_BYTES
            )
        }
    )

    with pytest.raises(
        ValueError,
        match="exceeds",
    ):
        parse_json_object(
            oversized,
            "ticker_json",
        )


def test_excessive_kline_count_is_rejected():
    excessive_klines = [
        make_kline(index)
        for index in range(201)
    ]

    with pytest.raises(
        ValueError,
        match="200-row limit",
    ):
        build_live_observations(
            "SOLUSDT",
            ticker(),
            excessive_klines,
            depth(),
        )


def test_excessive_depth_is_rejected():
    excessive_depth = depth()
    excessive_depth["bids"] = [
        ["100.00", "1.00"]
        for _ in range(501)
    ]

    with pytest.raises(
        ValueError,
        match="500-level limit",
    ):
        build_live_observations(
            "SOLUSDT",
            ticker(),
            [
                make_kline(index)
                for index in range(6)
            ],
            excessive_depth,
        )


def test_fresh_live_snapshot_is_accepted():
    now = datetime(
        2026,
        9,
        4,
        12,
        0,
        tzinfo=UTC,
    )
    payload = {
        "closeTime": int(
            (
                now - timedelta(seconds=30)
            ).timestamp()
            * 1000
        )
    }

    assert_live_snapshot_fresh(
        payload,
        max_age_seconds=120,
        now=now,
    )


def test_stale_live_snapshot_is_rejected():
    now = datetime(
        2026,
        9,
        4,
        12,
        0,
        tzinfo=UTC,
    )
    payload = {
        "closeTime": int(
            (
                now - timedelta(seconds=121)
            ).timestamp()
            * 1000
        )
    }

    with pytest.raises(
        ValueError,
        match="Live snapshot is stale",
    ):
        assert_live_snapshot_fresh(
            payload,
            max_age_seconds=120,
            now=now,
        )


def test_future_live_snapshot_is_rejected():
    now = datetime(
        2026,
        9,
        4,
        12,
        0,
        tzinfo=UTC,
    )
    payload = {
        "closeTime": int(
            (
                now + timedelta(seconds=6)
            ).timestamp()
            * 1000
        )
    }

    with pytest.raises(
        ValueError,
        match="timestamp cannot be in the future",
    ):
        assert_live_snapshot_fresh(
            payload,
            max_age_seconds=120,
            now=now,
        )