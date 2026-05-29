"""Load skill profiles from markdown files with YAML frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .permissions import PERMISSION_PRESETS
from .tools import TOOL_SPECS

_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"
_USER_SKILLS_DIR = Path.home() / ".gemini-agent-mcp" / "skills"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def load_skill(name: str, skills_dir: str | None = None) -> dict:
    """Load a skill by name. Searches custom dir, user dir, then built-in."""
    search_dirs = []
    if skills_dir:
        search_dirs.append(Path(skills_dir))
    search_dirs.append(_USER_SKILLS_DIR)
    search_dirs.append(_BUILTIN_SKILLS_DIR)

    for d in search_dirs:
        path = d / f"{name}.md"
        if path.exists():
            return _parse_skill_file(path)

    available = list_skills(skills_dir)
    names = [s["name"] for s in available]
    raise ValueError(f"Skill '{name}' not found. Available: {', '.join(names) or 'none'}")


def list_skills(skills_dir: str | None = None) -> list[dict]:
    """List all available skills with name and description."""
    seen = set()
    result = []
    search_dirs = []
    if skills_dir:
        search_dirs.append(Path(skills_dir))
    search_dirs.append(_USER_SKILLS_DIR)
    search_dirs.append(_BUILTIN_SKILLS_DIR)

    for d in search_dirs:
        if not d.exists():
            continue
        for path in sorted(d.glob("*.md")):
            try:
                skill = _parse_skill_file(path)
            except (ValueError, OSError):
                continue
            if skill["name"] not in seen:
                seen.add(skill["name"])
                result.append({
                    "name": skill["name"],
                    "description": skill.get("description", ""),
                    "permission_mode": skill.get("permission_mode", "read_only"),
                    "tools": skill.get("tools"),
                    "model": skill.get("model"),
                })
    return result


def _parse_skill_file(path: Path) -> dict:
    """Parse a skill .md file with YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"No valid YAML frontmatter in {path}")

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    try:
        fields = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(fields, dict):
        raise ValueError(f"Frontmatter in {path} is not a mapping")

    name = fields.get("name")
    if not name:
        raise ValueError(f"Missing required field 'name' in {path}")
    description = fields.get("description")
    if not description:
        raise ValueError(f"Missing required field 'description' in {path}")

    permission_mode = fields.get("permission_mode", "read_only")
    if permission_mode not in PERMISSION_PRESETS:
        valid = ", ".join(PERMISSION_PRESETS.keys())
        raise ValueError(f"Invalid permission_mode '{permission_mode}' in {path}. Valid: {valid}")

    tools_raw = fields.get("tools")
    tools = None
    if tools_raw is not None:
        if isinstance(tools_raw, list):
            tools = [str(t).strip() for t in tools_raw]
        elif isinstance(tools_raw, str):
            tools = [t.strip() for t in tools_raw.split(",") if t.strip()]
        else:
            raise ValueError(f"'tools' in {path} must be a list or comma-separated string")
        unknown = set(tools) - set(TOOL_SPECS.keys())
        if unknown:
            raise ValueError(f"Unknown tools in {path}: {', '.join(sorted(unknown))}")

    return {
        "name": name,
        "description": description,
        "permission_mode": permission_mode,
        "model": fields.get("model"),
        "tools": tools,
        "system_prompt": body,
    }
