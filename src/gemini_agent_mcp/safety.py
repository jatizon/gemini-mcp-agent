"""Path traversal prevention, bash blocklist, output truncation."""

from __future__ import annotations

from pathlib import Path

from .config import TOOL_OUTPUT_MAX_CHARS

BASH_FORBIDDEN = (
    "rm ", "rm\t", "rm\n", "rmdir", "mv ", " > /", ">> /",
    "curl", "wget", "ssh", "scp", "sudo", "chown", "chmod 777",
    "dd ", "mkfs", "fdisk", ":(){:|:&};:", "$(curl", "`curl",
    "python -c", "node -e", "perl -e", "ruby -e",
)

BASH_ALLOWED_PREFIXES = (
    "ls", "cat", "head", "tail", "wc", "find", "file", "stat",
    "du", "df", "echo", "grep", "rg", "sort", "uniq", "diff",
    "git log", "git diff", "git status", "git show", "git blame",
    "git branch", "git rev-parse", "git ls-files",
    "tree", "pwd", "env", "which", "type", "basename", "dirname",
    "sha256sum", "md5sum", "xxd",
)


def safe_resolve(root: Path, path_arg: str) -> Path | None:
    """Resolve path_arg inside root. Returns None if path traversal detected."""
    try:
        if Path(path_arg).is_absolute():
            target = Path(path_arg).resolve()
        else:
            target = (root / path_arg).resolve()
    except (OSError, ValueError):
        return None
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def check_bash_forbidden(cmd: str) -> str | None:
    """Returns the forbidden pattern if found, else None."""
    for pattern in BASH_FORBIDDEN:
        if pattern in cmd:
            return pattern
    return None


def check_bash_allowed(cmd: str) -> bool:
    """Returns True if cmd starts with an allowed prefix."""
    stripped = cmd.strip()
    for prefix in BASH_ALLOWED_PREFIXES:
        if stripped == prefix or stripped.startswith(prefix + " ") or stripped.startswith(prefix + "\t"):
            return True
    return False


def truncate(s: str, limit: int = TOOL_OUTPUT_MAX_CHARS) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n... [TRUNCATED: {len(s)} chars, showing {limit}]"
