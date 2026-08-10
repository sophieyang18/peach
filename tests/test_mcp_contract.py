import pytest

from backend.app.mcp_server import REQUIRED_TOOLS, peach_mcp


@pytest.mark.asyncio
async def test_mcp_exposes_required_tools() -> None:
    tools = await peach_mcp.list_tools()
    tool_names = {tool.name for tool in tools}

    assert REQUIRED_TOOLS <= tool_names


def test_mcp_is_cloudbase_streamable_http_ready() -> None:
    assert peach_mcp.settings.host == "0.0.0.0"
    assert peach_mcp.settings.streamable_http_path == "/"
    assert peach_mcp.settings.stateless_http is True
    assert peach_mcp.settings.json_response is True
