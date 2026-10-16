import os
import subprocess
import sys
import time

import pytest

from tests.conftest import fixture_bytes, run_cli
from tests.fake_api import FakeApi


def test_ingest_exits_zero_within_deadline_when_stdin_never_closes(
    agent_env: dict[str, str],
) -> None:
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, "-m", "somnia_agent", "ingest", "--harness", "codex", "--timeout", "1"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=dict(os.environ),
    )
    assert proc.stdin is not None
    proc.stdin.write(b'{"session_id": "s", ')  # partial payload, pipe left open
    proc.stdin.flush()
    assert proc.wait(timeout=5) == 0
    assert time.monotonic() - started < 3.0
    proc.stdin.close()


@pytest.mark.parametrize("payload", [b"", b"not json", b"[1,2,3]", b'{"no": "session"}'])
def test_ingest_exits_zero_on_garbage(agent_env: dict[str, str], payload: bytes) -> None:
    assert run_cli(["ingest", "--harness", "claude-code"], payload).returncode == 0


def test_ingest_does_not_touch_network(agent_env: dict[str, str]) -> None:
    os.environ["SOMNIA_TOKEN"] = "smn_unreachable_token_000000000"
    os.environ["SOMNIA_API_URL"] = "http://10.255.255.1:9"  # blackhole
    os.environ["SOMNIA_AGENT_NO_SPAWN"] = "0"  # real detached flusher
    try:
        started = time.monotonic()
        done = run_cli(["ingest", "--harness", "claude-code"], fixture_bytes("claude_code", "stop"))
        assert done.returncode == 0
        assert time.monotonic() - started < 2.0
    finally:
        del os.environ["SOMNIA_TOKEN"], os.environ["SOMNIA_API_URL"]


def test_context_gives_up_on_a_hanging_api(fake_api: FakeApi) -> None:
    fake_api.state.hang_seconds = 5.0
    started = time.monotonic()
    done = run_cli(
        ["context", "--harness", "claude-code", "--timeout", "1"],
        fixture_bytes("claude_code", "session_start"),
    )
    assert done.returncode == 0
    assert done.stdout == b""
    assert time.monotonic() - started < 3.0


def test_codex_stop_always_prints_valid_json(agent_env: dict[str, str]) -> None:
    done = run_cli(["ingest", "--harness", "codex"], fixture_bytes("codex", "stop"))
    assert done.stdout.strip() == b"{}"
