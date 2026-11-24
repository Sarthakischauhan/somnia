"""Load branch-scoped memory for a CLI or agent without a harness hook."""

import sys
from pathlib import Path

import httpx

from somnia_agent.api_client import SomniaClient, make_http
from somnia_agent.config import load_config
from somnia_agent.context_format import render_context
from somnia_agent.git_info import detect


def run_resume(cwd: Path) -> int:
    config = load_config()
    if config is None:
        print("Run somnia-agent login on this device first.", file=sys.stderr)
        return 1
    git = detect(cwd)
    try:
        with make_http(config, timeout_seconds=5) as http:
            context = SomniaClient(http).context(
                git.repo, git.branch, 4000, 10, None, checkpoint_first=True
            )
    except httpx.HTTPError as exc:
        print(f"Could not reach Somnia ({type(exc).__name__}).", file=sys.stderr)
        return 1
    print(
        render_context(context, checkpoint_first=True)
        or f"No saved Somnia context for {git.repo}@{git.branch}."
    )
    return 0
