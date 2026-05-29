"""Tests for skill file parsing and listing."""

from __future__ import annotations

from pathlib import Path

import pytest

from gemini_agent_mcp.skill_loader import _parse_skill_file, list_skills, load_skill


def _write_skill(path: Path, frontmatter: str, body: str = "System prompt body.") -> Path:
    """Helper: write a skill .md file with YAML frontmatter."""
    path.write_text(f"---\n{frontmatter}---\n{body}\n", encoding="utf-8")
    return path


# --- _parse_skill_file ---


def test_load_valid_skill(tmp_path: Path) -> None:
    skill_file = tmp_path / "review.md"
    _write_skill(
        skill_file,
        "name: review\ndescription: Code review skill\npermission_mode: read_only\nmodel: gemini-2.5-flash\ntools:\n  - read_file\n  - grep_search\n",
        body="You are a code reviewer.",
    )
    skill = _parse_skill_file(skill_file)
    assert skill["name"] == "review"
    assert skill["description"] == "Code review skill"
    assert skill["permission_mode"] == "read_only"
    assert skill["model"] == "gemini-2.5-flash"
    assert skill["tools"] == ["read_file", "grep_search"]
    assert skill["system_prompt"] == "You are a code reviewer."


def test_load_skill_with_yaml_list_tools(tmp_path: Path) -> None:
    skill_file = tmp_path / "reader.md"
    _write_skill(
        skill_file,
        "name: reader\ndescription: Read stuff\ntools:\n  - read_file\n  - grep_search\n",
    )
    skill = _parse_skill_file(skill_file)
    assert skill["tools"] == ["read_file", "grep_search"]


def test_load_skill_comma_separated_tools(tmp_path: Path) -> None:
    skill_file = tmp_path / "combo.md"
    _write_skill(
        skill_file,
        'name: combo\ndescription: Combo skill\ntools: "read_file, grep_search"\n',
    )
    skill = _parse_skill_file(skill_file)
    assert set(skill["tools"]) == {"read_file", "grep_search"}


def test_load_skill_missing_name_errors(tmp_path: Path) -> None:
    skill_file = tmp_path / "bad.md"
    _write_skill(skill_file, "description: No name here\n")
    with pytest.raises(ValueError, match="name"):
        _parse_skill_file(skill_file)


def test_load_skill_invalid_permission_errors(tmp_path: Path) -> None:
    skill_file = tmp_path / "badperm.md"
    _write_skill(
        skill_file,
        "name: badperm\ndescription: Bad perm\npermission_mode: invalid\n",
    )
    with pytest.raises(ValueError, match="permission_mode"):
        _parse_skill_file(skill_file)


def test_load_skill_unknown_tool_errors(tmp_path: Path) -> None:
    skill_file = tmp_path / "badtool.md"
    _write_skill(
        skill_file,
        "name: badtool\ndescription: Bad tool\ntools:\n  - nonexistent_tool\n",
    )
    with pytest.raises(ValueError, match="Unknown tools"):
        _parse_skill_file(skill_file)


# --- list_skills ---


def test_list_skills_from_dir(tmp_path: Path) -> None:
    _write_skill(
        tmp_path / "alpha.md",
        "name: alpha\ndescription: Alpha skill\npermission_mode: read_only\n",
    )
    _write_skill(
        tmp_path / "beta.md",
        "name: beta\ndescription: Beta skill\npermission_mode: edit\n",
    )
    skills = list_skills(skills_dir=str(tmp_path))
    names = {s["name"] for s in skills}
    assert "alpha" in names
    assert "beta" in names
    assert len([s for s in skills if s["name"] in ("alpha", "beta")]) == 2
