"""Hard wall-clock limit for hook commands: on expiry the command gives up and exits 0."""

import os
import select
import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

MAX_STDIN_BYTES = 4 * 1024 * 1024


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
