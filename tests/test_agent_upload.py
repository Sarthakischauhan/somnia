"""The somnia-agent uploader against the real API + database (RLS path)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from somnia_agent import redaction as agent_redaction
from somnia_agent.api_client import SomniaClient
from somnia_agent.harness_payloads import Harness, parse_hook
from somnia_agent.spool import session_dir, set_acked
from somnia_agent.spool_hook import spool_hook
from somnia_agent.uploader import CHECKPOINT_MARKER, flush_all

from somnia.db.connection import Conn
from somnia.ingest import payload_redaction, redaction
from tests.conftest import Device

FIXTURES = Path(__file__).parents[1] / "agent" / "tests" / "fixtures" / "claude_code"


def test_agent_redactor_matches_server() -> None:
    server = [(name, pattern.pattern, repl) for name, pattern, repl in redaction._PATTERNS]
    agent = [(name, pattern.pattern, repl) for name, pattern, repl in agent_redaction.PATTERNS]
    assert agent == server
    assert agent_redaction.SECRET_KEY.pattern == payload_redaction._SECRET_KEY.pattern


@pytest.mark.db
def test_agent_flush_is_idempotent_against_real_api(
    client: TestClient,
    device: Device,
    service_conn: Conn,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOMNIA_AGENT_STATE", str(tmp_path))
    for name in ["user_prompt_submit", "post_tool_use", "stop", "pre_compact"]:
        raw = (FIXTURES / f"{name}.json").read_bytes()
        directory = spool_hook(parse_hook(Harness.CLAUDE_CODE, raw))
    (directory / CHECKPOINT_MARKER).write_text("PreCompact")
    client.headers.update(device.headers)
    agent = SomniaClient(client)

    assert flush_all(agent)
    set_acked(session_dir("claude-code", "cc-sess-1"), 0)  # lost ack: everything is resent
    assert flush_all(agent)

    with service_conn.cursor() as cur:
        cur.execute("select seq, kind, payload from public.events order by seq")
        rows = cur.fetchall()
        cur.execute("select goal, files_touched from public.checkpoints")
        checkpoints = cur.fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        (1, "message"),
        (2, "tool_call"),
        (3, "files_touched"),
        (4, "message"),
    ]
    assert "ghp_" not in json.dumps([r[2] for r in rows])
    assert checkpoints == [(checkpoints[0][0], ["/work/repo/.env"])]
    assert str(checkpoints[0][0]).startswith("Fix the login bug")
