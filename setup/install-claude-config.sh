#!/usr/bin/env bash
# Installs the shared Claude Code config from this repo into ~/.claude, for every session of this user:
#
#   claude/hooks/   -> ~/.claude/hooks/        guard.py and hosts.json (copied, not linked: an edit in this
#                                              checkout takes effect only after a reviewed merge and a reinstall)
#   claude/skills/  -> ~/.claude/skills/       one directory per skill
#   claude/agents/  -> ~/.claude/agents/
#   claude/CLAUDE.md -> ~/.claude/homelab/CLAUDE.md, imported from ~/.claude/CLAUDE.md (your own lines stay)
#   claude/settings.json is merged into ~/.claude/settings.json: hooks and deny rules are added, nothing removed
#
# Safe to run again; run it after pulling changes to this repo. Used by setup/cloud-environment.sh and in WSL.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../claude" && pwd)"
DEST="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

mkdir -p "$DEST/hooks" "$DEST/skills" "$DEST/agents" "$DEST/homelab"

install -m 0755 "$SRC/hooks/guard.py" "$DEST/hooks/guard.py"
install -m 0644 "$SRC/hooks/hosts.json" "$DEST/hooks/hosts.json"

for skill in "$SRC"/skills/*/; do
  name="$(basename "$skill")"
  rm -rf "${DEST:?}/skills/$name"
  cp -R "$skill" "$DEST/skills/$name"
done
cp "$SRC"/agents/*.md "$DEST/agents/"

install -m 0644 "$SRC/CLAUDE.md" "$DEST/homelab/CLAUDE.md"
IMPORT="@~/.claude/homelab/CLAUDE.md"
touch "$DEST/CLAUDE.md"
grep -qxF "$IMPORT" "$DEST/CLAUDE.md" || printf '\n%s\n' "$IMPORT" >>"$DEST/CLAUDE.md"

python3 - "$SRC/settings.json" "$DEST/settings.json" <<'EOF'
import json, shutil, sys
from pathlib import Path

src, dest = Path(sys.argv[1]), Path(sys.argv[2])
new = json.loads(src.read_text())
cur = json.loads(dest.read_text()) if dest.exists() and dest.read_text().strip() else {}
if dest.exists():
    shutil.copy(dest, dest.with_suffix(".json.bak"))

hooks = cur.setdefault("hooks", {})
for event, groups in new.get("hooks", {}).items():
    existing = hooks.setdefault(event, [])
    for group in groups:
        if group not in existing:
            existing.append(group)

deny = cur.setdefault("permissions", {}).setdefault("deny", [])
deny += [rule for rule in new["permissions"]["deny"] if rule not in deny]

cur.setdefault("$schema", new["$schema"])
dest.write_text(json.dumps(cur, indent=2) + "\n")
EOF

echo "Installed homelab Claude config into $DEST"
