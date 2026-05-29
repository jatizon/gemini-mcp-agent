"""Cost tracking and reporting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import COST_LOG, PRICING_USD_PER_1M


def compute_cost(model: str, in_tokens: int, out_tokens: int) -> float | None:
    p = PRICING_USD_PER_1M.get(model)
    if not p:
        return None
    return (in_tokens / 1_000_000) * p["in"] + (out_tokens / 1_000_000) * p["out"]


def log_call(record: dict) -> None:
    record.setdefault("ts", datetime.now(timezone.utc).isoformat())
    try:
        COST_LOG.parent.mkdir(parents=True, exist_ok=True)
        with COST_LOG.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def get_status_report(today_only: bool = True) -> str:
    if not COST_LOG.exists():
        return "No cost log found. No Gemini agent calls recorded yet."

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_cost = 0.0
    total_calls = 0
    total_in = 0
    total_out = 0
    agent_calls = 0

    for line in COST_LOG.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        ts = entry.get("ts", "")
        if today_only and not ts.startswith(today):
            continue

        cost = entry.get("cost_usd") or 0
        total_cost += cost
        total_calls += 1
        total_in += entry.get("in_tokens", 0)
        total_out += entry.get("out_tokens", 0)
        if entry.get("mode") == "agent-loop":
            agent_calls += 1

    period = f"today ({today})" if today_only else "all time"
    return (
        f"Gemini usage ({period}):\n"
        f"  Calls: {total_calls} ({agent_calls} agent loops)\n"
        f"  Tokens: {total_in:,} in / {total_out:,} out\n"
        f"  Cost: ${total_cost:.4f}"
    )
