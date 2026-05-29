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
git clone https://github.com/jatizon/gemini-mcp-agent.git
cd gemini-mcp-agent
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

Once installed, Claude Code can use the Gemini agent automatically:

```
Use the gemini code-reviewer skill to review the auth module
```

### Skills

Skills are specialized agent profiles with tailored prompts and tool permissions:

```
gemini_agent(skill="code-reviewer", task="Review this PR for bugs")
gemini_agent(skill="test-writer", task="Add tests for the auth module")
gemini_agent(skill="refactorer", task="Simplify the database layer")
```

Built-in skills:

| Skill                 | Mode      | Focus                                     |
| --------------------- | --------- | ----------------------------------------- |
| `code-reviewer`       | read_only | Bugs, regressions, edge cases             |
| `bug-hunter`          | read_only | Logic errors, off-by-one, race conditions |
| `security-auditor`    | read_only | OWASP, auth, injection, secrets           |
| `test-writer`         | edit      | Write/improve tests, verify they pass     |
| `refactorer`          | edit      | Simplify, extract, reduce duplication     |
| `docs-writer`         | edit      | README, inline docs, API reference        |
| `architecture-mapper` | read_only | Components, data flow, dependencies       |
| `dependency-auditor`  | read_only | Outdated packages, vulnerabilities        |

Use `gemini_skills()` to list available skills. Add custom skills to `~/.gemini-agent-mcp/skills/`.

### Tools exposed to Claude Code

#### `gemini_agent`

| Parameter         | Type     | Required | Default          | Description                          |
| ----------------- | -------- | -------- | ---------------- | ------------------------------------ |
| `task`            | string   | yes      | -                | The task for Gemini                  |
| `skill`           | string   | no       | -                | Skill profile (e.g. 'code-reviewer') |
| `project_root`    | string   | no       | cwd              | Sandbox boundary                     |
| `files`           | string[] | no       | -                | Specific files to focus on           |
| `max_turns`       | integer  | no       | 15               | Max agent loop iterations            |
| `permission_mode` | string   | no       | read_only        | read_only, edit, or full             |
| `allow_bash`      | boolean  | no       | false            | Enable bash commands                 |
| `session_id`      | string   | no       | auto             | Resume a previous session            |
| `model`           | string   | no       | gemini-3.5-flash | Gemini model                         |

#### `gemini_status`

| Parameter    | Type    | Required | Default | Description             |
| ------------ | ------- | -------- | ------- | ----------------------- |
| `today_only` | boolean | no       | true    | Only show today's usage |

#### `gemini_skills`

Lists available skill profiles with descriptions and permission modes.

### Internal tools (used by Gemini, not exposed to Claude)

| Tool              | Mode | What it does                           |
| ----------------- | ---- | -------------------------------------- |
| `read_file`       | read | File content with line numbers         |
| `read_file_range` | read | Specific line range from a file        |
| `list_directory`  | read | Directory listing with sizes           |
| `grep_search`     | read | Recursive grep with context lines      |
| `glob_files`      | read | Pattern matching file list             |
| `edit_file`       | edit | Replace exact string in file           |
| `multi_edit_file` | edit | Batch edits atomically                 |
| `analyze_diff`    | read | Git diff against base ref              |
| `project_map`     | read | Auto-detect project type and structure |
| `run_tests`       | exec | Run test suite (auto-detected)         |
| `run_lint`        | exec | Run linter (auto-detected)             |
| `run_typecheck`   | exec | Run type checker (auto-detected)       |
| `bash_command`    | exec | Shell command (disabled by default)    |
| `todo_write`      | any  | Track progress within session          |
| `todo_read`       | any  | Read current task list                 |

### Permission modes

| Mode        | Tools available                | Use case                                    |
| ----------- | ------------------------------ | ------------------------------------------- |
| `read_only` | read + todo (default)          | Code review, architecture mapping, analysis |
| `edit`      | read + edit + todo             | Documentation writing, simple refactors     |
| `verify`    | read + edit + test/lint + todo | Test writing, refactoring with validation   |
| `full`      | all tools including bash       | Unconstrained analysis (use with care)      |

#### `gemini_task` — Fan-out/fan-in

Run multiple Gemini agents with different skills simultaneously:

```
gemini_task(
    tasks=[
        {"skill": "code-reviewer", "task": "Review the auth module"},
        {"skill": "security-auditor", "task": "Audit the auth module"},
        {"skill": "architecture-mapper", "task": "Map the auth dependencies"}
    ],
    project_root="/path/to/project",
    mode="parallel",
    synthesize=true
)
```

Returns a synthesized summary plus individual results from each agent.

### Dry-run patch mode

Edit tools support `dry_run: true` to preview changes without modifying files:

```
edit_file(path="src/app.py", old_string="foo", new_string="bar", dry_run=true)
→ Returns unified diff without touching the file
```

## Claude-like Subagents

This is not a native Claude Code subagent — it's an **MCP-powered Gemini subagent runtime** that simulates the pattern. The experience for the user is similar:

```
Claude Code (main)
  └── calls gemini_agent or gemini_task
        └── picks skill: code-reviewer
              └── Gemini runs in isolated session
                    ├── read_file, grep_search (read_only)
                    ├── edit_file, run_tests (if verify/edit)
                    └── returns structured summary to Claude
```

**Recommended workflow:**

1. `implementation-planner` — plan changes (read_only)
2. `refactorer` or `test-writer` — apply changes (verify mode)
3. `run_tests` validates automatically
4. `final-reviewer` — review the diff (read_only)
5. Claude main decides the final result

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
