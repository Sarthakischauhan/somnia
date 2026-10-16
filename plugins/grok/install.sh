#!/usr/bin/env bash
# Install somnia for Grok Build: ingest hooks, MCP server, AGENTS.md retrieval instruction.
# Docs: https://docs.x.ai/build/features/hooks  https://docs.x.ai/build/features/mcp-servers
#       https://docs.x.ai/build/features/project-rules
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
grok_home="$HOME/.grok"
mkdir -p "$grok_home/hooks"

command -v somnia-agent >/dev/null || {
  echo "somnia-agent not on PATH. Install it first:" >&2
  echo "  uv tool install 'somnia-agent[mcp] @ git+https://github.com/Sarthakischauhan/somnia#subdirectory=agent'" >&2
  exit 1
}

cp "$here/somnia-hooks.json" "$grok_home/hooks/somnia.json"
echo "hooks installed to $grok_home/hooks/somnia.json"

if command -v grok >/dev/null && ! grok mcp list 2>/dev/null | grep -q '\bsomnia\b'; then
  grok mcp add somnia -- somnia-agent mcp
elif ! grep -q '^\[mcp_servers\.somnia\]' "$grok_home/config.toml" 2>/dev/null; then
  { echo; cat "$here/mcp.toml"; } >> "$grok_home/config.toml"
fi
echo "MCP server 'somnia' configured"

# Global rules file: Grok loads ~/.grok/AGENTS.md into every session.
rules="$grok_home/AGENTS.md"
if ! grep -q 'somnia:start' "$rules" 2>/dev/null; then
  { echo; cat "$here/AGENTS.md"; } >> "$rules"
fi
echo "retrieval instruction added to $rules"

cat <<'MSG'

Next:
  1. somnia-agent login --api-url https://<your-somnia-api>   (paste a per-device smn_ token)
  2. If the somnia Claude Code plugin is also installed, Grok runs its hooks too; they detect
     GROK_HOOK_EVENT and no-op, so only these Grok hooks ingest.
MSG
