"""Tests for tool executors (execute_tool)."""

from __future__ import annotations

from pathlib import Path

from gemini_agent_mcp.tools import execute_tool


def test_read_file_returns_content(tmp_project: Path) -> None:
    result = execute_tool("read_file", {"path": "src/app.py"}, tmp_project, allow_bash=False)
    assert "import os" in result


def test_read_file_blocks_traversal(tmp_project: Path) -> None:
    result = execute_tool("read_file", {"path": "../../etc/passwd"}, tmp_project, allow_bash=False)
    assert "ERROR" in result


def test_read_file_rejects_binary(tmp_project: Path) -> None:
    result = execute_tool("read_file", {"path": "binary.bin"}, tmp_project, allow_bash=False)
    assert "ERROR" in result
    assert "UTF-8" in result


def test_grep_finds_pattern(tmp_project: Path) -> None:
    result = execute_tool("grep_search", {"pattern": "def main", "path": "src/"}, tmp_project, allow_bash=False)
    assert "app.py" in result


def test_grep_no_matches(tmp_project: Path) -> None:
    result = execute_tool("grep_search", {"pattern": "nonexistent_xyz"}, tmp_project, allow_bash=False)
    assert "no matches" in result


def test_glob_matches_py_files(tmp_project: Path) -> None:
    result = execute_tool("glob_files", {"pattern": "**/*.py"}, tmp_project, allow_bash=False)
    assert "app.py" in result
    assert "utils.py" in result


def test_bash_disabled_by_default(tmp_project: Path) -> None:
    result = execute_tool("bash_command", {"cmd": "ls"}, tmp_project, allow_bash=False)
    assert "ERROR" in result
    assert "disabled" in result


def test_bash_blocks_forbidden(tmp_project: Path) -> None:
    result = execute_tool("bash_command", {"cmd": "rm -rf /"}, tmp_project, allow_bash=True)
    assert "ERROR" in result
    assert "forbidden" in result
