"""Background upload of spooled events (and pending checkpoints / closes).

Only one flusher runs at a time (non-blocking flock); it keeps passing over the spool
until nothing is pending, so events appended while it runs are not stranded.
"""

import os
import subprocess
import sys
from pathlib import Path

from somnia_agent.api_client import SomniaClient
from somnia_agent.checkpoint_builder import build_checkpoint
from somnia_agent.git_info import detect
from somnia_agent.paths import state_dir
from somnia_agent.spool import (
    SessionMeta,
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
    events = read_events(directory)
    unsent = [e for e in events if e.seq > acked_seq(directory)]
    for start in range(0, len(unsent), BATCH_SIZE):
        batch = unsent[start : start + BATCH_SIZE]
        client.post_events(session_id, batch)
        set_acked(directory, batch[-1].seq)
    marker = directory / CHECKPOINT_MARKER
    if marker.exists():
        refreshed = read_meta(directory) or meta
        reason = marker.read_text(encoding="utf-8").strip() or "hook"
        draft = build_checkpoint(events, reason, refreshed.repo or "repo", refreshed.git_ref)
        client.post_checkpoint(session_id, draft)
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
