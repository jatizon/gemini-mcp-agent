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


def truncate(s: str, limit: int = TOOL_OUTPUT_MAX_CHARS) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n... [TRUNCATED: {len(s)} chars, showing {limit}]"
