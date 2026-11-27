"""Hook ingestion, checkpointing, and context injection.

Every handler runs under a hard deadline and swallows all failures: a memory service
must never block or break the coding agent. Uploads happen in a detached flusher.
"""

import json
import os
import select
import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from uuid import uuid4

from somnia_agent.api import SomniaClient, make_http
from somnia_agent.config import detect, load_config
from somnia_agent.context_format import render_context
from somnia_agent.events import Harness, HookEvent, hook_to_events, parse_hook
from somnia_agent.spool import (
    SessionMeta,
    append_events,
    ensure_meta,
    locked,
    session_dir,
    write_atomic,
)
from somnia_agent.uploader import CHECKPOINT_MARKER, CLOSE_MARKER, spawn_flush

MAX_STDIN_BYTES = 4 * 1024 * 1024
GROK_HOST_ENV = "GROK_HOOK_EVENT"
_CONTEXT_EVENTS = frozenset({"SessionStart", "UserPromptSubmit"})
_CODEX_JSON_REQUIRED = frozenset({"Stop", "SubagentStop"})
_CHECKPOINT_EVENTS = frozenset(
    {"PostToolUse", "PostToolUseFailure", "Stop", "PreCompact", "SessionEnd"}
)
_INJECTED_FILE = "injected.json"


class DeadlineExceededError(Exception):
    pass


def _raise(_signum: int, _frame: FrameType | None) -> None:
    raise DeadlineExceededError


@contextmanager
def hard_deadline(seconds: float) -> Iterator[None]:
    previous = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def read_stdin() -> bytes:
    """Read the hook payload; a harness that never closes stdin is cut off by the deadline."""
    if sys.stdin.isatty():
        return b""
    chunks: list[bytes] = []
    size = 0
    fd = sys.stdin.fileno()
    while size < MAX_STDIN_BYTES:
        select.select([fd], [], [])
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def running_under_grok() -> bool:
    # Grok sets this for every hook it runs, including imported Claude Code hooks.
    return bool(os.environ.get(GROK_HOST_ENV))


def hosted_by_another_harness(invoked_as: Harness) -> bool:
    """True when a Claude Code plugin hook runs inside Grok Build: the Grok plugin owns ingest."""
    return invoked_as is Harness.CLAUDE_CODE and running_under_grok()


def ingest_stdout(harness: Harness, event: str) -> str:
    """Codex rejects plain text from Stop hooks, so it gets an empty JSON object."""
    return "{}" if harness is Harness.CODEX and event in _CODEX_JSON_REQUIRED else ""


def context_stdout(harness: Harness, event: str, text: str | None) -> str:
    if text is None:
        return ingest_stdout(harness, event)
    if harness is Harness.GROK or event not in _CONTEXT_EVENTS:
        # Grok ignores stdout for passive events; printing is only useful for manual runs.
        return text
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
        ensure_ascii=False,
    )


def spool_hook(hook: HookEvent) -> Path:
    """Record one hook into the local spool (no network)."""
    directory = session_dir(hook.harness.value, hook.session_id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    ensure_meta(
        directory,
        SessionMeta(harness=hook.harness.value, harness_session_id=hook.session_id, cwd=hook.cwd),
    )
    append_events(directory, hook_to_events(hook))
    return directory


def _emit(text: str) -> None:
    if text:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def _queue_checkpoint(directory: Path, reason: str) -> None:
    with locked(directory / "spool.lock"):
        write_atomic(directory / CHECKPOINT_MARKER, f"{uuid4()}\n{reason}")


def run_ingest(
    harness: Harness,
    timeout_seconds: float,
    *,
    force_checkpoint: bool = False,
    reason: str | None = None,
) -> int:
    event = "unknown"
    try:
        with hard_deadline(timeout_seconds):
            hook = parse_hook(harness, read_stdin())
            event = hook.event
            directory = spool_hook(hook)
            if force_checkpoint or event in _CHECKPOINT_EVENTS:
                _queue_checkpoint(directory, reason or event)
            if not force_checkpoint and event == "SessionEnd":
                write_atomic(directory / CLOSE_MARKER, event)
            spawn_flush()
    except Exception:
        pass
    _emit(ingest_stdout(harness, event))
    return 0


def _injected(directory: Path) -> set[str]:
    path = directory / _INJECTED_FILE
    if not path.exists():
        return set()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return {str(item) for item in loaded} if isinstance(loaded, list) else set()


def context_for(hook: HookEvent, token_budget: int, k: int, http_timeout: float) -> str | None:
    config = load_config()
    if config is None:
        return None
    directory = spool_hook(hook)  # records the user prompt on UserPromptSubmit
    if hook.prompt:
        spawn_flush()
    git = detect(Path(hook.cwd or "."))
    checkpoint_first = hook.event == "SessionStart"
    with make_http(config, http_timeout) as http:
        context = SomniaClient(http).context(
            git.repo,
            git.branch,
            token_budget,
            k,
            hook.prompt,
            checkpoint_first=checkpoint_first,
        )
    if hook.event == "UserPromptSubmit":
        # Per-prompt retrieval: profile and checkpoint came at SessionStart; only add
        # memories not already injected this session.
        seen = _injected(directory)
        fresh = context.model_copy(update={"checkpoint": None, "profile": None})
        text = render_context(fresh, frozenset(seen))
    else:
        seen = set()
        text = render_context(context, checkpoint_first=checkpoint_first)
    seen.update(m.id for m in context.memories)
    write_atomic(directory / _INJECTED_FILE, json.dumps(sorted(seen)))
    return text


def run_context(harness: Harness, timeout_seconds: float, token_budget: int, k: int) -> int:
    event = "unknown"
    text: str | None = None
    try:
        with hard_deadline(timeout_seconds):
            hook = parse_hook(harness, read_stdin())
            event = hook.event
            text = context_for(hook, token_budget, k, http_timeout=timeout_seconds * 0.75)
    except Exception:
        text = None
    _emit(context_stdout(harness, event, text))
    return 0
