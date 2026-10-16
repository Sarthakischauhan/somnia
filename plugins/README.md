# Harness plugins

All three integrations call the same CLI, [`somnia-agent`](../agent/README.md). Install it and
log in once per device, then follow the harness guide.

| Harness | Silent ingest | Session-start context | Checkpoints | MCP | Guide |
| --- | --- | --- | --- | --- | --- |
| Claude Code | PostToolUse, UserPromptSubmit, Stop, SessionEnd hooks | SessionStart `additionalContext` | PreCompact, SessionEnd | `.mcp.json` + `/somnia:continue` | [claude-code](claude-code/README.md) |
| Codex | PostToolUse, Stop, SessionEnd hooks (+ prompts via UserPromptSubmit) | SessionStart + UserPromptSubmit `additionalContext` (lands as developer context) | PreCompact, SessionEnd | `[mcp_servers.somnia]` | [codex](codex/README.md) |
| Grok Build | SessionStart, UserPromptSubmit, PostToolUse(+Failure), Stop, SessionEnd hooks | **Not possible via hooks** (stdout ignored); MCP `continue_session` + AGENTS.md instruction | PreCompact, SessionEnd | `grok mcp add` | [grok](grok/README.md) |

Retrieved memory is always wrapped as untrusted data and placed in a context suffix
(hook `additionalContext` or an MCP tool result), never in the system prompt.
