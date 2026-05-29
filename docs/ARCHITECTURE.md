# Architecture

## Overview

gemini-agent-mcp is an MCP server that turns Gemini into an autonomous agent with a function-calling tool loop. It bridges two worlds:

1. **MCP protocol** (stdio JSON-RPC) — how Claude Code communicates with the server
2. **Gemini function calling** — how Gemini autonomously decides which tools to use

## Flow

```
Claude Code
    │
    ├─ tools/call: gemini_agent({task: "Analyze auth flow"})
    │
    ▼
MCP Server (server.py)
    │
    ├─ Validates input
    ├─ Loads API key
    │
    ▼
Agent Loop (agent_loop.py)
    │
    ├─ Creates Gemini client
    ├─ Loads session history (if session_id provided)
    ├─ Builds function declarations (tools.py)
    │
    ├─ LOOP (max_turns):
    │   │
    │   ├─ Send history to Gemini API
    │   │
    │   ├─ Gemini response:
    │   │   ├─ function_call? → Execute tool locally → Add result to history → Continue
    │   │   └─ text only?    → Done, return final answer
    │   │
    │   └─ Log progress to stderr
    │
    ├─ Save session
    ├─ Log cost
    │
    ▼
MCP Server
    │
    └─ Return final text + metadata to Claude Code
```

## Module Map

```
src/gemini_agent_mcp/
├── __main__.py     Entry point (python -m gemini_agent_mcp)
├── main.py         Bootstrap: builds tool list, wires handlers, starts server
├── server.py       MCP protocol handler (stdio JSON-RPC 2.0)
├── agent_loop.py   Gemini multi-turn function-calling loop
├── tools.py        Tool declarations (for Gemini) and local executors
├── safety.py       Path traversal prevention, bash blocklist, output truncation
├── session.py      Persist/restore conversation history between calls
├── cost.py         Cost computation and log reporting
└── config.py       Environment config, pricing tables, defaults
```

## Security Model

1. **Path sandboxing**: All file operations are resolved against `project_root`. Path traversal (`../../etc/passwd`) is blocked by `safety.safe_resolve()`.

2. **Bash blocklist**: Even when `allow_bash=true`, destructive commands are blocked (`rm`, `mv`, `sudo`, `curl`, etc.). The blocklist includes interpreter escapes (`python -c`, `node -e`).

3. **Output truncation**: Tool results are capped at 100K characters to prevent Gemini's context from exploding.

4. **Bash disabled by default**: The `bash_command` tool is not even declared to Gemini unless `allow_bash=true` is passed.

5. **No write tools**: Unlike the original `llm_call_gemini.py`, this server has no `write` tool. It is strictly read-only.

## Session Persistence

Sessions are stored as JSON files in `~/.gemini-agent-mcp/sessions/`. Each file contains the full conversation history (user prompts, Gemini responses, function calls, function results).

When a `session_id` is provided, the server loads the previous history and appends the new prompt. Gemini sees the full conversation and can reference prior findings.

Sessions are automatically cleaned up after 24 hours.

## Cost Model

Each Gemini API call within the agent loop accumulates tokens. The total is logged to `~/gemini_costs.log` as a single JSON record per `gemini_agent` invocation.

A typical 5-turn analysis with `gemini-3.5-flash` costs $0.001-0.005. This is roughly 100-500x cheaper than running the same analysis with Claude Opus.
