"""Tests for the MCP server JSON-RPC protocol handler."""

from __future__ import annotations

import pytest

from gemini_agent_mcp.server import McpServer


FAKE_TOOLS = [
    {
        "name": "test_tool",
        "description": "A tool for testing",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
    },
]


def _noop_handler(name: str, args: dict) -> str:
    return f"called {name}"


@pytest.fixture
def server() -> McpServer:
    return McpServer(tools_list=FAKE_TOOLS, tool_handler=_noop_handler)


def test_initialize_returns_protocol(server: McpServer) -> None:
    response = server.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    })
    assert response is not None
    assert response["id"] == 1
    assert response["jsonrpc"] == "2.0"
    result = response["result"]
    assert "protocolVersion" in result
    assert "serverInfo" in result
    assert result["serverInfo"]["name"] == "gemini-agent-mcp"


def test_tools_list_returns_tools(server: McpServer) -> None:
    response = server.handle({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    })
    assert response is not None
    tools = response["result"]["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 1
    assert tools[0]["name"] == "test_tool"


def test_tools_call_unknown_tool() -> None:
    def handler(name: str, args: dict) -> str:
        raise KeyError(f"Unknown tool: {name}")

    srv = McpServer(tools_list=FAKE_TOOLS, tool_handler=handler)
    response = srv.handle({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "nonexistent", "arguments": {}},
    })
    assert response is not None
    result = response["result"]
    assert result["isError"] is True
    assert "nonexistent" in result["content"][0]["text"]


def test_tools_call_routes_correctly(server: McpServer) -> None:
    response = server.handle({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "test_tool", "arguments": {"q": "hello"}},
    })
    assert response is not None
    result = response["result"]
    assert "isError" not in result
    assert result["content"][0]["text"] == "called test_tool"


def test_notification_initialized_returns_none(server: McpServer) -> None:
    response = server.handle({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    })
    assert response is None
