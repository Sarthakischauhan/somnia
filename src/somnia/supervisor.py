"""`somnia-backend`: run one API and one worker with a shared lifetime."""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterable

_CHILDREN = (
    ("api", "somnia.api.serve", "SOMNIA_SERVICE_DATABASE_URL"),
    ("worker", "somnia.worker.main", "SOMNIA_API_DATABASE_URL"),
)
_POLL_INTERVAL_S = 0.1
_SHUTDOWN_TIMEOUT_S = 10.0


def _command(module: str) -> list[str]:
    # Call the same main functions as the standalone console scripts, in this venv.
    return [sys.executable, "-u", "-c", f"from {module} import main; main()"]


def _stop(children: Iterable[subprocess.Popen[bytes]], signum: int) -> None:
    for child in children:
        child.send_signal(signum)
    deadline = time.monotonic() + _SHUTDOWN_TIMEOUT_S
    for child in children:
        try:
            child.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            print(f"somnia-backend: killing unresponsive child (pid {child.pid})", file=sys.stderr)
            child.kill()
            child.wait()


def main() -> int:
    received_signal = 0

    def remember_signal(signum: int, _frame: object) -> None:
        nonlocal received_signal
        if not received_signal:
            received_signal = signum

    previous_handlers = {
        sig: signal.signal(sig, remember_signal) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    children: dict[str, subprocess.Popen[bytes]] = {}
    try:
        for name, module, excluded_key in _CHILDREN:
            if received_signal:
                break
            env = {key: val for key, val in os.environ.items() if key.upper() != excluded_key}
            try:
                # The supervisor receives terminal signals and forwards them once.
                children[name] = subprocess.Popen(_command(module), env=env, start_new_session=True)
            except OSError as exc:
                print(f"somnia-backend: could not start {name}: {exc}", file=sys.stderr)
                return 1

        while not received_signal:
            for name, child in children.items():
                code = child.poll()
                if code is not None:
                    print(
                        f"somnia-backend: {name} exited unexpectedly (status {code})",
                        file=sys.stderr,
                    )
                    # Both children are long-lived; even an early zero exit is a failure.
                    return 128 - code if code < 0 else code or 1
            time.sleep(_POLL_INTERVAL_S)
        return 128 + received_signal
    finally:
        try:
            _stop(children.values(), received_signal or signal.SIGTERM)
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
