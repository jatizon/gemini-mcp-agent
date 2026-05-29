"""Tool declarations for Gemini function calling and local executors."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import BASH_MODE, BASH_TIMEOUT_S, GLOB_MAX_MATCHES
from .safety import BASH_ALLOWED_PREFIXES, check_bash_allowed, check_bash_forbidden, check_exec_allowed, safe_resolve, truncate

_RG_PATH = shutil.which("rg")

# --- Tool categories for permission filtering ---
READ_TOOLS = {"read_file", "read_file_range", "list_directory", "glob_files", "grep_search", "project_map", "analyze_diff"}
EDIT_TOOLS = {"edit_file", "multi_edit_file"}
VERIFY_TOOLS = {"run_tests", "run_lint", "run_typecheck"}
EXEC_TOOLS = {"bash_command"} | VERIFY_TOOLS
TODO_TOOLS = {"todo_write", "todo_read"}

TOOL_SPECS = {
    "read_file": {
        "description": "Read a text file with line numbers (path relative to project root).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root"},
            },
            "required": ["path"],
        },
    },
    "read_file_range": {
        "description": "Read specific line range from a file. Use when you only need part of a large file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root"},
                "start_line": {"type": "integer", "description": "First line to read (1-based)"},
                "end_line": {"type": "integer", "description": "Last line to read (inclusive)"},
            },
            "required": ["path", "start_line", "end_line"],
        },
    },
    "list_directory": {
        "description": "List files and directories at a path with sizes. Use to explore project structure.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to project root (default: '.')"},
                "depth": {"type": "integer", "description": "Max depth to recurse (default: 1)"},
            },
        },
    },
    "grep_search": {
        "description": "Recursive grep with line numbers and context. Use to find where a pattern appears.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex)"},
                "path": {"type": "string", "description": "Subpath to search (default: project root)"},
                "context": {"type": "integer", "description": "Lines of context around matches (default: 0)"},
            },
            "required": ["pattern"],
        },
    },
    "glob_files": {
        "description": "List files matching a glob pattern. Respects .gitignore when ripgrep is available.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')"},
                "limit": {"type": "integer", "description": "Max results (default: 500)"},
                "include_hidden": {"type": "boolean", "description": "Include hidden/ignored files (default: false)"},
            },
            "required": ["pattern"],
        },
    },
    "edit_file": {
        "description": "Edit a file by replacing an exact string match. Errors if 0 or 2+ matches found (unless replace_all=true).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root"},
                "old_string": {"type": "string", "description": "Exact string to find and replace"},
                "new_string": {"type": "string", "description": "Replacement string"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences (default: false)"},
                "dry_run": {"type": "boolean", "description": "Preview diff without modifying file (default: false)"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    "multi_edit_file": {
        "description": "Apply multiple edits to a file atomically. Each edit is {old_string, new_string}.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_string": {"type": "string"},
                            "new_string": {"type": "string"},
                        },
                        "required": ["old_string", "new_string"],
                    },
                    "description": "List of {old_string, new_string} edits to apply in order",
                },
                "dry_run": {"type": "boolean", "description": "Preview diff without modifying file (default: false)"},
            },
            "required": ["path", "edits"],
        },
    },
    "analyze_diff": {
        "description": "Show git diff against a base ref. Use to understand what changed.",
        "parameters": {
            "type": "object",
            "properties": {
                "base_ref": {"type": "string", "description": "Git ref to diff against (default: 'main')"},
            },
        },
    },
    "project_map": {
        "description": "Detect project type, language, test/lint commands, and directory structure.",
        "parameters": {
            "type": "object",
            "properties": {
                "depth": {"type": "integer", "description": "Directory listing depth (default: 2)"},
            },
        },
    },
    "run_tests": {
        "description": "Run the project's test suite. Auto-detects test command or uses provided one.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Override test command (auto-detected if omitted)"},
            },
        },
    },
    "run_lint": {
        "description": "Run the project's linter. Auto-detects lint command or uses provided one.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Override lint command (auto-detected if omitted)"},
            },
        },
    },
    "run_typecheck": {
        "description": "Run the project's type checker. Auto-detects command or uses provided one.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Override typecheck command (auto-detected if omitted)"},
            },
        },
    },
    "bash_command": {
        "description": (
            "Execute a bash command in the project root (timeout 30s). "
            "Disabled by default; requires allow_bash=true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["cmd"],
        },
    },
    "todo_write": {
        "description": "Create or update a task list for tracking progress on complex analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                        },
                        "required": ["id", "content", "status"],
                    },
                },
            },
            "required": ["items"],
        },
    },
    "todo_read": {
        "description": "Read the current task list.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def build_function_declarations(types_mod, allowed_tools: set[str] | None = None, allow_bash: bool = False):
    """Build google.genai Tool[] from TOOL_SPECS, filtered by allowed_tools."""
    decls = []
    for name, spec in TOOL_SPECS.items():
        if allowed_tools is not None and name not in allowed_tools:
            continue
        if name == "bash_command" and not allow_bash and (allowed_tools is None or name not in allowed_tools):
            continue
        decls.append(types_mod.FunctionDeclaration(
            name=name,
            description=spec["description"],
            parameters=spec["parameters"],
        ))
    if not decls:
        return None
    return [types_mod.Tool(function_declarations=decls)]


def execute_tool(name: str, args: dict, root: Path, allow_bash: bool, session_state: dict | None = None) -> str:
    """Execute a tool call and return the result string."""
    executor = _EXECUTORS.get(name)
    if executor is None:
        return f"ERROR: unknown tool '{name}'"
    try:
        if name in ("todo_write", "todo_read"):
            return executor(args, root, allow_bash, session_state or {})
        return executor(args, root, allow_bash)
    except Exception as exc:
        return f"ERROR: tool '{name}' raised: {exc}"


# --- Read tools ---

def _exec_read_file(args: dict, root: Path, _ab: bool) -> str:
    path = args.get("path", "")
    if not path:
        return "ERROR: missing 'path' argument"
    target = safe_resolve(root, path)
    if target is None:
        return f"ERROR: path '{path}' is outside project root"
    if not target.exists():
        return f"ERROR: file not found: {path}"
    if target.is_dir():
        return f"ERROR: '{path}' is a directory, use list_directory"
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"ERROR: '{path}' is not UTF-8 (likely binary)"
    numbered = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
    return truncate("\n".join(numbered))


def _exec_read_file_range(args: dict, root: Path, _ab: bool) -> str:
    path = args.get("path", "")
    start = args.get("start_line", 1)
    end = args.get("end_line", start + 50)
    if not path:
        return "ERROR: missing 'path' argument"
    target = safe_resolve(root, path)
    if target is None:
        return f"ERROR: path '{path}' is outside project root"
    if not target.exists():
        return f"ERROR: file not found: {path}"
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"ERROR: '{path}' is not UTF-8 (likely binary)"
    start = max(1, start)
    end = min(len(lines), end)
    numbered = [f"{i:4d} | {lines[i-1]}" for i in range(start, end + 1)]
    header = f"[{path} lines {start}-{end} of {len(lines)}]"
    return header + "\n" + "\n".join(numbered)


def _exec_list_directory(args: dict, root: Path, _ab: bool) -> str:
    path_arg = args.get("path", ".")
    depth = args.get("depth", 1)
    target = safe_resolve(root, path_arg)
    if target is None:
        return f"ERROR: path '{path_arg}' is outside project root"
    if not target.exists():
        return f"ERROR: path not found: {path_arg}"
    if not target.is_dir():
        return f"ERROR: '{path_arg}' is not a directory"
    lines = []
    _walk_dir(target, root, lines, depth, 0)
    return "\n".join(lines) if lines else "(empty directory)"


def _walk_dir(path: Path, root: Path, lines: list, max_depth: int, current: int) -> None:
    if current > max_depth:
        return
    indent = "  " * current
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        lines.append(f"{indent}[permission denied]")
        return
    for entry in entries[:100]:
        if entry.name.startswith(".") and current == 0:
            continue
        rel = str(entry.relative_to(root))
        if entry.is_dir():
            lines.append(f"{indent}{rel}/")
            _walk_dir(entry, root, lines, max_depth, current + 1)
        else:
            size = entry.stat().st_size
            lines.append(f"{indent}{rel}  ({_human_size(size)})")


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# --- Search tools ---

def _exec_grep_search(args: dict, root: Path, _ab: bool) -> str:
    pattern = args.get("pattern", "")
    if not pattern:
        return "ERROR: missing 'pattern' argument"
    path_arg = args.get("path", ".")
    context = args.get("context", 0)
    target = safe_resolve(root, path_arg)
    if target is None:
        return f"ERROR: path '{path_arg}' is outside project root"
    if not target.exists():
        return f"ERROR: path not found: {path_arg}"
    if _RG_PATH:
        cmd = [_RG_PATH, "-n", "--no-heading"]
        if context:
            cmd += [f"-C{context}"]
        cmd += ["--", pattern, str(target)]
    else:
        cmd = ["grep", "-r", "-n", "-I"]
        if context:
            cmd += [f"-C{context}"]
        cmd += ["--", pattern, str(target)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "ERROR: grep timeout (30s)"
    out = res.stdout
    if res.returncode != 0 and not out:
        return f"(no matches for pattern='{pattern}' in path='{path_arg}')"
    return truncate(out)


_GLOB_EXCLUDES = {".git", "node_modules", ".venv", "__pycache__", "dist", "build",
                   ".next", ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
                   ".eggs", "*.egg-info", ".cache", "coverage", ".coverage"}


def _exec_glob_files(args: dict, root: Path, _ab: bool) -> str:
    pattern = args.get("pattern", "")
    if not pattern:
        return "ERROR: missing 'pattern' argument"
    limit = args.get("limit", GLOB_MAX_MATCHES)
    include_hidden = args.get("include_hidden", False)
    if _RG_PATH and not include_hidden:
        try:
            cmd = [_RG_PATH, "--files", "-g", pattern, str(root)]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.stdout.strip():
                matches = sorted(res.stdout.strip().splitlines())[:limit]
                rel = []
                for m in matches:
                    try:
                        rel.append(str(Path(m).relative_to(root)))
                    except ValueError:
                        rel.append(m)
                return "\n".join(rel) if rel else f"(no matches for pattern='{pattern}')"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    try:
        all_matches = []
        for p in root.glob(pattern):
            if p.is_dir():
                continue
            if not include_hidden:
                parts = p.relative_to(root).parts
                if any(part in _GLOB_EXCLUDES or part.startswith(".") for part in parts):
                    continue
            all_matches.append(str(p.relative_to(root)))
        matches = sorted(all_matches)[:limit]
    except OSError as exc:
        return f"ERROR: glob failed: {exc}"
    if not matches:
        return f"(no matches for pattern='{pattern}')"
    return "\n".join(matches)


# --- Edit tools ---

def _exec_edit_file(args: dict, root: Path, _ab: bool) -> str:
    import difflib
    path = args.get("path", "")
    old = args.get("old_string", "")
    new = args.get("new_string", "")
    replace_all = args.get("replace_all", False)
    dry_run = args.get("dry_run", False)
    if not path:
        return "ERROR: missing 'path' argument"
    if not old:
        return "ERROR: missing 'old_string' argument"
    target = safe_resolve(root, path)
    if target is None:
        return f"ERROR: path '{path}' is outside project root"
    if not target.exists():
        return f"ERROR: file not found: {path}"
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERROR: '{path}' is not UTF-8"
    count = content.count(old)
    if count == 0:
        return f"ERROR: old_string not found in {path}"
    if count > 1 and not replace_all:
        return f"ERROR: old_string found {count} times in {path}. Use replace_all=true to replace all."
    new_content = content.replace(old, new) if replace_all else content.replace(old, new, 1)
    if dry_run:
        diff = "".join(difflib.unified_diff(
            content.splitlines(keepends=True), new_content.splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}",
        ))
        return f"[DRY RUN] would_edit: true\n{diff}" if diff else "[DRY RUN] no changes"
    target.write_text(new_content, encoding="utf-8")
    return f"OK: replaced {count if replace_all else 1} occurrence(s) in {path}"


def _exec_multi_edit_file(args: dict, root: Path, _ab: bool) -> str:
    import difflib
    path = args.get("path", "")
    edits = args.get("edits", [])
    dry_run = args.get("dry_run", False)
    if not path:
        return "ERROR: missing 'path' argument"
    if not edits:
        return "ERROR: missing 'edits' argument"
    target = safe_resolve(root, path)
    if target is None:
        return f"ERROR: path '{path}' is outside project root"
    if not target.exists():
        return f"ERROR: file not found: {path}"
    try:
        original = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERROR: '{path}' is not UTF-8"
    content = original
    applied = 0
    for i, edit in enumerate(edits):
        old = edit.get("old_string", "")
        new = edit.get("new_string", "")
        if not old:
            return f"ERROR: edit {i} missing old_string"
        count = content.count(old)
        if count == 0:
            return f"ERROR: edit {i} old_string not found in {path} (after {applied} edits applied)"
        if count > 1:
            return f"ERROR: edit {i} old_string found {count} times in {path}"
        content = content.replace(old, new, 1)
        applied += 1
    if dry_run:
        diff = "".join(difflib.unified_diff(
            original.splitlines(keepends=True), content.splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}",
        ))
        return f"[DRY RUN] would_edit: true, {applied} edits\n{diff}" if diff else "[DRY RUN] no changes"
    target.write_text(content, encoding="utf-8")
    return f"OK: applied {applied} edits to {path}"


# --- Analysis tools ---

def _exec_analyze_diff(args: dict, root: Path, _ab: bool) -> str:
    base = args.get("base_ref", "main")
    try:
        stat = subprocess.run(
            ["git", "diff", "--stat", base],
            capture_output=True, text=True, timeout=30, cwd=str(root),
        )
        diff = subprocess.run(
            ["git", "diff", base],
            capture_output=True, text=True, timeout=30, cwd=str(root),
        )
    except subprocess.TimeoutExpired:
        return "ERROR: git diff timeout (30s)"
    except FileNotFoundError:
        return "ERROR: git not found"
    out = f"=== git diff --stat {base} ===\n{stat.stdout}\n=== git diff {base} ===\n{diff.stdout}"
    return truncate(out)


def _exec_project_map(args: dict, root: Path, _ab: bool) -> str:
    from .project_detect import detect_project
    depth = args.get("depth", 2)
    info = detect_project(root)
    lines = [json.dumps(info, indent=2, ensure_ascii=False)]
    dir_lines: list[str] = []
    _walk_dir(root, root, dir_lines, depth, 0)
    lines.append("\n=== Directory tree ===")
    lines.extend(dir_lines[:200])
    return "\n".join(lines)


# --- Execution tools ---

def _exec_run_cmd(args: dict, root: Path, _ab: bool, cmd_key: str) -> str:
    import shlex
    from .project_detect import detect_project
    cmd = args.get("command")
    user_provided = cmd is not None
    if not cmd:
        info = detect_project(root)
        cmd = info.get(cmd_key)
        if not cmd:
            return f"ERROR: could not auto-detect {cmd_key}. Pass 'command' explicitly."
    if user_provided and not check_exec_allowed(cmd):
        return f"ERROR: command not in exec allowlist: '{cmd}'. Only test/lint/typecheck commands are allowed."
    timeout = 120 if cmd_key == "test_cmd" else 60
    try:
        res = subprocess.run(
            shlex.split(cmd), shell=False, capture_output=True, text=True,
            timeout=timeout, cwd=str(root),
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: command timeout ({timeout}s)"
    except (FileNotFoundError, ValueError) as exc:
        return f"ERROR: failed to run command: {exc}"
    out = res.stdout
    if res.stderr:
        out = (out or "") + f"\n[stderr]\n{res.stderr[:10000]}"
    if res.returncode != 0:
        out = (out or "") + f"\n[exit code: {res.returncode}]"
    return truncate(out) if out else "(no output)"


def _exec_run_tests(args: dict, root: Path, ab: bool) -> str:
    return _exec_run_cmd(args, root, ab, "test_cmd")


def _exec_run_lint(args: dict, root: Path, ab: bool) -> str:
    return _exec_run_cmd(args, root, ab, "lint_cmd")


def _exec_run_typecheck(args: dict, root: Path, ab: bool) -> str:
    return _exec_run_cmd(args, root, ab, "typecheck_cmd")


# --- Bash ---

def _exec_bash_command(args: dict, root: Path, allow_bash: bool) -> str:
    if not allow_bash:
        return "ERROR: bash is disabled. Set allow_bash=true in the gemini_agent call."
    cmd = args.get("cmd", "")
    if not cmd:
        return "ERROR: missing 'cmd' argument"
    if BASH_MODE == "allowlist":
        if not check_bash_allowed(cmd):
            return f"ERROR: command not in allowlist. Allowed prefixes: {', '.join(BASH_ALLOWED_PREFIXES[:10])}..."
    else:
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


# --- Todo tools ---

def _exec_todo_write(args: dict, _root: Path, _ab: bool, state: dict) -> str:
    items = args.get("items", [])
    state["todos"] = items
    return f"OK: {len(items)} items saved"


def _exec_todo_read(args: dict, _root: Path, _ab: bool, state: dict) -> str:
    todos = state.get("todos", [])
    if not todos:
        return "(no todos)"
    lines = []
    for t in todos:
        marker = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}.get(t.get("status", ""), "[ ]")
        lines.append(f"{marker} {t.get('id', '?')}: {t.get('content', '')}")
    return "\n".join(lines)


_EXECUTORS = {
    "read_file": _exec_read_file,
    "read_file_range": _exec_read_file_range,
    "list_directory": _exec_list_directory,
    "grep_search": _exec_grep_search,
    "glob_files": _exec_glob_files,
    "edit_file": _exec_edit_file,
    "multi_edit_file": _exec_multi_edit_file,
    "analyze_diff": _exec_analyze_diff,
    "project_map": _exec_project_map,
    "run_tests": _exec_run_tests,
    "run_lint": _exec_run_lint,
    "run_typecheck": _exec_run_typecheck,
    "bash_command": _exec_bash_command,
    "todo_write": _exec_todo_write,
    "todo_read": _exec_todo_read,
}
