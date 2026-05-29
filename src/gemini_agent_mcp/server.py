"""MCP server — stdio JSON-RPC 2.0 protocol handler."""

from __future__ import annotations

import json
import sys

from .config import SERVER_NAME, SERVER_VERSION

PROTOCOL_VERSION = "2024-11-05"


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def make_result(req_id: object, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def make_error(req_id: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def make_tool_response(req_id: object, text: str, is_error: bool = False) -> dict:
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return make_result(req_id, result)


class McpServer:
    def __init__(self, tools_list: list[dict], tool_handler):
        self._tools = tools_list
        self._handle_tool = tool_handler

    def handle(self, request: dict) -> dict | None:
        method = request.get("method", "")
        req_id = request.get("id")

        if method == "initialize":
            return make_result(req_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            })

        if method in ("notifications/initialized", "initialized"):
            return None

        if method == "tools/list":
            return make_result(req_id, {"tools": self._tools})

        if method == "tools/call":
            params = request.get("params", {})
            name = params.get("name", "")
            args = params.get("arguments", {})
            try:
                result_text = self._handle_tool(name, args)
                return make_tool_response(req_id, result_text)
            except Exception as exc:
                return make_tool_response(req_id, f"Error: {exc}", is_error=True)

        if req_id is not None:
            return make_error(req_id, -32601, f"Method not found: {method}")

        return None

    def run(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = self.handle(request)
            if response is not None:
                send(response)
