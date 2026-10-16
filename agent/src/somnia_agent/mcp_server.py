"""Optional stdio MCP server: search_memory, status, continue_session.

Results come back as tool results (a user-turn suffix), wrapped as untrusted data.
"""

from pathlib import Path

from mcp.server.mcpserver import MCPServer

from somnia_agent.api_client import SomniaClient, make_http
from somnia_agent.config import load_config
from somnia_agent.context_format import UNTRUSTED_NOTE, render_context
from somnia_agent.git_info import detect
from somnia_agent.spool import acked_seq, read_events, read_meta, sessions_root

HTTP_TIMEOUT = 10.0
NOT_CONFIGURED = "somnia is not configured on this device: run `somnia-agent login`."


def _client_context(query: str | None, token_budget: int, k: int, *, with_checkpoint: bool) -> str:
    config = load_config()
    if config is None:
        return NOT_CONFIGURED
    git = detect(Path.cwd())
    with make_http(config, HTTP_TIMEOUT) as http:
        context = SomniaClient(http).context(git.repo, git.branch, token_budget, k, query)
    if not with_checkpoint:
        context = context.model_copy(update={"checkpoint": None})
    rendered = render_context(context)
    return rendered or f"No somnia memory yet for {git.repo}@{git.branch}."


def search_memory(query: str, k: int = 8, token_budget: int = 1500) -> str:
    """Search somnia memory for this repo and branch (vector search + recency ranking)."""
    return _client_context(query, token_budget, k, with_checkpoint=False)


def continue_session(token_budget: int = 2000) -> str:
    """Latest checkpoint (goal, state, next steps, files) plus top memories for this branch."""
    return _client_context(None, token_budget, 10, with_checkpoint=True)


def status() -> str:
    """Upload state of local sessions for this working directory, and server-side status."""
    config = load_config()
    if config is None:
        return NOT_CONFIGURED
    cwd = str(Path.cwd())
    root = sessions_root()
    lines: list[str] = [f"api: {config.api_url}"]
    dirs = sorted(root.iterdir(), key=lambda p: p.stat().st_mtime) if root.exists() else []
    for directory in dirs[-5:]:
        meta = read_meta(directory)
        if meta is None or meta.cwd != cwd:
            continue
        events = read_events(directory)
        pending = len([e for e in events if e.seq > acked_seq(directory)])
        line = f"{meta.harness} session {meta.harness_session_id}: {pending} event(s) pending"
        if meta.somnia_session_id is not None:
            with make_http(config, HTTP_TIMEOUT) as http:
                remote = SomniaClient(http).session_status(meta.somnia_session_id)
            line += (
                f"; somnia {remote.session.id} {remote.session.status},"
                f" {remote.unprocessed_events} not yet dreamt"
            )
        lines.append(line)
    if len(lines) == 1:
        lines.append("no local sessions recorded for this directory")
    return "\n".join(lines)


def build_server() -> MCPServer:
    server = MCPServer("somnia", instructions=UNTRUSTED_NOTE)
    server.tool()(search_memory)
    server.tool()(continue_session)
    server.tool()(status)
    return server


def run_mcp() -> int:
    build_server().run("stdio")
    return 0
