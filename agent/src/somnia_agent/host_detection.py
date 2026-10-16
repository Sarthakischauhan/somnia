"""Detect when a plugin's hooks are being run by a different harness than the one they target.

Grok Build imports Claude Code plugins and their hooks automatically
(https://docs.x.ai/build/features/skills-plugins-marketplaces, "Claude Code compatibility"),
so the somnia Claude Code plugin would ingest every event a second time next to the Grok plugin.

Signal: Grok sets GROK_HOOK_EVENT in the environment of every hook process it runs
(https://docs.x.ai/build/features/hooks, "The script contract": "Every hook process also
receives GROK_HOOK_EVENT, GROK_HOOK_NAME, GROK_SESSION_ID, and GROK_WORKSPACE_ROOT in its
environment"). Claude Code does not set it.
"""

import os

from somnia_agent.harness_payloads import Harness

GROK_HOST_ENV = "GROK_HOOK_EVENT"


def running_under_grok() -> bool:
    return bool(os.environ.get(GROK_HOST_ENV))


def hosted_by_another_harness(invoked_as: Harness) -> bool:
    """True when a Claude Code plugin hook runs inside Grok Build: the Grok plugin owns ingest."""
    return invoked_as is Harness.CLAUDE_CODE and running_under_grok()
