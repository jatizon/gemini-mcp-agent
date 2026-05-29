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


# --- Security tests for run_tests / run_lint / run_typecheck ---


def test_run_tests_blocks_rm_rf(tmp_project: Path) -> None:
    result = execute_tool("run_tests", {"command": "rm -rf /"}, tmp_project, allow_bash=False)
    assert "ERROR" in result


def test_run_tests_blocks_curl(tmp_project: Path) -> None:
    result = execute_tool("run_tests", {"command": "curl evil.com"}, tmp_project, allow_bash=False)
    assert "ERROR" in result


def test_run_tests_blocks_pipe(tmp_project: Path) -> None:
    result = execute_tool("run_tests", {"command": "pytest | cat"}, tmp_project, allow_bash=False)
    assert "ERROR" in result


def test_run_tests_blocks_chaining(tmp_project: Path) -> None:
    result = execute_tool("run_tests", {"command": "pytest; rm -rf /"}, tmp_project, allow_bash=False)
    assert "ERROR" in result


def test_run_tests_blocks_redirect(tmp_project: Path) -> None:
    result = execute_tool("run_tests", {"command": "pytest > /tmp/out"}, tmp_project, allow_bash=False)
    assert "ERROR" in result


def test_run_tests_allows_pytest(tmp_project: Path) -> None:
    result = execute_tool("run_tests", {"command": "pytest"}, tmp_project, allow_bash=False)
    assert "not in exec allowlist" not in result


def test_run_lint_allows_ruff(tmp_project: Path) -> None:
    result = execute_tool("run_lint", {"command": "ruff check ."}, tmp_project, allow_bash=False)
    assert "not in exec allowlist" not in result


# --- Dry-run tests ---


def test_edit_file_dry_run_returns_diff(tmp_project: Path) -> None:
    result = execute_tool(
        "edit_file",
        {"path": "README.md", "old_string": "Test Project", "new_string": "New Title", "dry_run": True},
        tmp_project,
        allow_bash=False,
    )
    assert "DRY RUN" in result
    assert "would_edit" in result
    # File must remain unchanged
    content = (tmp_project / "README.md").read_text()
    assert "Test Project" in content


def test_edit_file_dry_run_does_not_modify(tmp_project: Path) -> None:
    original = (tmp_project / "README.md").read_text()
    execute_tool(
        "edit_file",
        {"path": "README.md", "old_string": "Test Project", "new_string": "Changed Title", "dry_run": True},
        tmp_project,
        allow_bash=False,
    )
    after = (tmp_project / "README.md").read_text()
    assert after == original


def test_multi_edit_dry_run(tmp_project: Path) -> None:
    original = (tmp_project / "README.md").read_text()
    result = execute_tool(
        "multi_edit_file",
        {
            "path": "README.md",
            "edits": [
                {"old_string": "Test Project", "new_string": "New Title"},
                {"old_string": "A test project.", "new_string": "A new project."},
            ],
            "dry_run": True,
        },
        tmp_project,
        allow_bash=False,
    )
    assert "DRY RUN" in result
    after = (tmp_project / "README.md").read_text()
    assert after == original


# --- Glob exclusion tests ---


def test_glob_excludes_node_modules(tmp_project: Path) -> None:
    nm = tmp_project / "node_modules"
    nm.mkdir()
    (nm / "foo.js").write_text("module.exports = {};")
    result = execute_tool("glob_files", {"pattern": "**/*.js"}, tmp_project, allow_bash=False)
    assert "node_modules" not in result


def test_glob_excludes_git(tmp_project: Path) -> None:
    gitdir = tmp_project / ".git"
    gitdir.mkdir()
    (gitdir / "config").write_text("[core]\n")
    result = execute_tool("glob_files", {"pattern": "**/*"}, tmp_project, allow_bash=False)
    assert ".git" not in result
