# somnia for Codex

Codex hooks (`hooks.json`) plus the somnia MCP server in `config.toml`.

## Install

```bash
uv tool install 'somnia-agent[mcp] @ git+https://github.com/Sarthakischauhan/somnia#subdirectory=agent'
somnia-agent login --api-url https://<your-somnia-api>
plugins/codex/install.sh        # merges hooks into ~/.codex/hooks.json, adds [mcp_servers.somnia]
```

### Approve the hooks with `/hooks` (required)

Codex does not run non-managed hooks until you review and trust them, and trust is recorded
against each hook's hash, so new or changed hooks are skipped until trusted again. After
installing (and after any update to `hooks.json`):

1. Start `codex`. It warns at startup that hooks need review.
2. Run `/hooks`, review the six somnia hooks, and trust them.

`--dangerously-bypass-hook-trust` skips this for one invocation; don't use it as the normal setup.
For project scope instead of user scope, put `hooks.json` in `<repo>/.codex/` (loaded only when
the project `.codex/` layer is trusted).

## What runs when

| Event | Command | Notes |
| --- | --- | --- |
| `SessionStart` | `somnia-agent context` | Checkpoint + top memories as `hookSpecificOutput.additionalContext`. |
| `UserPromptSubmit` | `somnia-agent context --token-budget 600` | Records the prompt, then adds only memories relevant to it that were not already injected this session. |
| `PostToolUse`, `Stop` | `somnia-agent ingest` | `Stop` always prints `{}` because Codex treats plain-text Stop output as invalid. |
| `PreCompact` | `somnia-agent checkpoint` | Stdout is ignored by Codex for this event. |
| `SessionEnd` | `somnia-agent ingest --timeout 0.8` | Final checkpoint + close. Codex's SessionEnd default timeout is 1 s (max 3), so the hook timeout is 1 s. |

All requested events exist in Codex. **Caveat:** Codex adds `additionalContext` as extra
*developer* context; there is no user-turn channel for hook output. It is a suffix to the
conversation, not the system prompt, and it is wrapped as untrusted data.

## Docs

- Hooks (events, `hooks.json` locations, `/hooks` trust, output contract):
  https://developers.openai.com/codex/hooks
- MCP servers in `config.toml`: https://developers.openai.com/codex/mcp
