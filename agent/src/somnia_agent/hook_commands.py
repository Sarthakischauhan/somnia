"""ingest / checkpoint / context as hook handlers.

Every handler runs under a hard deadline and swallows all failures: a memory service
must never block or break the coding agent. Uploads happen in a detached flusher.
"""

import json
import sys
from pathlib import Path

from somnia_agent.api_client import SomniaClient, make_http
from somnia_agent.config import load_config
from somnia_agent.context_format import render_context
from somnia_agent.deadline import DeadlineExceededError, hard_deadline, read_stdin
from somnia_agent.git_info import detect
from somnia_agent.harness_payloads import Harness, HookEvent, parse_hook
from somnia_agent.hook_output import context_stdout, ingest_stdout
from somnia_agent.spool import write_atomic
from somnia_agent.spool_hook import spool_hook
from somnia_agent.uploader import CHECKPOINT_MARKER, CLOSE_MARKER, spawn_flush

_CHECKPOINT_EVENTS = frozenset({"PreCompact", "SessionEnd"})
_INJECTED_FILE = "injected.json"


def _emit(text: str) -> None:
    if text:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def run_ingest(harness: Harness, timeout_seconds: float) -> int:
    event = "unknown"
    try:
        with hard_deadline(timeout_seconds):
            hook = parse_hook(harness, read_stdin())
            event = hook.event
            directory = spool_hook(hook)
            if event in _CHECKPOINT_EVENTS:
                write_atomic(directory / CHECKPOINT_MARKER, event)
            if event == "SessionEnd":
                write_atomic(directory / CLOSE_MARKER, event)
            spawn_flush()
    except (DeadlineExceededError, Exception):
        pass
    _emit(ingest_stdout(harness, event))
    return 0


def run_checkpoint(harness: Harness, timeout_seconds: float, reason: str | None) -> int:
    event = "unknown"
    try:
        with hard_deadline(timeout_seconds):
            hook = parse_hook(harness, read_stdin())
            event = hook.event
            directory = spool_hook(hook)
            write_atomic(directory / CHECKPOINT_MARKER, reason or event)
            spawn_flush()
    except (DeadlineExceededError, Exception):
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
    with make_http(config, http_timeout) as http:
        context = SomniaClient(http).context(git.repo, git.branch, token_budget, k, hook.prompt)
    if hook.event == "UserPromptSubmit":
        # Per-prompt retrieval: no checkpoint, only memories not already injected.
        seen = _injected(directory)
        fresh = context.model_copy(update={"checkpoint": None})
        text = render_context(fresh, frozenset(seen))
    else:
        seen = set()
        text = render_context(context)
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
    except (DeadlineExceededError, Exception):
        text = None
    _emit(context_stdout(harness, event, text))
    return 0
