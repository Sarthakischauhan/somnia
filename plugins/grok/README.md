# somnia for Grok Build

Grok Build (`grok`, xAI's terminal coding agent) has lifecycle hooks and MCP support. Hooks give
silent ingest. **Context cannot be injected by a hook:** Grok ignores stdout for every event except
`PreToolUse`. Retrieval therefore goes through the somnia MCP server, prompted by an AGENTS.md
instruction.

## Install

```bash
uv tool install 'somnia-agent[mcp] @ git+https://github.com/Sarthakischauhan/somnia#subdirectory=agent'
somnia-agent login --api-url https://<your-somnia-api>
plugins/grok/install.sh
```

The script:
- copies `somnia-hooks.json` to `~/.grok/hooks/somnia.json` (personal hooks need no trust step;
  project hooks in `.grok/hooks/` need `/hooks-trust` or `--trust`);
- runs `grok mcp add somnia -- somnia-agent mcp` (or appends `mcp.toml` to `~/.grok/config.toml`);
- appends the `AGENTS.md` block to `~/.grok/AGENTS.md`, which Grok loads every session.

Don't also install the Claude Code plugin for Grok. Grok imports Claude Code plugins and hooks
automatically, so every event would be ingested twice. If the Claude plugin is installed anyway,
`somnia-agent` detects `GROK_HOOK_EVENT` and parses Grok's payload correctly.

## What runs when

| Event | Command |
| --- | --- |
| `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `PostToolUseFailure`, `Stop`, `SessionEnd` | `somnia-agent ingest --harness grok` |
| `PreCompact` | `somnia-agent checkpoint --harness grok` |

Grok's stdin payload is camelCase (`hookEventName`, `sessionId`, `cwd`, `workspaceRoot`,
`toolName`, `toolInput`). The docs only list those fields, so prompt text, tool output and the
assistant's final message are captured only if Grok sends them (`prompt`, `toolOutput` /
`toolResponse`, `lastAssistantMessage`). Tool calls and touched files are always captured.
Hook timeout default is 5 s; ours finish in under 1.5 s.

## Docs

- Hooks: https://docs.x.ai/build/features/hooks
- MCP servers: https://docs.x.ai/build/features/mcp-servers
- AGENTS.md / project rules: https://docs.x.ai/build/features/project-rules
- Plugins and Claude Code compatibility: https://docs.x.ai/build/features/skills-plugins-marketplaces
- Source: https://github.com/xai-org/grok-build
