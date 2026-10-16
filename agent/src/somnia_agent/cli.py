"""`somnia-agent` entry point."""

import argparse
from collections.abc import Sequence

from somnia_agent.config import DEFAULT_API_URL
from somnia_agent.flush_command import run_flush
from somnia_agent.harness_payloads import Harness, effective_harness
from somnia_agent.hook_commands import run_checkpoint, run_context, run_ingest
from somnia_agent.login_command import run_login

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

    commands.add_parser("flush", help="upload spooled events now")
    commands.add_parser("mcp", help="run the stdio MCP server (needs the [mcp] extra)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command: str = args.command
    if command == "ingest":
        return run_ingest(effective_harness(Harness(args.harness)), args.timeout)
    if command == "checkpoint":
        return run_checkpoint(effective_harness(Harness(args.harness)), args.timeout, args.reason)
    if command == "context":
        return run_context(
            effective_harness(Harness(args.harness)), args.timeout, args.token_budget, args.k
        )
    if command == "login":
        return run_login(args.api_url, args.token, verify=not args.no_verify)
    if command == "flush":
        return run_flush()
    from somnia_agent.mcp_server import run_mcp  # optional dependency

    return run_mcp()
