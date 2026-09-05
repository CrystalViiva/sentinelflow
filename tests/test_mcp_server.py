import asyncio
import json

from mcp import Client

from app.mcp_server.server import mcp


def test_mcp_tool_discovery():
    async def discover() -> set[str]:
        async with Client(mcp) as client:
            result = await client.list_tools()

            return {
                tool.name
                for tool in result.tools
            }

    names = asyncio.run(discover())

    assert {
        "analyze_replay",
        "analyze_live_snapshot",
        "create_paper_proposal",
        "approve_proposal",
        "reserve_approved_execution",
        "record_execution_result",
    } <= names


def test_stale_live_snapshot_returns_structured_rejection():
    async def call_tool() -> dict:
        arguments = {
            "symbol": "SOLUSDT",
            "ticker_json": json.dumps(
                {
                    "symbol": "SOLUSDT",
                    "closeTime": 1_700_000_330_000,
                    "lastPrice": "101.00",
                }
            ),
            "klines_json": json.dumps(
                [
                    [
                        (
                            1_700_000_000_000
                            + (index * 60_000)
                        ),
                        "100",
                        "102",
                        "99",
                        "101",
                        str(10 + index),
                        (
                            1_700_000_000_000
                            + (index * 60_000)
                            + 59_999
                        ),
                        "1010",
                        25,
                        "6",
                        "606",
                        "0",
                    ]
                    for index in range(6)
                ]
            ),
            "depth_json": json.dumps(
                {
                    "lastUpdateId": 123456,
                    "bids": [
                        ["100", "2"],
                        ["99", "3"],
                    ],
                    "asks": [
                        ["101", "4"],
                        ["102", "1"],
                    ],
                }
            ),
        }

        async with Client(mcp) as client:
            result = await client.call_tool(
                "analyze_live_snapshot",
                arguments,
            )

            return json.loads(
                result.content[0].text
            )

    payload = asyncio.run(call_tool())

    assert payload["accepted"] is False
    assert "Live snapshot is stale" in payload["error"]
    assert payload["signal_created"] is False
    assert (
        payload["safety"]["execution_reserved"]
        is False
    )
    assert (
        payload["safety"]["binance_order_called"]
        is False
    )