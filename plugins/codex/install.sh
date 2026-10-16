#!/usr/bin/env bash
# Install somnia hooks + MCP server for Codex (user scope: ~/.codex).
# Docs: https://developers.openai.com/codex/hooks  https://developers.openai.com/codex/mcp
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
codex_home="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$codex_home"

command -v somnia-agent >/dev/null || {
  echo "somnia-agent not on PATH. Install it first:" >&2
  echo "  uv tool install 'somnia-agent[mcp] @ git+https://github.com/Sarthakischauhan/somnia#subdirectory=agent'" >&2
  exit 1
}

# Merge our handlers into hooks.json without dropping existing ones (idempotent).
python3 - "$here/hooks.json" "$codex_home/hooks.json" <<'PY'
import json, pathlib, sys
ours = json.loads(pathlib.Path(sys.argv[1]).read_text())["hooks"]
target = pathlib.Path(sys.argv[2])
current = json.loads(target.read_text()) if target.exists() else {}
hooks = current.setdefault("hooks", {})
for event, groups in ours.items():
    existing = hooks.setdefault(event, [])
    commands = {h.get("command") for g in existing for h in g.get("hooks", [])}
    existing.extend(g for g in groups if g["hooks"][0]["command"] not in commands)
target.write_text(json.dumps(current, indent=2) + "\n")
print(f"hooks merged into {target}")
PY

config="$codex_home/config.toml"
if grep -q '^\[mcp_servers\.somnia\]' "$config" 2>/dev/null; then
  echo "MCP server 'somnia' already in $config"
else
  { echo; cat "$here/mcp.toml"; } >> "$config"
  echo "MCP server 'somnia' added to $config"
fi

cat <<'MSG'

Next:
  1. somnia-agent login --api-url https://<your-somnia-api>   (paste a per-device smn_ token)
  2. Start codex and run /hooks to review and trust the somnia hooks.
     Codex does not run new or changed non-managed hooks until you trust them.
MSG
