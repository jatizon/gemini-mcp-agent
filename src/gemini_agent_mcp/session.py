"""Session management — persist Gemini conversation history between calls."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import SESSION_DIR

_SESSION_MAX_AGE_S = 86400  # 24 hours


def load_session(session_id: str) -> list:
    """Load conversation history for a session. Returns empty list if not found."""
    path = _session_path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _deserialize_history(data.get("history", []))
    except (json.JSONDecodeError, KeyError, OSError):
        return []


def save_session(session_id: str, history: list, types_mod) -> None:
    """Save conversation history for a session."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = _session_path(session_id)
    data = {
        "session_id": session_id,
        "updated_at": time.time(),
        "turns": len(history),
        "history": _serialize_history(history),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cleanup_old_sessions()


def _session_path(session_id: str) -> Path:
    safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return SESSION_DIR / f"{safe_id}.json"


def _serialize_history(history: list) -> list[dict]:
    """Convert genai Content objects to JSON-safe dicts."""
    result = []
    for content in history:
        role = getattr(content, "role", "user")
        parts_data = []
        for part in getattr(content, "parts", []):
            if getattr(part, "text", None):
                parts_data.append({"type": "text", "text": part.text})
            elif getattr(part, "function_call", None):
                fc = part.function_call
                parts_data.append({
                    "type": "function_call",
                    "name": fc.name,
                    "args": dict(fc.args) if fc.args else {},
                })
            elif getattr(part, "function_response", None):
                fr = part.function_response
                parts_data.append({
                    "type": "function_response",
                    "name": fr.name,
                    "response": dict(fr.response) if fr.response else {},
                })
        result.append({"role": role, "parts": parts_data})
    return result


def _deserialize_history(data: list[dict]) -> list:
    """Convert JSON dicts back to genai Content objects."""
    from google.genai import types

    history = []
    for entry in data:
        role = entry.get("role", "user")
        parts = []
        for p in entry.get("parts", []):
            ptype = p.get("type")
            if ptype == "text":
                parts.append(types.Part.from_text(text=p["text"]))
            elif ptype == "function_call":
                parts.append(types.Part.from_function_call(
                    name=p["name"], args=p.get("args", {}),
                ))
            elif ptype == "function_response":
                parts.append(types.Part.from_function_response(
                    name=p["name"], response=p.get("response", {}),
                ))
        if parts:
            history.append(types.Content(role=role, parts=parts))
    return history


def _cleanup_old_sessions() -> None:
    """Remove session files older than 24 hours."""
    if not SESSION_DIR.exists():
        return
    now = time.time()
    for path in SESSION_DIR.glob("*.json"):
        try:
            if now - path.stat().st_mtime > _SESSION_MAX_AGE_S:
                path.unlink()
        except OSError:
            pass
