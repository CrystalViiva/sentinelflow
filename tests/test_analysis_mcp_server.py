import asyncio
import json

from mcp import Client

from app.mcp_server.analysis_server import mcp


def test_analysis_server_exposes_only_analysis_tools():
    async def discover() -> set[str]:
        async with Client(mcp) as client:
            result = await client.list_tools()

            return {
                tool.name
                for tool in result.tools
            }

    names = asyncio.run(discover())

    assert names == {
        "analyze_live_snapshot",
        "analyze_replay",
    }


def test_analysis_server_uses_native_objects():
    async def get_schema() -> dict:
        async with Client(mcp) as client:
            result = await client.list_tools()

            tool = next(
                item
                for item in result.tools
                if item.name == "analyze_live_snapshot"
            )

            return tool.input_schema

    schema = asyncio.run(get_schema())
    properties = schema["properties"]

    assert properties["ticker"]["type"] == "object"
    assert properties["klines"]["type"] == "array"
    assert properties["depth"]["type"] == "object"


def test_analysis_server_returns_stale_rejection():
    async def call_tool() -> dict:
        arguments = {
            "symbol": "SOLUSDT",
            "ticker": {
                "symbol": "SOLUSDT",
                "closeTime": 1_700_000_330_000,
                "lastPrice": "101.00",
            },
            "klines": [],
            "depth": {},
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