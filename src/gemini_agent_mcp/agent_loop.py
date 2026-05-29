"""Gemini autonomous agent loop with function calling."""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

from .config import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
)
from .cost import compute_cost, log_call
from .permissions import get_allowed_tools
from .session import load_session, save_session
from .tools import build_function_declarations, execute_tool

_TAG = "gemini-agent-mcp"

_DEFAULT_SYSTEM = (
    "You are a code analysis agent. You have access to tools for reading files, "
    "searching code, and listing files. Use them to thoroughly investigate the task, "
    "then provide a clear, concise analysis.\n\n"
    "Rules:\n"
    "- Use tools to gather evidence before drawing conclusions.\n"
    "- Be specific: cite file paths and line numbers.\n"
    "- Keep your final response concise and actionable.\n"
    "- When you have enough information, stop using tools and give your final answer."
)


def _extract_function_calls(candidate):
    if not candidate or not getattr(candidate, "content", None):
        return []
    parts = getattr(candidate.content, "parts", None) or []
    return [
        getattr(p, "function_call", None)
        for p in parts
        if getattr(getattr(p, "function_call", None), "name", None)
    ]


def _extract_text(candidate) -> str:
    if not candidate or not getattr(candidate, "content", None):
        return ""
    parts = getattr(candidate.content, "parts", None) or []
    return "\n".join(t for p in parts if (t := getattr(p, "text", None)))


def run_agent(
    api_key: str,
    task: str,
    project_root: str | None = None,
    files: list[str] | None = None,
    max_turns: int | None = None,
    allow_bash: bool = False,
    session_id: str | None = None,
    model: str | None = None,
    skill: str | None = None,
    permission_mode: str | None = None,
    custom_tools: list[str] | None = None,
    skills_dir: str | None = None,
) -> dict:
    """Run the Gemini agent loop. Returns {text, meta}."""
    from google import genai
    from google.genai import types

    model = model or DEFAULT_MODEL
    max_turns = max_turns or DEFAULT_MAX_TURNS
    root = Path(project_root or ".").resolve()

    if not root.exists() or not root.is_dir():
        raise ValueError(f"Invalid project_root: {root}")

    system_instruction = _DEFAULT_SYSTEM
    effective_permission = permission_mode or "read_only"
    effective_model = model

    if skill:
        from .skill_loader import load_skill
        skill_data = load_skill(skill, skills_dir)
        if skill_data.get("system_prompt"):
            system_instruction = skill_data["system_prompt"]
        if skill_data.get("permission_mode"):
            effective_permission = skill_data["permission_mode"]
        if skill_data.get("model"):
            effective_model = skill_data["model"]
        if skill_data.get("tools"):
            custom_tools = skill_data["tools"]

    allowed = get_allowed_tools(effective_permission, custom_tools)

    if allow_bash:
        allowed.add("bash_command")

    client = genai.Client(api_key=api_key)
    tools = build_function_declarations(types, allowed_tools=allowed, allow_bash=allow_bash)

    prompt_parts = [f"Task: {task}"]
    if files:
        prompt_parts.append(f"Focus on these files: {', '.join(files)}")
    prompt_parts.append(f"Project root: {root}")
    prompt = "\n".join(prompt_parts)

    session_id = session_id or str(uuid.uuid4())[:8]
    history = load_session(session_id)

    history.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    ))

    config = types.GenerateContentConfig(
        temperature=DEFAULT_TEMPERATURE,
        max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        tools=tools,
        system_instruction=system_instruction,
    )

    session_state: dict = {}
    stats = {
        "turns": 0, "tool_calls": 0, "in_tokens": 0, "out_tokens": 0,
        "cost_usd": 0.0, "duration_ms": 0, "tools_used": [],
        "files_read": [], "files_edited": [],
    }
    final_text = ""
    t_start = time.perf_counter()

    for turn in range(max_turns):
        stats["turns"] = turn + 1
        _log_progress(turn + 1, max_turns, skill=skill)

        try:
            resp = client.models.generate_content(
                model=effective_model, contents=history, config=config,
            )
        except Exception as exc:
            stats["error"] = str(exc)[:500]
            final_text = f"Gemini API error: {exc}"
            break

        if getattr(resp, "usage_metadata", None):
            u = resp.usage_metadata
            stats["in_tokens"] += getattr(u, "prompt_token_count", 0) or 0
            stats["out_tokens"] += getattr(u, "candidates_token_count", 0) or 0

        candidate = resp.candidates[0] if getattr(resp, "candidates", None) else None
        if not candidate:
            stats["error"] = "no candidates in response"
            final_text = "Gemini returned no response."
            break

        calls = _extract_function_calls(candidate)
        text = _extract_text(candidate)

        if not calls:
            final_text = text
            _log_progress(turn + 1, max_turns, done=True, text_len=len(text), skill=skill)
            break

        history.append(candidate.content)

        response_parts = []
        for fc in calls:
            name = fc.name
            try:
                fc_args = dict(fc.args) if fc.args else {}
            except (TypeError, ValueError):
                fc_args = {}

            _log_tool_call(turn + 1, name, fc_args)
            result = execute_tool(name, fc_args, root, allow_bash, session_state)

            stats["tool_calls"] += 1
            stats["tools_used"].append(name)
            if name in ("read_file", "read_file_range") and "path" in fc_args:
                stats["files_read"].append(fc_args["path"])
            elif name in ("edit_file", "multi_edit_file") and "path" in fc_args:
                stats["files_edited"].append(fc_args["path"])

            response_parts.append(types.Part.from_function_response(
                name=name, response={"result": result},
            ))

        history.append(types.Content(role="user", parts=response_parts))
    else:
        final_text = _extract_text(
            resp.candidates[0] if getattr(resp, "candidates", None) else None
        ) or f"Agent reached max turns ({max_turns}) without final answer."

    stats["duration_ms"] = int((time.perf_counter() - t_start) * 1000)
    stats["cost_usd"] = compute_cost(effective_model, stats["in_tokens"], stats["out_tokens"]) or 0.0

    save_session(session_id, history, types, extra={
        "skill": skill,
        "task": task,
        "files_read": list(set(stats["files_read"])),
        "files_edited": list(set(stats["files_edited"])),
        "tools_used": stats["tools_used"],
        "todos": session_state.get("todos", []),
        "final_summary": final_text[:2000],
    })

    log_call({
        "model": effective_model,
        "tag": _TAG,
        "mode": "agent-loop",
        "skill": skill,
        "turns": stats["turns"],
        "tool_calls_count": stats["tool_calls"],
        "in_tokens": stats["in_tokens"],
        "out_tokens": stats["out_tokens"],
        "cost_usd": stats["cost_usd"],
        "duration_ms": stats["duration_ms"],
        "output_chars": len(final_text),
        "session_id": session_id,
        "status": "error" if stats.get("error") else "ok",
        **({"error": stats["error"]} if stats.get("error") else {}),
    })

    return {
        "text": final_text,
        "meta": {
            "turns": stats["turns"],
            "tool_calls": stats["tool_calls"],
            "in_tokens": stats["in_tokens"],
            "out_tokens": stats["out_tokens"],
            "cost_usd": stats["cost_usd"],
            "duration_ms": stats["duration_ms"],
            "session_id": session_id,
            "skill": skill,
            "files_read": list(set(stats["files_read"])),
            "files_edited": list(set(stats["files_edited"])),
        },
    }


def _log_progress(turn: int, max_turns: int, done: bool = False, text_len: int = 0, skill: str | None = None) -> None:
    prefix = f"[gemini-agent:{skill}]" if skill else "[gemini-agent]"
    if done:
        print(f"{prefix} turn {turn}/{max_turns} | final answer ({text_len} chars)", file=sys.stderr)
    else:
        print(f"{prefix} turn {turn}/{max_turns} ...", file=sys.stderr)


def _log_tool_call(turn: int, name: str, args: dict) -> None:
    preview = json.dumps(args, ensure_ascii=False)[:120]
    print(f"[gemini-agent]   {name}({preview})", file=sys.stderr)
