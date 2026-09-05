from decimal import Decimal

import pytest

from app.services.live_constraints import (
    derive_live_constraints,
)


def account(
    free_usdt: str | None = "20.00",
) -> dict:
    balances = []

    if free_usdt is not None:
        balances.append(
            {
                "asset": "USDT",
                "free": free_usdt,
                "locked": "0.00",
            }
        )

    return {
        "accountType": "SPOT",
        "canTrade": True,
        "permissions": ["TRD_GRP_068"],
        "balances": balances,
    }


def symbol_info() -> dict:
    return {
        "symbol": "SOLUSDT",
        "status": "TRADING",
        "baseAsset": "SOL",
        "quoteAsset": "USDT",
        "orderTypes": [
            "LIMIT",
            "MARKET",
        ],
        "quoteOrderQtyMarketAllowed": True,
        "isSpotTradingAllowed": True,
        "permissionSets": [
            [
                "SPOT",
                "MARGIN",
                "TRD_GRP_068",
            ]
        ],
        "filters": [
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.00100000",
                "maxQty": "90000.00000000",
                "stepSize": "0.00100000",
            },
            {
                "filterType": "NOTIONAL",
                "minNotional": "5.00000000",
                "applyMinToMarket": True,
                "maxNotional": "9000000.00000000",
                "applyMaxToMarket": False,
            },
        ],
    }


def exchange_info() -> dict:
    return {
        "timezone": "UTC",
        "symbols": [
            symbol_info(),
        ],
    }


def test_constraints_are_derived_from_binance_data():
    constraints = derive_live_constraints(
        "SOLUSDT",
        account(),
        exchange_info(),
    )

    assert constraints.symbol == "SOLUSDT"
    assert constraints.base_asset == "SOL"
    assert constraints.quote_asset == "USDT"

    assert (
        constraints.available_balance
        == Decimal("20.00")
    )
    assert (
        constraints.min_notional
        == Decimal("5.00000000")
    )
    assert (
        constraints.min_quantity
        == Decimal("0.00100000")
    )
    assert (
        constraints.quantity_step_size
        == Decimal("0.00100000")
    )
    assert (
        constraints.quote_order_qty_market_allowed
        is True
    )


def test_missing_usdt_balance_becomes_zero():
    constraints = derive_live_constraints(
        "SOLUSDT",
        account(free_usdt=None),
        exchange_info(),
    )

    assert (
        constraints.available_balance
        == Decimal("0")
    )


def test_disabled_account_trading_is_rejected():
    payload = account()
    payload["canTrade"] = False

    with pytest.raises(
        ValueError,
        match="not permitted to trade",
    ):
        derive_live_constraints(
            "SOLUSDT",
            payload,
            exchange_info(),
        )


def test_non_spot_account_is_rejected():
    payload = account()
    payload["accountType"] = "MARGIN"

    with pytest.raises(
        ValueError,
        match="must be a SPOT account",
    ):
        derive_live_constraints(
            "SOLUSDT",
            payload,
            exchange_info(),
        )


def test_non_trading_symbol_is_rejected():
    payload = exchange_info()
    payload["symbols"][0]["status"] = "HALT"

    with pytest.raises(
        ValueError,
        match="not currently TRADING",
    ):
        derive_live_constraints(
            "SOLUSDT",
            account(),
            payload,
        )


def test_missing_spot_permission_is_rejected():
    payload = exchange_info()
    payload["symbols"][0]["permissionSets"] = [
        ["MARGIN"]
    ]

    with pytest.raises(
        ValueError,
        match="SPOT permission is unavailable",
    ):
        derive_live_constraints(
            "SOLUSDT",
            account(),
            payload,
        )


def test_quote_amount_market_support_is_required():
    payload = exchange_info()
    payload["symbols"][0][
        "quoteOrderQtyMarketAllowed"
    ] = False

    with pytest.raises(
        ValueError,
        match="Quote-amount MARKET orders",
    ):
        derive_live_constraints(
            "SOLUSDT",
            account(),
            payload,
        )


def test_minimum_notional_must_apply_to_market():
    payload = exchange_info()
    payload["symbols"][0]["filters"][1][
        "applyMinToMarket"
    ] = False

    with pytest.raises(
        ValueError,
        match="No minimum-notional rule",
    ):
        derive_live_constraints(
            "SOLUSDT",
            account(),
            payload,
        )


def test_usdt_quote_asset_is_required():
    payload = exchange_info()
    payload["symbols"][0]["quoteAsset"] = "BTC"

    with pytest.raises(
        ValueError,
        match="require a USDT quote asset",
    ):
        derive_live_constraints(
            "SOLUSDT",
            account(),
            payload,
        )