# somnia-agent

Harness-side CLI for somnia. One typed package (mypy strict, `httpx` + `pydantic`, optional `mcp`)
used by the Claude Code, Codex and Grok Build integrations under [`plugins/`](../plugins).

## Install

```bash
# on PATH for hooks (recommended: hooks then start in ~100 ms)
uv tool install 'somnia-agent[mcp] @ git+https://github.com/Sarthakischauhan/somnia#subdirectory=agent'
# or ad hoc, without installing
uvx --from 'somnia-agent[mcp] @ git+https://github.com/Sarthakischauhan/somnia#subdirectory=agent' somnia-agent --help
```

## Log in (per-device token)

```bash
somnia-agent login --api-url https://<your-somnia-api>      # prompts for the smn_ token
```

The token is verified against the API and stored at `~/.config/somnia/agent.json` with mode
`0600` (`SOMNIA_AGENT_CONFIG` overrides the path; `SOMNIA_TOKEN` + `SOMNIA_API_URL` override the
file). Only `smn_` per-device tokens are accepted: the Supabase service key is never used here, it
lives only in the worker. **Gap:** the service has no device-code flow yet, so the token is pasted
(mint one per device; it is stored hashed server-side).

## Commands

| Command | Used by | Behaviour |
| --- | --- | --- |
| `ingest --harness H` | PostToolUse, UserPromptSubmit, Stop, SessionEnd hooks | Reads hook JSON on stdin, redacts secrets, appends to the local spool with a per-session `seq` (flock), then spawns a detached uploader and exits. Hard deadline (default 1.5 s, `--timeout`), always exit 0. |
| `checkpoint --harness H` | PreCompact (and SessionEnd) | Same as ingest, plus queues a checkpoint built from the spool (goal = first prompt, state = last assistant message, files touched). |
| `context --harness H` | SessionStart, Codex UserPromptSubmit | Fetches `/v1/context` for the repo/branch within `--token-budget` (tiktoken-counted server-side) and prints the harness's `additionalContext` JSON. Prints nothing on any failure; deadline 2 s. |
| `flush` | the detached uploader | Uploads unsent events; safe to run any time. |
| `login` | you | See above. |
| `mcp` | MCP clients | stdio server with `search_memory`, `status`, `continue_session`. |

`H` is `claude-code`, `codex` or `grok`. When `GROK_HOOK_EVENT` is set (Grok Build running a hook,
including Claude Code plugin hooks it imports), the payload is parsed as Grok's camelCase format.

## Guarantees

- **Never blocks the harness.** No network in the hook process: ingest writes a local spool and
  exits; uploads happen in a detached `somnia-agent flush`. A `SIGALRM` deadline bounds stdin reads
  and everything else; failures exit 0. Codex `Stop` hooks always get `{}` (Codex rejects plain
  text there).
- **Idempotent.** Each event gets a monotonic `seq` per harness session under a file lock. A
  retried or duplicated upload resends identical `(session_id, seq)` pairs, which the API ignores.
- **Redacted before disk.** The same patterns as the server redactor (parity is tested) run on
  prompts, tool inputs and outputs before anything is written to the spool.
- **Untrusted context.** Retrieved memory is printed inside `<somnia-memory trust="untrusted">`
  … `</somnia-memory>` with a note not to follow instructions inside it; a closing tag inside
  memory content is neutralised. It is delivered as hook `additionalContext` / an MCP tool
  result, never the system prompt.

State lives in `~/.local/state/somnia/sessions/<hash>/` (`SOMNIA_AGENT_STATE` overrides).

## Develop

```bash
cd agent && uv sync && uv run ruff check . && uv run mypy && uv run pytest
```
