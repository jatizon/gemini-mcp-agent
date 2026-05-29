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
                        "enum": ["read_only", "edit", "verify", "full"],
                        "description": "Permission level: read_only (default), edit (modify files), verify (edit + test/lint), full (all)",
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
                        "description": "Gemini model to use",
                        "default": "gemini-3.5-flash",
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
        {
            "name": "gemini_task",
            "description": (
                "Run multiple Gemini agents in parallel or sequential with different skills. "
                "Use for fan-out analysis: e.g. code-reviewer + security-auditor + architecture-mapper "
                "running simultaneously, with an optional synthesized summary."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "skill": {"type": "string"},
                                "task": {"type": "string"},
                                "files": {"type": "array", "items": {"type": "string"}},
                                "permission_mode": {"type": "string"},
                                "max_turns": {"type": "integer"},
                                "model": {"type": "string"},
                            },
                            "required": ["task"],
                        },
                    },
                    "project_root": {"type": "string", "description": "Absolute path to project root"},
                    "mode": {"type": "string", "enum": ["parallel", "sequential"], "description": "Execution mode (default: parallel)"},
                    "synthesize": {"type": "boolean", "description": "Produce a final synthesis (default: true)"},
                    "model": {"type": "string", "description": "Default model for all tasks"},
                    "parallel_limit": {"type": "integer", "description": "Max concurrent agents in parallel mode (default: 10)"},
                },
                "required": ["tasks", "project_root"],
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
    if name == "gemini_task":
        return _handle_gemini_task(args)
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
            f"Model: {meta.get('model', 'gemini-3.5-flash')} | "
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


def _handle_gemini_task(args: dict) -> str:
    from .agent_loop import run_multi_agent

    tasks = args.get("tasks")
    project_root = args.get("project_root", ".")
    if not tasks:
        raise ValueError("Missing required argument: tasks")

    api_key = load_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found.")

    result = run_multi_agent(
        api_key=api_key,
        tasks=tasks,
        project_root=project_root,
        mode=args.get("mode", "parallel"),
        synthesize=args.get("synthesize", True),
        model=args.get("model"),
        parallel_limit=args.get("parallel_limit", 10),
    )

    parts = []
    if result.get("summary"):
        parts.append(result["summary"])
    parts.append("\n---")
    meta = result.get("meta", {})
    parts.append(
        f"Mode: {meta.get('mode')} | Tasks: {meta.get('task_count')} | "
        f"OK: {meta.get('ok_count')} | Cost: ${meta.get('total_cost_usd', 0):.4f} | "
        f"Time: {meta.get('duration_ms')}ms"
    )
    for r in result.get("results", []):
        status_icon = "ok" if r.get("status") == "ok" else "FAIL"
        parts.append(f"  [{status_icon}] {r.get('skill', '?')}: {r.get('summary', '')[:200]}")
    return "\n".join(parts)


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
    print(f"[{__package__}] MCP server started (stdio) — 4 tools, skills enabled", file=sys.stderr)
    server.run()
