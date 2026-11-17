import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).parents[1] / "src" / "med_scout" / "server.py"

CHICAGO = {"latitude": 41.88, "longitude": -87.62}


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def call_tool(name: str, arguments: dict):
    """Start the server over stdio, like a real MCP client, and call one tool."""
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(name, arguments)


@pytest.mark.anyio
async def test_search_trials_returns_only_illinois_sites():
    result = await call_tool(
        "search_trials",
        {"condition": "breast cancer", "terms": ["HER2-negative"], **CHICAGO},
    )

    assert not result.is_error
    trials = result.structured_content["result"]
    assert trials, "expected at least one recruiting trial near Chicago"
    for trial in trials:
        assert trial["nearest_locations"], f"{trial['nct_id']} has no sites"
        for site in trial["nearest_locations"]:
            assert site["state"] == "Illinois", f"{trial['nct_id']} has a site in {site['state']}"
