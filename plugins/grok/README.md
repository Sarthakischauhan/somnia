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

Grok imports Claude Code plugins and their hooks automatically, so if the somnia Claude Code
plugin is also installed, its hooks run inside Grok too. To prevent double ingest,
`somnia-agent` checks `GROK_HOOK_EVENT`, which Grok sets in the environment of every hook process
([hooks docs](https://docs.x.ai/build/features/hooks), "The script contract"). When it is set and
the hook was invoked with `--harness claude-code`, the command exits 0 with no spool write and no
stdout. Only this Grok plugin (`--harness grok`) ingests.

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
