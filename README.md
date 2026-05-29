# gemini-agent-mcp

MCP server that runs **Gemini as an autonomous agent** with a function-calling tool loop.

Gemini is the brain (cheap, 1M token context). Tools are executed locally by the server. From Claude Code's perspective, it works like a subagent: send a task, get a final analysis back.

```
Claude Code ──MCP──> gemini-agent-mcp
                        │
                        ├─ Gemini: "I need to read src/app.py"
                        │    └─ Server executes read_file locally
                        ├─ Gemini: "Now grep for 'auth'"
                        │    └─ Server executes grep_search locally
                        ├─ Gemini: "I have enough info"
                        │    └─ Returns final analysis
                        │
Claude Code <──────── Final result + metadata
```

## Why

- **Cost**: Gemini Flash is ~50x cheaper than Claude Opus for bulk analysis
- **Context**: Gemini's 1M token window handles large codebases without chunking
- **Safety**: All tools are sandboxed with path traversal prevention and bash blocklists
- **Sessions**: Gemini remembers previous context across calls via session IDs

## Install

### One-liner (Claude Code)

```bash
claude mcp add gemini-agent -s user -- \
  env GEMINI_API_KEY=your-key-here \
  python3 -m gemini_agent_mcp
```

### From source

```bash
git clone https://github.com/your-user/gemini-agent-mcp.git
cd gemini-agent-mcp
pip install -e .

# Then add to Claude Code:
claude mcp add gemini-agent -s user -- \
  env GEMINI_API_KEY=your-key-here \
  python3 -m gemini_agent_mcp
```

### Get a Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a key (free tier: 15 RPM, 1500 req/day)
3. Set it as `GEMINI_API_KEY`

## Usage

Once installed, Claude Code can use the Gemini agent automatically. You can also ask explicitly:

```
Use the gemini_agent tool to analyze the authentication flow in this project
```

### Tools exposed to Claude Code

#### `gemini_agent`

Run Gemini as an autonomous agent that reads files, searches code, and returns analysis.

| Parameter      | Type     | Required | Default          | Description                      |
| -------------- | -------- | -------- | ---------------- | -------------------------------- |
| `task`         | string   | yes      | -                | The analysis task                |
| `project_root` | string   | no       | cwd              | Sandbox boundary (absolute path) |
| `files`        | string[] | no       | -                | Specific files to focus on       |
| `max_turns`    | integer  | no       | 15               | Max agent loop iterations        |
| `allow_bash`   | boolean  | no       | false            | Enable bash commands             |
| `session_id`   | string   | no       | auto             | Resume a previous session        |
| `model`        | string   | no       | gemini-3.5-flash | Gemini model to use              |

#### `gemini_status`

Show cost and usage stats.

| Parameter    | Type    | Required | Default | Description             |
| ------------ | ------- | -------- | ------- | ----------------------- |
| `today_only` | boolean | no       | true    | Only show today's usage |

### Internal tools (used by Gemini, not exposed to Claude)

These are the function-calling tools that Gemini uses autonomously during analysis:

| Tool           | What it does                     | Safety                                       |
| -------------- | -------------------------------- | -------------------------------------------- |
| `read_file`    | Read a file from the project     | Path traversal blocked, 100KB cap            |
| `grep_search`  | Recursive grep with line numbers | Sandboxed to project root, 30s timeout       |
| `glob_files`   | List files matching a pattern    | Sandboxed, 500 match cap                     |
| `bash_command` | Run a shell command              | **Disabled by default**. Blocklist enforced. |

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

```
┌──────────────────────────────────────────────────┐
│ Claude Code (main thread)                        │
│                                                  │
│  "Analyze the auth flow" ──────────────────┐     │
│                                            │     │
│  ┌─────────────────────────────────────┐   │     │
│  │ MCP Protocol (stdio JSON-RPC)       │◄──┘     │
│  └──────────────┬──────────────────────┘         │
│                 │                                 │
│  ┌──────────────▼──────────────────────┐         │
│  │ gemini-agent-mcp                    │         │
│  │                                     │         │
│  │  ┌─────────────────────────────┐    │         │
│  │  │ Gemini Agent Loop           │    │         │
│  │  │                             │    │         │
│  │  │  Turn 1: glob_files(**/*.py)│    │         │
│  │  │  Turn 2: read_file(auth.py) │    │         │
│  │  │  Turn 3: grep_search(token) │    │         │
│  │  │  Turn 4: Final analysis     │    │         │
│  │  └─────────────────────────────┘    │         │
│  │                                     │         │
│  │  Tools executed locally (sandboxed) │         │
│  │  Cost logged to ~/gemini_costs.log  │         │
│  └─────────────────────────────────────┘         │
│                                                  │
│  ◄── Final analysis + metadata ──────────────    │
└──────────────────────────────────────────────────┘
```

## Sessions

Pass `session_id` to continue a previous conversation:

```
First call:  gemini_agent(task="Map the API endpoints") → session_id: "abc123"
Second call: gemini_agent(task="Now find which ones lack auth", session_id="abc123")
```

Gemini remembers all prior tool calls and findings. Sessions expire after 24 hours.

## Cost

Gemini Flash pricing (as of May 2026):

| Model            | Input     | Output   | Typical agent run (5 turns) |
| ---------------- | --------- | -------- | --------------------------- |
| gemini-3.5-flash | $0.075/1M | $0.30/1M | ~$0.001-0.005               |
| gemini-3.5-pro   | $1.25/1M  | $10.0/1M | ~$0.02-0.10                 |

Check usage: the `gemini_status` tool reads `~/gemini_costs.log`.

## Configuration

Environment variables:

| Variable                   | Default                         | Description           |
| -------------------------- | ------------------------------- | --------------------- |
| `GEMINI_API_KEY`           | (required)                      | Google Gemini API key |
| `GEMINI_COST_LOG`          | `~/gemini_costs.log`            | Path to cost log file |
| `GEMINI_AGENT_SESSION_DIR` | `~/.gemini-agent-mcp/sessions/` | Session storage       |

The server also searches for `GEMINI_API_KEY` in `.env` files (cwd and ancestors).

## Optional: Claude Code agent wrapper

For the nice subagent UI in Claude Code's terminal, copy `examples/claude-agent.md` to `~/.claude/agents/gemini-researcher.md`. This creates a Claude subagent that calls the MCP tool internally.

## License

MIT
