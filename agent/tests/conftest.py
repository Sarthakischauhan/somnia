import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.fake_api import FakeApi

FIXTURES = Path(__file__).parent / "fixtures"
DEVICE_TOKEN = "smn_test_device_token_0123456789"


def fixture_bytes(harness_dir: str, name: str) -> bytes:
    return (FIXTURES / harness_dir / f"{name}.json").read_bytes()


def fixture_json(harness_dir: str, name: str) -> dict[str, object]:
    loaded = json.loads(fixture_bytes(harness_dir, name))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def agent_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    env = {
        "SOMNIA_AGENT_STATE": str(tmp_path / "state"),
        "SOMNIA_AGENT_CONFIG": str(tmp_path / "config" / "agent.json"),
        "SOMNIA_AGENT_NO_SPAWN": "1",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SOMNIA_TOKEN", raising=False)
    monkeypatch.delenv("SOMNIA_API_URL", raising=False)
    return env


@pytest.fixture
def fake_api(agent_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeApi]:
    with FakeApi() as api:
        monkeypatch.setenv("SOMNIA_TOKEN", DEVICE_TOKEN)
        monkeypatch.setenv("SOMNIA_API_URL", api.url)
        yield api


def run_cli(
    args: list[str], stdin: bytes, timeout: float = 10.0
) -> subprocess.CompletedProcess[bytes]:
    """Run the real CLI in a subprocess with the test's environment."""
    return subprocess.run(
        [sys.executable, "-m", "somnia_agent", *args],
        input=stdin,
        capture_output=True,
        timeout=timeout,
        env=dict(os.environ),
        check=False,
    )
