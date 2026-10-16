"""Repo / branch / ref for a working directory, used to key sessions and context."""

import re
import subprocess
from pathlib import Path

from pydantic import BaseModel

GIT_TIMEOUT_SECONDS = 0.5
_REMOTE = re.compile(r"(?:[:/])([^/:]+/[^/]+?)(?:\.git)?/?$")


class GitInfo(BaseModel):
    repo: str
    branch: str
    ref: str | None


def _git(cwd: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = done.stdout.strip()
    return out if done.returncode == 0 and out else None


def repo_from_remote(url: str) -> str | None:
    match = _REMOTE.search(url.strip())
    return match.group(1) if match else None


def detect(cwd: Path) -> GitInfo:
    remote = _git(cwd, "remote", "get-url", "origin")
    top = _git(cwd, "rev-parse", "--show-toplevel")
    repo = (remote and repo_from_remote(remote)) or Path(top or cwd).name or "unknown"
    branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD") or "none"
    return GitInfo(repo=repo, branch=branch, ref=_git(cwd, "rev-parse", "HEAD"))
