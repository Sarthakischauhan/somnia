"""Agent device credentials, config and state paths, and Git working directory info."""

import json
import os
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

DEVICE_TOKEN_PREFIX = "smn_"
DEFAULT_API_URL = "http://127.0.0.1:8000"
GIT_TIMEOUT_SECONDS = 0.5
_REMOTE = re.compile(r"(?:[:/])([^/:]+/[^/]+?)(?:\.git)?/?$")


def config_path() -> Path:
    override = os.environ.get("SOMNIA_AGENT_CONFIG")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "somnia" / "agent.json"


def state_dir() -> Path:
    override = os.environ.get("SOMNIA_AGENT_STATE")
    if override:
        return Path(override)
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "somnia"


class AgentConfig(BaseModel):
    api_url: str = Field(min_length=1)
    token: str = Field(min_length=1)

    @field_validator("token")
    @classmethod
    def _device_token_only(cls, value: str) -> str:
        if not value.startswith(DEVICE_TOKEN_PREFIX):
            raise ValueError(
                "not a somnia device token (expected smn_...); service keys are never accepted"
            )
        return value

    @field_validator("api_url")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        return value.rstrip("/")


def save_config(config: AgentConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(config.model_dump_json(indent=2))
    os.chmod(target, 0o600)  # O_CREAT mode does not apply to an existing file
    return target


def load_config(path: Path | None = None) -> AgentConfig | None:
    """Environment (SOMNIA_API_URL + SOMNIA_TOKEN) wins over the config file."""
    env_token = os.environ.get("SOMNIA_TOKEN")
    if env_token:
        api_url = os.environ.get("SOMNIA_API_URL", DEFAULT_API_URL)
        return AgentConfig(api_url=api_url, token=env_token)
    target = path or config_path()
    if not target.exists():
        return None
    return AgentConfig.model_validate(json.loads(target.read_text(encoding="utf-8")))


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
