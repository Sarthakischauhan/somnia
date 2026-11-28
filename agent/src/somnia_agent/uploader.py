"""Background upload of spooled events (and pending checkpoints / closes).

Only one flusher runs at a time (non-blocking flock); it keeps passing over the spool
until nothing is pending, so events appended while it runs are not stranded.
"""

import os
import subprocess
import sys
from pathlib import Path

import httpx

from somnia_agent.api import CheckpointIn, SomniaClient, make_http
from somnia_agent.config import detect, load_config, state_dir
from somnia_agent.spool import (
    SessionMeta,
    SpooledEvent,
    acked_seq,
    locked,
    read_events,
    read_meta,
    sessions_root,
    set_acked,
    write_atomic,
)

BATCH_SIZE = 200
MAX_PASSES = 5
CHECKPOINT_MARKER = "checkpoint.pending"
CLOSE_MARKER = "close.pending"
FLUSH_HTTP_TIMEOUT = 10.0
GOAL_CHARS = 500
STATE_CHARS = 2000
MAX_FILES = 50


def _message(event: SpooledEvent, role: str) -> str | None:
    if event.kind != "message" or event.payload.get("role") != role:
        return None
    content = event.payload.get("content")
    return content if isinstance(content, str) and content.strip() else None


def _build_checkpoint(
    events: list[SpooledEvent], reason: str, repo: str, git_ref: str | None
) -> CheckpointIn:
    """Draft a checkpoint from spooled events without making a model call."""
    user_messages = [m for e in events if (m := _message(e, "user"))]
    files: list[str] = []
    for event in events:
        paths = event.payload.get("paths") if event.kind == "files_touched" else None
        if isinstance(paths, list):
            files.extend(p for p in paths if isinstance(p, str) and p not in files)
    goal = user_messages[0] if user_messages else f"Continue work in {repo}"
    state = f"Session checkpointed ({reason})."
    for event in reversed(events):
        if assistant := _message(event, "assistant"):
            state = assistant
            break
        if event.kind == "tool_call":
            outcome = "failed" if event.payload.get("is_error") else "completed"
            state = f"Last tool {outcome}: {event.payload.get('name', 'unknown')}"
            if output := event.payload.get("output"):
                state += f"\n{output}"
            break
    next_steps = [f"Latest request: {user_messages[-1][:GOAL_CHARS]}"] if user_messages else []
    return CheckpointIn(
        goal=goal[:GOAL_CHARS],
        state=state[:STATE_CHARS],
        next_steps=next_steps,
        files_touched=files[-MAX_FILES:],
        git_ref=git_ref,
    )


def spawn_flush() -> None:
    """Fire-and-forget: the hook process never waits on the network."""
    if os.environ.get("SOMNIA_AGENT_NO_SPAWN") == "1":
        return
    subprocess.Popen(
        [sys.executable, "-m", "somnia_agent", "flush"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def _ensure_remote_session(client: SomniaClient, directory: Path, meta: SessionMeta) -> str:
    if meta.somnia_session_id is not None:
        return meta.somnia_session_id
    git = detect(Path(meta.cwd or "."))
    created = client.create_session(git.repo, git.branch, git.ref)
    updated = meta.model_copy(
        update={
            "somnia_session_id": created.id,
            "repo": git.repo,
            "branch": git.branch,
            "git_ref": git.ref,
        }
    )
    write_atomic(directory / "session.json", updated.model_dump_json())
    return created.id


def _pending(directory: Path) -> bool:
    events = read_events(directory)
    last = events[-1].seq if events else 0
    return (
        last > acked_seq(directory)
        or (directory / CHECKPOINT_MARKER).exists()
        or (directory / CLOSE_MARKER).exists()
    )


def flush_session(client: SomniaClient, directory: Path) -> None:
    meta = read_meta(directory)
    if meta is None or not _pending(directory):
        return
    session_id = _ensure_remote_session(client, directory, meta)
    marker = directory / CHECKPOINT_MARKER
    with locked(directory / "spool.lock"):
        events = read_events(directory)
        pending = marker.read_text(encoding="utf-8") if marker.exists() else None
    unsent = [e for e in events if e.seq > acked_seq(directory)]
    for start in range(0, len(unsent), BATCH_SIZE):
        batch = unsent[start : start + BATCH_SIZE]
        client.post_events(session_id, batch)
        set_acked(directory, batch[-1].seq)
    if pending is not None:
        refreshed = read_meta(directory) or meta
        reason = pending.rsplit("\n", 1)[-1].strip() or "hook"
        draft = _build_checkpoint(events, reason, refreshed.repo or "repo", refreshed.git_ref)
        client.post_checkpoint(session_id, draft)
        with locked(directory / "spool.lock"):
            if marker.read_text(encoding="utf-8") == pending:
                marker.unlink()
    close = directory / CLOSE_MARKER
    if close.exists():
        client.close_session(session_id)
        close.unlink()


def flush_all(client: SomniaClient) -> bool:
    """Returns False when another flusher already holds the lock."""
    with locked(state_dir() / "flush.lock", blocking=False) as acquired:
        if not acquired:
            return False
        root = sessions_root()
        for _ in range(MAX_PASSES):
            dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []
            pending = [d for d in dirs if _pending(d)]
            if not pending:
                break
            for directory in pending:
                flush_session(client, directory)
        return True


def run_flush() -> int:
    """Run the detached uploader; transient failures are retried on the next hook."""
    config = load_config()
    if config is None:
        return 0
    try:
        with make_http(config, FLUSH_HTTP_TIMEOUT) as http:
            flush_all(SomniaClient(http))
    except httpx.HTTPError as error:
        print(f"flush incomplete, will retry on the next hook: {error}")
        return 1
    return 0
