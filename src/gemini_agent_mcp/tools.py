"""Tool declarations for Gemini function calling and local executors."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import BASH_TIMEOUT_S, GLOB_MAX_MATCHES
from .safety import check_bash_forbidden, safe_resolve, truncate

TOOL_SPECS = {
    "read_file": {
        "description": "Read a text file from the project (path relative to project root).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root"},
            },
            "required": ["path"],
        },
    },
    "grep_search": {
        "description": (
            "Recursive grep with line numbers. Use to find where a pattern appears in the codebase."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex)"},
                "path": {"type": "string", "description": "Subpath to search (default: project root)"},
            },
            "required": ["pattern"],
        },
    },
    "glob_files": {
        "description": "List files matching a glob pattern (e.g. '**/*.py', 'src/**/*.ts').",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern"},
            },
            "required": ["pattern"],
        },
    },
    "bash_command": {
        "description": (
            "Execute a read-only bash command in the project root (timeout 30s). "
            "Disabled by default; requires allow_bash=true in the gemini_agent call."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["cmd"],
        },
    },
}


def build_function_declarations(types_mod, allow_bash: bool = False):
    """Build google.genai Tool[] from TOOL_SPECS."""
    decls = []
    for name, spec in TOOL_SPECS.items():
        if name == "bash_command" and not allow_bash:
            continue
        decls.append(types_mod.FunctionDeclaration(
            name=name,
            description=spec["description"],
            parameters=spec["parameters"],
        ))
    if not decls:
        return None
    return [types_mod.Tool(function_declarations=decls)]


def execute_tool(name: str, args: dict, root: Path, allow_bash: bool) -> str:
    """Execute a tool call and return the result string."""
    executor = _EXECUTORS.get(name)
    if executor is None:
        return f"ERROR: unknown tool '{name}'"
    try:
        return executor(args, root, allow_bash)
    except Exception as exc:
        return f"ERROR: tool '{name}' raised: {exc}"


def _exec_read_file(args: dict, root: Path, _allow_bash: bool) -> str:
    path = args.get("path", "")
    if not path:
        return "ERROR: missing 'path' argument"
    target = safe_resolve(root, path)
    if target is None:
        return f"ERROR: path '{path}' is outside project root"
    if not target.exists():
        return f"ERROR: file not found: {path}"
    if target.is_dir():
        return f"ERROR: '{path}' is a directory, use glob_files"
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERROR: '{path}' is not UTF-8 (likely binary)"
    return truncate(text)


def _exec_grep_search(args: dict, root: Path, _allow_bash: bool) -> str:
    pattern = args.get("pattern", "")
    if not pattern:
        return "ERROR: missing 'pattern' argument"
    path_arg = args.get("path", ".")
    target = safe_resolve(root, path_arg)
    if target is None:
        return f"ERROR: path '{path_arg}' is outside project root"
    if not target.exists():
        return f"ERROR: path not found: {path_arg}"
    try:
        res = subprocess.run(
            ["grep", "-r", "-n", "-I", "--", pattern, str(target)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: grep timeout (30s)"
    out = res.stdout
    if res.returncode != 0 and not out:
        return f"(no matches for pattern='{pattern}' in path='{path_arg}')"
    return truncate(out)


def _exec_glob_files(args: dict, root: Path, _allow_bash: bool) -> str:
    pattern = args.get("pattern", "")
    if not pattern:
        return "ERROR: missing 'pattern' argument"
    try:
        matches = sorted(
            str(p.relative_to(root))
            for p in root.glob(pattern)
            if not p.is_dir()
        )[:GLOB_MAX_MATCHES]
    except OSError as exc:
        return f"ERROR: glob failed: {exc}"
    if not matches:
        return f"(no matches for pattern='{pattern}')"
    return "\n".join(matches)


def _exec_bash_command(args: dict, root: Path, allow_bash: bool) -> str:
    if not allow_bash:
        return "ERROR: bash is disabled. Set allow_bash=true in the gemini_agent call."
    cmd = args.get("cmd", "")
    if not cmd:
        return "ERROR: missing 'cmd' argument"
    forbidden = check_bash_forbidden(cmd)
    if forbidden:
        return f"ERROR: forbidden pattern in command: '{forbidden}'"
    try:
        res = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=BASH_TIMEOUT_S, cwd=str(root),
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: bash timeout ({BASH_TIMEOUT_S}s)"
    out = res.stdout
    if res.stderr:
        out = (out or "") + f"\n[stderr]\n{res.stderr[:5000]}"
    if res.returncode != 0:
        out = (out or "") + f"\n[exit code: {res.returncode}]"
    return truncate(out) if out else "(no output)"


_EXECUTORS = {
    "read_file": _exec_read_file,
    "grep_search": _exec_grep_search,
    "glob_files": _exec_glob_files,
    "bash_command": _exec_bash_command,
}
