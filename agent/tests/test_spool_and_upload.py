import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from somnia_agent.api_client import SomniaClient
from somnia_agent.event_mapping import EventBody
from somnia_agent.harness_payloads import Harness, parse_hook
from somnia_agent.spool import append_events, read_events, session_dir, set_acked
from somnia_agent.spool_hook import spool_hook
from somnia_agent.uploader import CHECKPOINT_MARKER, CLOSE_MARKER, flush_all
from tests.conftest import DEVICE_TOKEN, fixture_bytes, run_cli
from tests.fake_api import FakeApi


def _client(api: FakeApi) -> httpx.Client:
    return httpx.Client(base_url=api.url, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})


def test_seq_is_contiguous_under_concurrent_appends(agent_env: dict[str, str]) -> None:
    directory = session_dir("codex", "s")
    directory.mkdir(parents=True)
    body = EventBody(kind="message", payload={"role": "user", "content": "hi"})
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: append_events(directory, [body, body]), range(25)))
    assert [e.seq for e in read_events(directory)] == list(range(1, 51))


def test_upload_is_idempotent_on_session_and_seq(fake_api: FakeApi) -> None:
    for name in ["user_prompt_submit", "post_tool_use", "stop"]:
        spool_hook(parse_hook(Harness.CODEX, fixture_bytes("codex", name)))
    with _client(fake_api) as http:
        client = SomniaClient(http)
        assert flush_all(client)
        assert flush_all(client)  # nothing pending: no re-post
        assert fake_api.state.posted_seqs == [1, 2, 3]
        set_acked(session_dir("codex", "cx-sess-1"), 0)  # simulate a lost ack
        assert flush_all(client)
    assert fake_api.state.posted_seqs == [1, 2, 3, 1, 2, 3]
    (stored,) = fake_api.state.events.values()
    assert sorted(stored) == [1, 2, 3]
    assert len(fake_api.state.sessions) == 1  # session mapping reused, not recreated


def test_precompact_and_session_end_queue_checkpoint_and_close(fake_api: FakeApi) -> None:
    for name in ["user_prompt_submit", "post_tool_use", "stop", "pre_compact", "session_end"]:
        done = run_cli(["ingest", "--harness", "codex"], fixture_bytes("codex", name))
        assert done.returncode == 0
    directory = session_dir("codex", "cx-sess-1")
    assert (directory / CHECKPOINT_MARKER).exists()
    assert (directory / CLOSE_MARKER).exists()
    with _client(fake_api) as http:
        flush_all(SomniaClient(http))
    (checkpoint,) = fake_api.state.checkpoints
    assert checkpoint["goal"] == "Add retries to the uploader"
    assert checkpoint["state"] == "Retries added with exponential backoff."
    assert len(fake_api.state.closed) == 1
    assert not (directory / CHECKPOINT_MARKER).exists()


def test_flush_command_uploads_via_config(fake_api: FakeApi) -> None:
    run_cli(["ingest", "--harness", "grok"], fixture_bytes("grok", "post_tool_use"))
    done = run_cli(["flush"], b"")
    assert done.returncode == 0, done.stdout
    (stored,) = fake_api.state.events.values()
    assert sorted(stored) == [1, 2]


def test_spool_files_are_private(agent_env: dict[str, str]) -> None:
    run_cli(["ingest", "--harness", "claude-code"], fixture_bytes("claude_code", "stop"))
    (events,) = Path(agent_env["SOMNIA_AGENT_STATE"]).rglob("events.jsonl")
    assert os.stat(events).st_mode & 0o777 == 0o600
    assert json.loads(events.read_text().splitlines()[0])["seq"] == 1
