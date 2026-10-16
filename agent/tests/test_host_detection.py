"""Claude Code plugin hooks run by Grok Build must no-op; only the Grok plugin ingests."""

from pathlib import Path

import pytest

from tests.conftest import fixture_bytes, run_cli

# Grok sets GROK_HOOK_EVENT for every hook process (docs.x.ai/build/features/hooks).
GROK_ENV = "GROK_HOOK_EVENT"


def _spooled(agent_env: dict[str, str]) -> list[Path]:
    return list(Path(agent_env["SOMNIA_AGENT_STATE"]).rglob("events.jsonl"))


@pytest.mark.parametrize("command", ["ingest", "checkpoint", "context"])
def test_claude_hook_under_grok_is_a_no_op(
    agent_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    monkeypatch.setenv(GROK_ENV, "PostToolUse")
    # Grok sends its own camelCase payload to the imported Claude plugin hook.
    done = run_cli([command, "--harness", "claude-code"], fixture_bytes("grok", "post_tool_use"))
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
    assert not Path(agent_env["SOMNIA_AGENT_STATE"]).exists()


def test_claude_hook_native_ingests(agent_env: dict[str, str]) -> None:
    done = run_cli(
        ["ingest", "--harness", "claude-code"], fixture_bytes("claude_code", "post_tool_use")
    )
    assert done.returncode == 0
    (events,) = _spooled(agent_env)
    assert len(events.read_text().splitlines()) == 2  # tool_call + files_touched


def test_grok_plugin_hook_under_grok_ingests(
    agent_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(GROK_ENV, "PostToolUse")
    done = run_cli(["ingest", "--harness", "grok"], fixture_bytes("grok", "post_tool_use"))
    assert done.returncode == 0
    (events,) = _spooled(agent_env)
    assert '"name":"edit_file"' in events.read_text()


def test_both_plugins_under_grok_ingest_once(
    agent_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(GROK_ENV, "PostToolUse")
    payload = fixture_bytes("grok", "post_tool_use")
    run_cli(["ingest", "--harness", "claude-code"], payload)
    run_cli(["ingest", "--harness", "grok"], payload)
    (events,) = _spooled(agent_env)
    assert [line.count('"seq":') for line in events.read_text().splitlines()] == [1, 1]
