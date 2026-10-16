"""The shipped harness configs wire the documented events to valid somnia-agent commands."""

import json
import shlex
import tomllib
from pathlib import Path

import pytest

from somnia_agent.cli import build_parser

PLUGINS = Path(__file__).parents[2] / "plugins"


def _commands(path: Path) -> dict[str, list[list[str]]]:
    hooks = json.loads(path.read_text())["hooks"]
    out: dict[str, list[list[str]]] = {}
    for event, groups in hooks.items():
        for group in groups:
            for handler in group["hooks"]:
                assert handler["type"] == "command"
                argv = (
                    [handler["command"], *handler["args"]]
                    if "args" in handler
                    else (shlex.split(handler["command"]))
                )
                out.setdefault(event, []).append(argv)
    return out


@pytest.mark.parametrize(
    ("config", "events"),
    [
        (
            "claude-code/hooks/hooks.json",
            {"SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "PreCompact", "SessionEnd"},
        ),
        (
            "codex/hooks.json",
            {"SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact", "Stop", "SessionEnd"},
        ),
        (
            "grok/somnia-hooks.json",
            {
                "SessionStart",
                "UserPromptSubmit",
                "PostToolUse",
                "PostToolUseFailure",
                "Stop",
                "PreCompact",
                "SessionEnd",
            },
        ),
    ],
)
def test_hook_configs_parse_with_the_cli(config: str, events: set[str]) -> None:
    commands = _commands(PLUGINS / config)
    assert set(commands) == events
    parser = build_parser()
    for argvs in commands.values():
        for argv in argvs:
            assert argv[0] == "somnia-agent"
            parsed = parser.parse_args(argv[1:])
            assert parsed.command in {"ingest", "context", "checkpoint"}


def test_context_only_where_the_harness_injects_it() -> None:
    claude = _commands(PLUGINS / "claude-code/hooks/hooks.json")
    codex = _commands(PLUGINS / "codex/hooks.json")
    grok = _commands(PLUGINS / "grok/somnia-hooks.json")
    assert claude["SessionStart"][0][1] == "context"
    assert {codex["SessionStart"][0][1], codex["UserPromptSubmit"][0][1]} == {"context"}
    # Grok ignores stdout for passive events: no hook can inject context there.
    assert all(argv[1] != "context" for argvs in grok.values() for argv in argvs)


def test_mcp_configs_launch_the_server() -> None:
    claude = json.loads((PLUGINS / "claude-code/.mcp.json").read_text())["mcpServers"]["somnia"]
    assert [claude["command"], *claude["args"]] == ["somnia-agent", "mcp"]
    for name in ["codex/mcp.toml", "grok/mcp.toml"]:
        server = tomllib.loads((PLUGINS / name).read_text())["mcp_servers"]["somnia"]
        assert [server["command"], *server["args"]] == ["somnia-agent", "mcp"]


def test_claude_plugin_manifest_and_marketplace_names_match() -> None:
    manifest = json.loads((PLUGINS / "claude-code/.claude-plugin/plugin.json").read_text())
    market = json.loads((PLUGINS.parent / ".claude-plugin/marketplace.json").read_text())
    (entry,) = market["plugins"]
    assert entry["name"] == manifest["name"] == "somnia"
    assert entry["source"] == "./plugins/claude-code"
