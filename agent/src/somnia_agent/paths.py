"""Where the agent keeps its config (secret) and its spool (state)."""

import os
from pathlib import Path


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
