"""Record one hook into the local spool (no network)."""

from pathlib import Path

from somnia_agent.event_mapping import hook_to_events
from somnia_agent.harness_payloads import HookEvent
from somnia_agent.spool import SessionMeta, append_events, ensure_meta, session_dir


def spool_hook(hook: HookEvent) -> Path:
    directory = session_dir(hook.harness.value, hook.session_id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    ensure_meta(
        directory,
        SessionMeta(harness=hook.harness.value, harness_session_id=hook.session_id, cwd=hook.cwd),
    )
    append_events(directory, hook_to_events(hook))
    return directory
