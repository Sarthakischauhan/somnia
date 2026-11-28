"""`somnia-agent` entry point."""

import argparse
import getpass
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx
from pydantic import ValidationError

from somnia_agent.api import SomniaClient, make_http
from somnia_agent.config import DEFAULT_API_URL, AgentConfig, detect, load_config, save_config
from somnia_agent.context_format import render_context
from somnia_agent.events import Harness
from somnia_agent.hooks import hosted_by_another_harness, run_context, run_ingest
from somnia_agent.uploader import run_flush

DEFAULT_HOOK_TIMEOUT = 1.5
DEFAULT_CONTEXT_TIMEOUT = 2.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="somnia-agent")
    commands = parser.add_subparsers(dest="command", required=True)
    harnesses = [h.value for h in Harness]

    ingest = commands.add_parser("ingest", help="spool a hook payload from stdin; never blocks")
    ingest.add_argument("--harness", choices=harnesses, required=True)
    ingest.add_argument("--timeout", type=float, default=DEFAULT_HOOK_TIMEOUT)

    checkpoint = commands.add_parser("checkpoint", help="spool a hook and queue a checkpoint")
    checkpoint.add_argument("--harness", choices=harnesses, required=True)
    checkpoint.add_argument("--timeout", type=float, default=DEFAULT_HOOK_TIMEOUT)
    checkpoint.add_argument("--reason", default=None)

    context = commands.add_parser("context", help="print session context for a hook")
    context.add_argument("--harness", choices=harnesses, required=True)
    context.add_argument("--timeout", type=float, default=DEFAULT_CONTEXT_TIMEOUT)
    context.add_argument("--token-budget", type=int, default=1500)
    context.add_argument("-k", type=int, default=8)

    login = commands.add_parser("login", help="store a per-device token (0600)")
    login.add_argument("--api-url", default=DEFAULT_API_URL)
    login.add_argument("--token", default=None, help="omit to be prompted")
    login.add_argument("--no-verify", action="store_true")

    resume = commands.add_parser("resume", help="read the saved handoff for this checkout")
    resume.add_argument("--cwd", type=Path, default=Path.cwd())

    commands.add_parser("flush", help="upload spooled events now")
    commands.add_parser("mcp", help="run the stdio MCP server (needs the [mcp] extra)")
    return parser


def _login(api_url: str, token: str | None, verify: bool) -> int:
    raw = token if token is not None else getpass.getpass("somnia device token (smn_...): ")
    try:
        config = AgentConfig(api_url=api_url, token=raw.strip())
    except ValidationError as error:
        print(f"login failed: {error.errors()[0]['msg']}")
        return 1
    if verify:
        try:
            with make_http(config, 5.0) as http:
                SomniaClient(http).verify()
        except httpx.HTTPError as error:
            print(f"login failed: could not verify token against {config.api_url}: {error}")
            return 1
    path = save_config(config)
    print(f"saved device token for {config.api_url} to {path} (mode 0600)")
    return 0


def _resume(cwd: Path) -> int:
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command: str = args.command
    if command in {"ingest", "checkpoint", "context"}:
        harness = Harness(args.harness)
        if hosted_by_another_harness(harness):
            return 0  # the host's own Somnia plugin ingests
        if command == "context":
            return run_context(harness, args.timeout, args.token_budget, args.k)
        return run_ingest(
            harness,
            args.timeout,
            force_checkpoint=command == "checkpoint",
            reason=args.reason if command == "checkpoint" else None,
        )
    if command == "login":
        return _login(args.api_url, args.token, verify=not args.no_verify)
    if command == "resume":
        return _resume(args.cwd)
    if command == "flush":
        return run_flush()
    from somnia_agent.mcp_server import run_mcp  # optional dependency

    return run_mcp()
