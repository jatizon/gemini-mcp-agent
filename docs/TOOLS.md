# Tool Reference

These are the tools available to Gemini during the agent loop. They are **not** exposed to Claude Code directly — only Gemini decides when and how to use them.

## read_file

Read a text file from the project.

| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `path` | string | yes | File path relative to project root |

**Safety**: Path traversal blocked via `safe_resolve()`. Binary files rejected. Output capped at 100KB.

**Example call from Gemini**:
```json
{"name": "read_file", "args": {"path": "src/auth/middleware.py"}}
```

## grep_search

Recursive grep with line numbers.

| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `pattern` | string | yes | Search pattern (regex) |
| `path` | string | no | Subpath to search (default: project root) |

**Safety**: Sandboxed to project root. Skips binary files. 30-second timeout. Output capped at 100KB.

**Example call from Gemini**:
```json
{"name": "grep_search", "args": {"pattern": "def authenticate", "path": "src/"}}
```

## glob_files

List files matching a glob pattern.

| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `pattern` | string | yes | Glob pattern (e.g. `**/*.py`) |

**Safety**: Sandboxed to project root. Directories excluded from results. Capped at 500 matches.

**Example call from Gemini**:
```json
{"name": "glob_files", "args": {"pattern": "**/*.py"}}
```

## bash_command

Execute a shell command in the project root.

| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `cmd` | string | yes | Shell command to execute |

**Safety**: Disabled by default — only available when `allow_bash=true` is passed to `gemini_agent`. Forbidden pattern blocklist enforced even when enabled. 30-second timeout. Output capped at 100KB.

**Forbidden patterns**: `rm`, `mv`, `sudo`, `curl`, `wget`, `ssh`, `chmod 777`, `dd`, `python -c`, `node -e`, and more. See `safety.py` for the full list.

**Example call from Gemini**:
```json
{"name": "bash_command", "args": {"cmd": "wc -l src/**/*.py"}}
```
