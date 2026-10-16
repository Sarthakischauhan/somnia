"""Append-only per-session JSONL spool with a locked, monotonic seq counter.

Each harness session gets `<state>/sessions/<key>/` holding:
  events.jsonl   one {"seq", "kind", "payload"} per line, seq assigned under flock
  seq            last assigned seq
  acked          highest seq the server has accepted
  session.json   harness session -> somnia session mapping (+ repo/branch)
  checkpoint.json  pending checkpoint draft, posted after events
A retried upload resends identical seqs, which the server ignores (unique (session_id, seq)).
"""

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, JsonValue

from somnia_agent.event_mapping import EventBody, EventKind
from somnia_agent.paths import state_dir


class SpooledEvent(BaseModel):
    seq: int
    kind: EventKind
    payload: dict[str, JsonValue]


class SessionMeta(BaseModel):
    harness: str
    harness_session_id: str
    cwd: str | None = None
    somnia_session_id: str | None = None
    repo: str | None = None
    branch: str | None = None
    git_ref: str | None = None


def sessions_root() -> Path:
    return state_dir() / "sessions"


def session_dir(harness: str, harness_session_id: str) -> Path:
    digest = hashlib.sha256(f"{harness}:{harness_session_id}".encode()).hexdigest()[:32]
    return sessions_root() / digest


@contextmanager
def locked(path: Path, *, blocking: bool = True) -> Iterator[bool]:
    """Exclusive flock on `path`. Yields False when non-blocking and already held."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def _read_int(path: Path) -> int:
    return int(path.read_text(encoding="utf-8") or "0") if path.exists() else 0


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


def ensure_meta(directory: Path, meta: SessionMeta) -> None:
    path = directory / "session.json"
    if not path.exists():
        write_atomic(path, meta.model_dump_json())


def read_meta(directory: Path) -> SessionMeta | None:
    path = directory / "session.json"
    if not path.exists():
        return None
    return SessionMeta.model_validate_json(path.read_text(encoding="utf-8"))


def append_events(directory: Path, bodies: list[EventBody]) -> list[SpooledEvent]:
    if not bodies:
        return []
    with locked(directory / "spool.lock"):
        seq = _read_int(directory / "seq")
        spooled: list[SpooledEvent] = []
        for body in bodies:
            seq += 1
            spooled.append(SpooledEvent(seq=seq, kind=body.kind, payload=body.payload))
        fd = os.open(directory / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.writelines(event.model_dump_json() + "\n" for event in spooled)
        write_atomic(directory / "seq", str(seq))
    return spooled


def read_events(directory: Path) -> list[SpooledEvent]:
    path = directory / "events.jsonl"
    if not path.exists():
        return []
    events: list[SpooledEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(SpooledEvent.model_validate(json.loads(line)))
    return events


def acked_seq(directory: Path) -> int:
    return _read_int(directory / "acked")


def set_acked(directory: Path, seq: int) -> None:
    write_atomic(directory / "acked", str(seq))
