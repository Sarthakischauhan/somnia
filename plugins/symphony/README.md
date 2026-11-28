# Somnia in Symphony

Install the agent from the Somnia checkout and log each device into the same Somnia user
account. The CLI must be on Symphony's PATH.

```bash
uv tool install --force /path/to/somnia/agent
somnia-agent login --api-url https://your-somnia-api
symphony plugins add /path/to/somnia/plugins/symphony
symphony plugins enable somnia
```

In Symphony, restart or run `/reload`, then check `/addons` for `somnia`. Open the same
git repo and branch on the receiving machine. Run `/somnia-resume` to inspect the handoff,
or ask Symphony to call `somnia_resume` and pick up the next unfinished step. Other agents
can run `somnia-agent resume`. Codex and Claude Code can also get the checkpoint through
their Somnia session-start hooks.

The addon records each top-level run's prompt, completed tool results and final reply.
It sends events to the CLI in order on a background worker, so Symphony doesn't wait for
Somnia. If capture falls 32 events behind, new events are skipped rather than blocking the
run. The CLI redacts and spools events locally, queues checkpoints after tool results and
the final reply, and uploads in the background. An unfinished tool has no result to hand off. If uploads are offline, run `somnia-agent flush` on the original device once it
reconnects. The Somnia dashboard's **Session handoffs** page shows the latest saved checkpoint
per repo and branch.

Use the original worktree or transfer uncommitted edits before resuming elsewhere. The
handoff carries context and a Git ref. It does not transfer files or restart a tool process.
