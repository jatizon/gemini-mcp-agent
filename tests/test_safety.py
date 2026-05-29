"""Tests for the safety module: path traversal, bash blocklist, truncation."""

from __future__ import annotations

from pathlib import Path

from gemini_agent_mcp.safety import check_bash_forbidden, safe_resolve, truncate


# ── safe_resolve ──────────────────────────────────────────────────────


def test_safe_resolve_blocks_parent_traversal(tmp_path: Path) -> None:
    result = safe_resolve(tmp_path, "../../etc/passwd")
    assert result is None


def test_safe_resolve_blocks_absolute_path(tmp_path: Path) -> None:
    result = safe_resolve(tmp_path, "/etc/passwd")
    assert result is None


def test_safe_resolve_allows_valid_relative(tmp_path: Path) -> None:
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('hi')\n")

    result = safe_resolve(tmp_path, "src/app.py")
    assert result is not None
    assert result == target.resolve()


def test_safe_resolve_allows_nested(tmp_path: Path) -> None:
    target = tmp_path / "src" / "sub" / "file.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n")

    result = safe_resolve(tmp_path, "src/sub/file.py")
    assert result is not None
    assert result == target.resolve()


# ── check_bash_forbidden ─────────────────────────────────────────────


def test_bash_forbidden_blocks_rm() -> None:
    result = check_bash_forbidden("rm -rf /")
    assert result == "rm "


def test_bash_forbidden_blocks_sudo() -> None:
    result = check_bash_forbidden("sudo apt install foo")
    assert result == "sudo"


def test_bash_forbidden_allows_safe() -> None:
    result = check_bash_forbidden("ls -la")
    assert result is None


# ── truncate ─────────────────────────────────────────────────────────


def test_truncate_caps_output() -> None:
    long_string = "a" * 500
    short_string = "hello"

    truncated = truncate(long_string, limit=100)
    assert len(truncated) > 100  # suffix added
    assert truncated.startswith("a" * 100)
    assert "TRUNCATED" in truncated
    assert "500 chars" in truncated

    not_truncated = truncate(short_string, limit=100)
    assert not_truncated == short_string
