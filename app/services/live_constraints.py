import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{5,20}$")


@dataclass(frozen=True)
class LiveTradingConstraints:
    symbol: str
    base_asset: str
    quote_asset: str
    available_balance: Decimal
    min_notional: Decimal
    min_quantity: Decimal
    quantity_step_size: Decimal
    quote_order_qty_market_allowed: bool


def _decimal(
    value: Any,
    field_name: str,
) -> Decimal:
    try:
        result = Decimal(str(value))
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{field_name} must be a valid decimal"
        ) from exc

    if not result.is_finite():
        raise ValueError(
            f"{field_name} must be finite"
        )

    return result


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()

    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Symbol must contain 5-20 uppercase letters or digits"
        )

    return normalized


def _find_symbol_info(
    exchange_info: dict,
    symbol: str,
) -> dict:
    symbols = exchange_info.get("symbols")

    if not isinstance(symbols, list):
        raise ValueError(
            "exchange_info.symbols must be an array"
        )

    matches = [
        item
        for item in symbols
        if (
            isinstance(item, dict)
            and str(item.get("symbol", "")).upper()
            == symbol
        )
    ]

    if not matches:
        raise ValueError(
            f"{symbol} was not found in exchange information"
        )

    if len(matches) != 1:
        raise ValueError(
            f"Exchange information contains duplicate {symbol} entries"
        )

    return matches[0]


def _spot_permission_is_allowed(
    symbol_info: dict,
) -> bool:
    permission_sets = symbol_info.get("permissionSets")

    if permission_sets is None:
        return True

    if not isinstance(permission_sets, list):
        raise ValueError(
            "symbol.permissionSets must be an array"
        )

    flattened = {
        str(permission).upper()
        for permission_set in permission_sets
        if isinstance(permission_set, list)
        for permission in permission_set
    }

    return "SPOT" in flattened


def _find_filter(
    symbol_info: dict,
    filter_type: str,
) -> dict:
    filters = symbol_info.get("filters")

    if not isinstance(filters, list):
        raise ValueError(
            "symbol.filters must be an array"
        )

    matches = [
        item
        for item in filters
        if (
            isinstance(item, dict)
            and item.get("filterType") == filter_type
        )
    ]

    if not matches:
        raise ValueError(
            f"Required {filter_type} filter is missing"
        )

    if len(matches) != 1:
        raise ValueError(
            f"Duplicate {filter_type} filters found"
        )

    return matches[0]


def _minimum_market_notional(
    symbol_info: dict,
) -> Decimal:
    filters = symbol_info.get("filters")

    if not isinstance(filters, list):
        raise ValueError(
            "symbol.filters must be an array"
        )

    applicable: list[Decimal] = []

    for item in filters:
        if not isinstance(item, dict):
            continue

        filter_type = item.get("filterType")

        if (
            filter_type == "NOTIONAL"
            and item.get("applyMinToMarket") is True
        ):
            applicable.append(
                _decimal(
                    item.get("minNotional"),
                    "NOTIONAL.minNotional",
                )
            )

        if (
            filter_type == "MIN_NOTIONAL"
            and item.get("applyToMarket") is not False
        ):
            applicable.append(
                _decimal(
                    item.get("minNotional"),
                    "MIN_NOTIONAL.minNotional",
                )
            )

    if not applicable:
        raise ValueError(
            "No minimum-notional rule applies to MARKET orders"
        )

    minimum = max(applicable)

    if minimum <= 0:
        raise ValueError(
            "Minimum MARKET notional must be positive"
        )

    return minimum


def _available_quote_balance(
    account: dict,
    quote_asset: str,
) -> Decimal:
    balances = account.get("balances")

    if not isinstance(balances, list):
        raise ValueError(
            "account.balances must be an array"
        )

    matches = [
        item
        for item in balances
        if (
            isinstance(item, dict)
            and str(item.get("asset", "")).upper()
            == quote_asset
        )
    ]

    if len(matches) > 1:
        raise ValueError(
            f"Account contains duplicate {quote_asset} balances"
        )

    if not matches:
        return Decimal("0")

    available = _decimal(
        matches[0].get("free"),
        f"account.balances.{quote_asset}.free",
    )

    if available < 0:
        raise ValueError(
            f"{quote_asset} free balance cannot be negative"
        )

    return available


def derive_live_constraints(
    symbol: str,
    account: dict,
    exchange_info: dict,
) -> LiveTradingConstraints:
    normalized_symbol = _normalize_symbol(symbol)

    if not isinstance(account, dict):
        raise ValueError(
            "account must be an object"
        )

    if not isinstance(exchange_info, dict):
        raise ValueError(
            "exchange_info must be an object"
        )

    if account.get("accountType") != "SPOT":
        raise ValueError(
            "Agentic account must be a SPOT account"
        )

    if account.get("canTrade") is not True:
        raise ValueError(
            "Agentic account is not permitted to trade"
        )

    symbol_info = _find_symbol_info(
        exchange_info,
        normalized_symbol,
    )

    if symbol_info.get("status") != "TRADING":
        raise ValueError(
            f"{normalized_symbol} is not currently TRADING"
        )

    if symbol_info.get("isSpotTradingAllowed") is not True:
        raise ValueError(
            f"Spot trading is not allowed for {normalized_symbol}"
        )

    if not _spot_permission_is_allowed(symbol_info):
        raise ValueError(
            f"SPOT permission is unavailable for {normalized_symbol}"
        )

    order_types = symbol_info.get("orderTypes")

    if (
        not isinstance(order_types, list)
        or "MARKET" not in order_types
    ):
        raise ValueError(
            f"MARKET orders are not supported for {normalized_symbol}"
        )

    if (
        symbol_info.get("quoteOrderQtyMarketAllowed")
        is not True
    ):
        raise ValueError(
            f"Quote-amount MARKET orders are not allowed for "
            f"{normalized_symbol}"
        )

    base_asset = str(
        symbol_info.get("baseAsset", "")
    ).upper()
    quote_asset = str(
        symbol_info.get("quoteAsset", "")
    ).upper()

    if not base_asset:
        raise ValueError(
            "Symbol base asset is missing"
        )

    if quote_asset != "USDT":
        raise ValueError(
            "SentinelFlow live proposals currently require "
            "a USDT quote asset"
        )

    lot_size = _find_filter(
        symbol_info,
        "LOT_SIZE",
    )

    min_quantity = _decimal(
        lot_size.get("minQty"),
        "LOT_SIZE.minQty",
    )
    quantity_step_size = _decimal(
        lot_size.get("stepSize"),
        "LOT_SIZE.stepSize",
    )

    if min_quantity <= 0:
        raise ValueError(
            "LOT_SIZE.minQty must be positive"
        )

    if quantity_step_size <= 0:
        raise ValueError(
            "LOT_SIZE.stepSize must be positive"
        )

    return LiveTradingConstraints(
        symbol=normalized_symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        available_balance=_available_quote_balance(
            account,
            quote_asset,
        ),
        min_notional=_minimum_market_notional(
            symbol_info
        ),
        min_quantity=min_quantity,
        quantity_step_size=quantity_step_size,
        quote_order_qty_market_allowed=True,
    )