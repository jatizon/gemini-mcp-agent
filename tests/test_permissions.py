"""Tests for permission presets and get_allowed_tools."""

from __future__ import annotations

from gemini_agent_mcp.permissions import PERMISSION_PRESETS, get_allowed_tools


# --- read_only preset ---


def test_read_only_has_read_tools() -> None:
    tools = get_allowed_tools("read_only")
    assert "read_file" in tools
    assert "grep_search" in tools


def test_read_only_excludes_edit() -> None:
    tools = get_allowed_tools("read_only")
    assert "edit_file" not in tools


def test_read_only_excludes_bash() -> None:
    tools = get_allowed_tools("read_only")
    assert "bash_command" not in tools


# --- edit preset ---


def test_edit_includes_edit_tools() -> None:
    tools = get_allowed_tools("edit")
    assert "edit_file" in tools
    assert "multi_edit_file" in tools


def test_edit_excludes_run_tests() -> None:
    tools = get_allowed_tools("edit")
    assert "run_tests" not in tools


def test_edit_excludes_bash() -> None:
    tools = get_allowed_tools("edit")
    assert "bash_command" not in tools


# --- verify preset ---


def test_verify_includes_run_tests() -> None:
    tools = get_allowed_tools("verify")
    assert "run_tests" in tools
    assert "run_lint" in tools
    assert "run_typecheck" in tools


def test_verify_includes_edit() -> None:
    tools = get_allowed_tools("verify")
    assert "edit_file" in tools


def test_verify_excludes_bash() -> None:
    tools = get_allowed_tools("verify")
    assert "bash_command" not in tools


# --- full preset ---


def test_full_includes_bash() -> None:
    tools = get_allowed_tools("full")
    assert "bash_command" in tools


# --- custom_tools override ---


def test_custom_tools_overrides() -> None:
    tools = get_allowed_tools(mode="read_only", custom_tools=["read_file"])
    assert tools == {"read_file"}
