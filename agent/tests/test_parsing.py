import pytest

from somnia_agent.event_mapping import hook_to_events
from somnia_agent.harness_payloads import Harness, parse_hook
from tests.conftest import FIXTURES, fixture_bytes

ALL = (
    [
        (Harness.CLAUDE_CODE, "claude_code", p.stem)
        for p in (FIXTURES / "claude_code").glob("*.json")
    ]
    + [(Harness.CODEX, "codex", p.stem) for p in (FIXTURES / "codex").glob("*.json")]
    + [(Harness.GROK, "grok", p.stem) for p in (FIXTURES / "grok").glob("*.json")]
)


@pytest.mark.parametrize(("harness", "folder", "name"), ALL)
def test_every_fixture_parses(harness: Harness, folder: str, name: str) -> None:
    hook = parse_hook(harness, fixture_bytes(folder, name))
    assert hook.session_id
    assert hook.event.lower().replace("_", "") == name.replace("_", "")
    for body in hook_to_events(hook):
        assert body.kind in {"message", "tool_call", "files_touched"}


def test_claude_post_tool_use_maps_to_tool_call_and_files() -> None:
    hook = parse_hook(Harness.CLAUDE_CODE, fixture_bytes("claude_code", "post_tool_use"))
    events = hook_to_events(hook)
    assert [e.kind for e in events] == ["tool_call", "files_touched"]
    assert events[0].payload["name"] == "Write"
    assert events[1].payload == {"paths": ["/work/repo/.env"], "action": "write"}


def test_codex_prompt_and_stop_map_to_messages() -> None:
    prompt = hook_to_events(parse_hook(Harness.CODEX, fixture_bytes("codex", "user_prompt_submit")))
    stop = hook_to_events(parse_hook(Harness.CODEX, fixture_bytes("codex", "stop")))
    assert prompt[0].payload == {"role": "user", "content": "Add retries to the uploader"}
    assert stop[0].payload["role"] == "assistant"


def test_grok_camel_case_and_failure_flag() -> None:
    ok = parse_hook(Harness.GROK, fixture_bytes("grok", "post_tool_use"))
    failed = parse_hook(Harness.GROK, fixture_bytes("grok", "post_tool_use_failure"))
    assert ok.session_id == "gk-sess-1"
    assert ok.tool_name == "edit_file"
    assert ok.cwd == "/work/repo"  # workspaceRoot preferred over a subdirectory cwd
    assert hook_to_events(failed)[0].payload["is_error"] is True
    start = parse_hook(Harness.GROK, fixture_bytes("grok", "session_start"))
    assert start.cwd == "/work/repo"


def test_session_lifecycle_events_carry_no_payload_events() -> None:
    for harness, folder in [(Harness.CLAUDE_CODE, "claude_code"), (Harness.CODEX, "codex")]:
        hook = parse_hook(harness, fixture_bytes(folder, "pre_compact"))
        assert hook_to_events(hook) == []
