import pytest

from somnia_agent.redaction import redact_json, redact_text
from tests.conftest import fixture_bytes, run_cli

SECRETS = ["ghp_" + "a" * 36, "sk-" + "b" * 30, "AKIA" + "C" * 16, "plain-secret-value", "x" * 24]


def test_text_and_json_redaction() -> None:
    assert "ghp_" not in redact_text("token ghp_" + "a" * 36)
    assert redact_json({"api_key": "hunter22", "nested": [{"password": "p"}]}) == {
        "api_key": "[REDACTED]",
        "nested": [{"password": "[REDACTED]"}],
    }


@pytest.mark.parametrize(
    ("harness", "folder", "name"),
    [
        ("claude-code", "claude_code", "post_tool_use"),
        ("claude-code", "claude_code", "user_prompt_submit"),
        ("codex", "codex", "post_tool_use"),
        ("grok", "grok", "post_tool_use"),
    ],
)
def test_ingest_never_writes_secrets_to_spool(
    agent_env: dict[str, str], harness: str, folder: str, name: str
) -> None:
    from pathlib import Path

    done = run_cli(["ingest", "--harness", harness], fixture_bytes(folder, name))
    assert done.returncode == 0
    spooled = "".join(
        p.read_text() for p in Path(agent_env["SOMNIA_AGENT_STATE"]).rglob("events.jsonl")
    )
    assert "REDACTED" in spooled
    for secret in SECRETS:
        assert secret not in spooled
