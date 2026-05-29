"""Bootstrap and run the MCP server."""

from __future__ import annotations

import json
import sys

from .config import load_api_key
from .server import McpServer


def _build_tools_list() -> list[dict]:
    return [
        {
            "name": "gemini_agent",
            "description": (
                "Run Gemini as an autonomous agent with a function-calling tool loop. "
                "Gemini reads files, greps, globs, and optionally runs bash commands "
                "to analyze a codebase, then returns a final synthesis. "
                "Use for: architecture analysis, code review, log triage, "
                "dependency mapping, pattern detection."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The analysis task for Gemini to perform",
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Absolute path to the project root (sandbox boundary). Defaults to cwd.",
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of specific files to focus on (paths relative to project_root)",
                    },
                    "max_turns": {
                        "type": "integer",
                        "description": "Maximum agent loop iterations (default: 15)",
                    },
                    "allow_bash": {
                        "type": "boolean",
                        "description": "Enable bash tool for Gemini (default: false, read-only)",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Resume a previous session (Gemini remembers prior context)",
                    },
                    "model": {
                        "type": "string",
                        "description": "Gemini model to use (default: gemini-3.5-flash)",
                    },
                },
                "required": ["task"],
            },
        },
        {
            "name": "gemini_status",
            "description": (
                "Show Gemini agent cost and usage stats from the cost log."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "today_only": {
                        "type": "boolean",
                        "description": "Only show today's usage (default: true)",
                    },
                },
            },
        },
    ]


def _handle_tool(name: str, args: dict) -> str:
    if name == "gemini_agent":
        return _handle_gemini_agent(args)
    if name == "gemini_status":
        return _handle_gemini_status(args)
    raise ValueError(f"Unknown tool: {name}")


def _handle_gemini_agent(args: dict) -> str:
    from .agent_loop import run_agent

    task = args.get("task", "").strip()
    if not task:
        raise ValueError("Missing required argument: task")

    api_key = load_api_key()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not found. Set it as an environment variable "
            "or in a .env file."
        )

    result = run_agent(
        api_key=api_key,
        task=task,
        project_root=args.get("project_root"),
        files=args.get("files"),
        max_turns=args.get("max_turns"),
        allow_bash=args.get("allow_bash", False),
        session_id=args.get("session_id"),
        model=args.get("model"),
    )

    parts = [result["text"]]
    meta = result.get("meta", {})
    if meta:
        parts.append("\n---")
        parts.append(f"Turns: {meta.get('turns', '?')} | "
                     f"Tools: {meta.get('tool_calls', '?')} | "
                     f"In: {meta.get('in_tokens', '?')} | "
                     f"Out: {meta.get('out_tokens', '?')} | "
                     f"Cost: ${meta.get('cost_usd', 0):.4f} | "
                     f"Time: {meta.get('duration_ms', '?')}ms")
        if meta.get("session_id"):
            parts.append(f"Session: {meta['session_id']}")

    return "\n".join(parts)


def _handle_gemini_status(args: dict) -> str:
    from .cost import get_status_report
    today_only = args.get("today_only", True)
    return get_status_report(today_only=today_only)


def main() -> None:
    api_key = load_api_key()
    if not api_key:
        print(
            f"[{__package__}] WARNING: GEMINI_API_KEY not found at startup. "
            "Will check again on each tool call.",
            file=sys.stderr,
        )

    tools = _build_tools_list()
    server = McpServer(tools, _handle_tool)
    print(f"[{__package__}] MCP server started (stdio)", file=sys.stderr)
    server.run()
