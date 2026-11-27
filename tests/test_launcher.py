import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
import uvicorn

from somnia.api import serve


@pytest.mark.parametrize(
    ("host", "port", "expected_host", "expected_port"),
    [(None, None, "127.0.0.1", 8000), ("0.0.0.0", "10000", "0.0.0.0", 10000)],
)
def test_api_bind(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    host: str | None,
    port: str | None,
    expected_host: str,
    expected_port: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOMNIA_API_DATABASE_URL", "postgresql://api@localhost/test")
    monkeypatch.setenv("SOMNIA_PROVIDER", "fake")
    for key, value in [("SOMNIA_HOST", host), ("PORT", port)]:
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    run = Mock()
    monkeypatch.setattr(uvicorn, "run", run)

    serve.main()

    assert run.call_args.kwargs == {"host": expected_host, "port": expected_port, "workers": 1}


@pytest.mark.parametrize("port", ["", "not-a-port", "0", "65536"])
def test_api_rejects_invalid_port(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    monkeypatch.setenv("PORT", port)
    with pytest.raises(SystemExit, match="PORT must be an integer between 1 and 65535"):
        serve.main()


CHILD = """
import json, os, signal, sys, time
from pathlib import Path
name = sys.argv[1]
def stop(sig, frame):
    if not Path(name + '.ignore').exists():
        Path(name + '.signal').write_text(str(sig))
        sys.exit(0)
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
keys = ['SOMNIA_API_DATABASE_URL', 'SOMNIA_SERVICE_DATABASE_URL', 'somnia_service_database_url']
Path(name + '.tmp').write_text(json.dumps({k: os.environ[k] for k in keys if k in os.environ}))
Path(name + '.tmp').rename(name + '.ready')
while not Path(name + '.exit').exists():
    time.sleep(0.01)
code = int(Path(name + '.exit').read_text())
if code < 0:
    os.kill(os.getpid(), -code)
sys.exit(code)
"""


@pytest.fixture
def backend(tmp_path: Path) -> Iterator[subprocess.Popen[bytes]]:
    launch = """
import sys
from somnia import supervisor
supervisor._SHUTDOWN_TIMEOUT_S = 0.5
supervisor._command = lambda module: [
    sys.executable, '-c', sys.argv[1], 'api' if module == 'somnia.api.serve' else 'worker'
]
raise SystemExit(supervisor.main())
"""
    env = {
        **os.environ,
        "SOMNIA_API_DATABASE_URL": "api-role",
        "SOMNIA_SERVICE_DATABASE_URL": "service-role",
        "somnia_service_database_url": "service-role-alias",
    }
    with (
        (tmp_path / "stderr").open("wb") as log,
        subprocess.Popen(
            [sys.executable, "-c", launch, CHILD], cwd=tmp_path, env=env, stderr=log
        ) as process,
    ):
        try:
            deadline = time.monotonic() + 5
            while not all((tmp_path / f"{name}.ready").exists() for name in ("api", "worker")):
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail((tmp_path / "stderr").read_text() or "children did not start")
                time.sleep(0.01)
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_backend_forwards_signal_and_separates_credentials(
    backend: subprocess.Popen[bytes], tmp_path: Path, sig: signal.Signals
) -> None:
    assert json.loads((tmp_path / "api.ready").read_text()) == {
        "SOMNIA_API_DATABASE_URL": "api-role"
    }
    worker_env = json.loads((tmp_path / "worker.ready").read_text())
    assert worker_env["SOMNIA_SERVICE_DATABASE_URL"] == "service-role"
    assert "SOMNIA_API_DATABASE_URL" not in worker_env

    backend.send_signal(sig)

    assert backend.wait(timeout=5) == 128 + sig
    for name in ("api", "worker"):
        assert int((tmp_path / f"{name}.signal").read_text()) == sig


@pytest.mark.parametrize(
    ("exited", "sibling", "code", "expected"),
    [("worker", "api", 17, 17), ("api", "worker", 0, 1), ("api", "worker", -9, 137)],
)
def test_backend_propagates_child_exit_and_stops_sibling(
    backend: subprocess.Popen[bytes],
    tmp_path: Path,
    exited: str,
    sibling: str,
    code: int,
    expected: int,
) -> None:
    (tmp_path / "exit.tmp").write_text(str(code))
    (tmp_path / "exit.tmp").rename(tmp_path / f"{exited}.exit")

    assert backend.wait(timeout=5) == expected
    assert int((tmp_path / f"{sibling}.signal").read_text()) == signal.SIGTERM
    assert f"{exited} exited unexpectedly (status {code})" in (tmp_path / "stderr").read_text()


def test_backend_kills_unresponsive_child(backend: subprocess.Popen[bytes], tmp_path: Path) -> None:
    (tmp_path / "worker.ignore").touch()
    backend.terminate()

    assert backend.wait(timeout=5) == 128 + signal.SIGTERM
    assert "killing unresponsive child" in (tmp_path / "stderr").read_text()
    assert int((tmp_path / "api.signal").read_text()) == signal.SIGTERM
