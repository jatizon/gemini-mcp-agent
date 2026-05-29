"""Permission modes for controlling tool access per skill/invocation."""

from __future__ import annotations

from .tools import EDIT_TOOLS, EXEC_TOOLS, READ_TOOLS, TODO_TOOLS

PERMISSION_PRESETS = {
    "read_only": READ_TOOLS | TODO_TOOLS,
    "edit": READ_TOOLS | EDIT_TOOLS | TODO_TOOLS,
    "full": READ_TOOLS | EDIT_TOOLS | EXEC_TOOLS | TODO_TOOLS,
}


def get_allowed_tools(mode: str = "read_only", custom_tools: list[str] | None = None) -> set[str]:
    """Return the set of allowed tool names for a permission mode."""
    if custom_tools is not None:
        return set(custom_tools)
    return PERMISSION_PRESETS.get(mode, PERMISSION_PRESETS["read_only"]).copy()
