import asyncio
import os
from pathlib import Path

from somnia_agent.config import load_config
from somnia_agent.mcp_server import build_server
from tests.conftest import DEVICE_TOKEN, run_cli
from tests.fake_api import FakeApi


def test_login_writes_0600_config(agent_env: dict[str, str]) -> None:
    with FakeApi() as api:
        done = run_cli(["login", "--api-url", api.url + "/", "--token", DEVICE_TOKEN], b"")
    assert done.returncode == 0, done.stdout
    path = Path(agent_env["SOMNIA_AGENT_CONFIG"])
    assert os.stat(path).st_mode & 0o777 == 0o600
    config = load_config()
    assert config is not None
    assert config.token == DEVICE_TOKEN
    assert not config.api_url.endswith("/")


def test_login_rejects_service_keys(agent_env: dict[str, str]) -> None:
    service_key = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJlLXZhbHVl"
    done = run_cli(["login", "--token", service_key, "--no-verify"], b"")
    assert done.returncode == 1
    assert b"service keys are never accepted" in done.stdout
    assert not Path(agent_env["SOMNIA_AGENT_CONFIG"]).exists()


def test_login_fails_on_unverifiable_token(agent_env: dict[str, str]) -> None:
    done = run_cli(["login", "--api-url", "http://127.0.0.1:9", "--token", DEVICE_TOKEN], b"")
    assert done.returncode == 1
    assert not Path(agent_env["SOMNIA_AGENT_CONFIG"]).exists()


def test_mcp_server_exposes_three_tools(fake_api: FakeApi) -> None:
    tools = asyncio.run(build_server().list_tools())
    assert sorted(t.name for t in tools) == ["continue_session", "search_memory", "status"]
