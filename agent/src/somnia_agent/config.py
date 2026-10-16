"""Per-device credentials. Only `smn_` device tokens are accepted, never a service key."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from somnia_agent.paths import config_path

DEVICE_TOKEN_PREFIX = "smn_"
DEFAULT_API_URL = "http://127.0.0.1:8000"


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
