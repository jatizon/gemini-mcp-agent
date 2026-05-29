"""Environment configuration and constants."""

from __future__ import annotations

import os
from pathlib import Path

SERVER_NAME = "gemini-agent-mcp"
SERVER_VERSION = "0.1.0"

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_MAX_TURNS = 15
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_OUTPUT_TOKENS = 65_536

COST_LOG = Path(os.environ.get("GEMINI_COST_LOG", str(Path.home() / "gemini_costs.log")))
SESSION_DIR = Path(os.environ.get(
    "GEMINI_AGENT_SESSION_DIR",
    str(Path.home() / ".gemini-agent-mcp" / "sessions"),
))

PRICING_USD_PER_1M = {
    "gemini-3.5-flash":      {"in": 0.075, "out": 0.30},
    "gemini-3.5-flash-lite": {"in": 0.05,  "out": 0.20},
    "gemini-3.5-pro":        {"in": 1.25,  "out": 10.0},
    "gemini-2.5-flash":      {"in": 0.075, "out": 0.30},
    "gemini-2.5-pro":        {"in": 1.25,  "out": 10.0},
}

TOOL_OUTPUT_MAX_CHARS = 100_000
BASH_TIMEOUT_S = 30
GLOB_MAX_MATCHES = 500


def load_api_key() -> str | None:
    """Load GEMINI_API_KEY from environment or .env files."""
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]

    candidates = []
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        candidates.append(d / ".env")
        candidates.append(d / "snowflake" / ".env")
    candidates.append(Path.home() / ".gemini_api_key")

    for p in candidates:
        if not p.exists() or not p.is_file():
            continue
        if p.name == ".gemini_api_key":
            key = p.read_text().strip()
            if key:
                return key
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None
