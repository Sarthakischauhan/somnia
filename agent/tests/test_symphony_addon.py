import json
import sys
from pathlib import Path
from queue import Queue
from threading import Event

import pytest
from core_harness.extensions import AddonEvent, dispatch_event, dispose_addons, load_addons

from somnia_agent.spool import read_events, session_dir
from somnia_agent.uploader import CHECKPOINT_MARKER
from tests.conftest import run_cli

ADDONS = Path(__file__).resolve().parents[2] / "plugins" / "symphony" / "addons"


def test_symphony_addon_dispatches_ordered_ingest_off_the_run_loop(
    agent_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = load_addons([ADDONS])
    assert not snapshot.failed
    assert snapshot.tool_names == {"somnia_resume"}
    assert [command.name for command in snapshot.commands] == ["somnia-resume"]
    (addon,) = snapshot.loaded
    assert addon.dispose is not None
    worker_started, release_worker = Event(), Event()
    results: Queue[tuple[object, int]] = Queue()

    def run_ingest(body: dict[str, object]) -> None:
        worker_started.set()
        if release_worker.wait(timeout=5):
            result = run_cli(["ingest", "--harness", "symphony"], json.dumps(body).encode())
            results.put((body["hook_event_name"], result.returncode))

    monkeypatch.setattr(sys.modules[addon.dispose.__module__], "_ingest", run_ingest)

    def emit(event: AddonEvent, run_id: str = "run", **payload: object) -> None:
        assert not dispatch_event(snapshot, event.value, {"run_id": run_id, **payload})

    try:
        emit(AddonEvent.RUN_STARTED, prompt="Fix retries")
        assert worker_started.wait(timeout=2)
        emit(AddonEvent.RUN_STARTED, "child", parent_id="run", prompt="Ignore child")
        emit(AddonEvent.RUN_COMPLETED, "child", output_text="Ignored")
        emit(
            AddonEvent.TOOL_EXECUTION_STARTED,
            tool_name="edit",
            tool_call_id="edit-1",
            arguments={"path": "retries.py"},
        )
        emit(
            AddonEvent.TOOL_EXECUTION_COMPLETED,
            tool_name="edit",
            tool_call_id="edit-1",
            status="error",
            result="Could not edit",
        )
        emit(
            AddonEvent.TOOL_EXECUTION_COMPLETED,
            tool_name="somnia_resume",
            tool_call_id="resume",
            status="success",
            result="Do not capture handoff contents",
        )
        emit(AddonEvent.RUN_COMPLETED, output_text="I found the bug")
        emit(
            AddonEvent.TOOL_EXECUTION_COMPLETED,
            tool_name="late",
            tool_call_id="late-1",
            status="success",
            result="Ignored after run completion",
        )
        # All callbacks returned while the first ingest was still blocked.
        assert results.empty()
    finally:
        assert not dispose_addons(snapshot.loaded)
        release_worker.set()

    assert [results.get(timeout=5) for _ in range(3)] == [
        ("UserPromptSubmit", 0),
        ("PostToolUse", 0),
        ("Stop", 0),
    ]
    assert not any(subscription.active for subscription in addon.subscriptions)
    directory = session_dir("symphony", "run")
    prompt, tool, paths, reply = read_events(directory)
    assert prompt.payload == {"role": "user", "content": "Fix retries"}
    assert tool.payload == {
        "name": "edit",
        "input": {"path": "retries.py"},
        "output": "Could not edit",
        "is_error": True,
    }
    assert paths.payload["paths"] == ["retries.py"]
    assert reply.payload == {"role": "assistant", "content": "I found the bug"}
    assert (directory / CHECKPOINT_MARKER).read_text().splitlines()[1] == "Stop"
