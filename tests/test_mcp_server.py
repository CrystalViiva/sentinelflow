import asyncio

from mcp import Client

from app.mcp_server.server import mcp


def test_mcp_tool_discovery():
    async def discover() -> set[str]:
        async with Client(mcp) as client:
            result = await client.list_tools()
            return {tool.name for tool in result.tools}

    names = asyncio.run(discover())
    assert {
        "analyze_replay",
        "create_paper_proposal",
        "approve_proposal",
        "reserve_approved_execution",
        "record_execution_result",
    } <= names
