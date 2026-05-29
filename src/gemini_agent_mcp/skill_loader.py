"""Load skill profiles from markdown files with YAML frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"
_USER_SKILLS_DIR = Path.home() / ".gemini-agent-mcp" / "skills"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)
_LIST_ITEM_RE = re.compile(r"^\s*-\s*(.+)$", re.MULTILINE)


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
        raise ValueError(f"No frontmatter in {path}")

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    fields = {}
    for m in _FIELD_RE.finditer(frontmatter_text):
        key = m.group(1)
        val = m.group(2).strip()
        fields[key] = val

    name = fields.get("name") or path.stem
    tools_raw = fields.get("tools")
    tools = None
    if tools_raw:
        if tools_raw.startswith("[") or tools_raw.startswith("-"):
            tools = [item.strip() for item in _LIST_ITEM_RE.findall(tools_raw)]
        else:
            tools = [t.strip() for t in tools_raw.split(",") if t.strip()]

    return {
        "name": name,
        "description": fields.get("description", ""),
        "permission_mode": fields.get("permission_mode", "read_only"),
        "model": fields.get("model"),
        "tools": tools,
        "system_prompt": body,
    }
