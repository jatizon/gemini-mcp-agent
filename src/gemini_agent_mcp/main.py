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
                "Gemini reads files, greps, globs, edits, and optionally runs commands "
                "to analyze or modify a codebase. Use skills for specialized behavior "
                "(code-reviewer, test-writer, refactorer, etc.). "
                "Use for: architecture analysis, code review, log triage, "
                "dependency mapping, pattern detection, test writing, refactoring."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The task for Gemini to perform",
                    },
                    "skill": {
                        "type": "string",
                        "description": (
                            "Skill profile to use (e.g. 'code-reviewer', 'test-writer', 'refactorer'). "
                            "Sets system prompt, tools, and permissions. Use gemini_skills to list available skills."
                        ),
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
                    "permission_mode": {
                        "type": "string",
                        "enum": ["read_only", "edit", "full"],
                        "description": "Permission level: read_only (default), edit (can modify files), full (edit + bash/tests)",
                    },
                    "allow_bash": {
                        "type": "boolean",
                        "description": "Enable bash tool for Gemini (default: false)",
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
            "description": "Show Gemini agent cost and usage stats from the cost log.",
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
        {
            "name": "gemini_skills",
            "description": "List available Gemini agent skill profiles with their descriptions and permission modes.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "skills_dir": {
                        "type": "string",
                        "description": "Optional custom skills directory path",
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
    if name == "gemini_skills":
        return _handle_gemini_skills(args)
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
        skill=args.get("skill"),
        permission_mode=args.get("permission_mode"),
    )

    parts = [result["text"]]
    meta = result.get("meta", {})
    if meta:
        parts.append("\n---")
        info = (
            f"Turns: {meta.get('turns', '?')} | "
            f"Tools: {meta.get('tool_calls', '?')} | "
            f"In: {meta.get('in_tokens', '?')} | "
            f"Out: {meta.get('out_tokens', '?')} | "
            f"Cost: ${meta.get('cost_usd', 0):.4f} | "
            f"Time: {meta.get('duration_ms', '?')}ms"
        )
        if meta.get("skill"):
            info += f" | Skill: {meta['skill']}"
        parts.append(info)
        if meta.get("session_id"):
            parts.append(f"Session: {meta['session_id']}")
        if meta.get("files_read"):
            parts.append(f"Files read: {', '.join(meta['files_read'][:10])}")
        if meta.get("files_edited"):
            parts.append(f"Files edited: {', '.join(meta['files_edited'][:10])}")

    return "\n".join(parts)


def _handle_gemini_status(args: dict) -> str:
    from .cost import get_status_report
    return get_status_report(today_only=args.get("today_only", True))


def _handle_gemini_skills(args: dict) -> str:
    from .skill_loader import list_skills
    skills = list_skills(args.get("skills_dir"))
    if not skills:
        return "No skills found. Add .md files to ~/.gemini-agent-mcp/skills/ or the built-in skills/ directory."
    lines = []
    for s in skills:
        mode = s.get("permission_mode", "read_only")
        lines.append(f"  {s['name']} ({mode}): {s.get('description', '')}")
    return "Available skills:\n" + "\n".join(lines)


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
    print(f"[{__package__}] MCP server started (stdio) — 3 tools, skills enabled", file=sys.stderr)
    server.run()
