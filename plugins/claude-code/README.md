# somnia for Claude Code

A Claude Code plugin (`.claude-plugin/plugin.json`) bundling hooks, the somnia MCP server and a
`/continue` command. The repo root has a `.claude-plugin/marketplace.json` listing it.

## Install

```bash
uv tool install 'somnia-agent[mcp] @ git+https://github.com/Sarthakischauhan/somnia#subdirectory=agent'
somnia-agent login --api-url https://<your-somnia-api>
claude plugin marketplace add Sarthakischauhan/somnia
claude plugin install somnia@somnia
# or, from a checkout, for one session: claude --plugin-dir plugins/claude-code
```

Run `/hooks` to see the plugin's hooks and `/mcp` to see the `somnia` server.

## What runs when

| Event | Command | Notes |
| --- | --- | --- |
| `SessionStart` (startup, resume, clear, compact) | `somnia-agent context` | Prints `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": …}}`; Claude Code adds it to the conversation as context (not the system prompt). Capped below the 10,000-character hook limit. |
| `UserPromptSubmit`, `PostToolUse`, `Stop` | `somnia-agent ingest` | `async: true`, so Claude Code never waits; ingest itself is spool-only with a 1.5 s deadline. |
| `PreCompact` (manual, auto) | `somnia-agent checkpoint` | Queues a checkpoint before context is compacted. |
| `SessionEnd` | `somnia-agent ingest` | Queues a final checkpoint and closes the somnia session (fits the 1.5 s SessionEnd budget). |

Hooks use exec form (`command` + `args`), so no shell is involved.

`/somnia:continue` calls the MCP `continue_session` tool and summarises where the last session
stopped. `search_memory` and `status` are available to the model as MCP tools.

## Docs

- Hooks reference (events, input fields, `additionalContext`, `async`, `timeout`, exec form):
  https://code.claude.com/docs/en/hooks (formerly docs.anthropic.com/en/docs/claude-code/hooks)
- Plugin manifest and layout (`.claude-plugin/plugin.json`, `hooks/hooks.json`, `.mcp.json`,
  `commands/`, `${CLAUDE_PLUGIN_ROOT}`): https://code.claude.com/docs/en/plugins-reference
- Marketplaces: https://code.claude.com/docs/en/plugin-marketplaces
