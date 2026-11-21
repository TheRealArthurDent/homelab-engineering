#!/usr/bin/env bash
# Setup script for the Claude Code cloud environment that holds infrastructure, smart-home, private-cloud and
# homelab-engineering. Paste it (or `bash <path>/setup/cloud-environment.sh`) into the environment's setup script.
#
# Network access the environment needs: github.com (repos, Superpowers), pypi.org and files.pythonhosted.org
# (pip), galaxy.ansible.com (collections; optional, see below). Nothing in 192.168.0.0/16: the cloud never talks
# to the Pis.
#
# Every step after the guard install is best effort: a blocked package index leaves a session without some
# tooling, never without the guard.
set -euo pipefail

warn() { echo "WARN: $*" >&2; }

# 1. Find this repo's checkout (the environment clones it with the others), or clone it.
HE_DIR="${HOMELAB_ENGINEERING_DIR:-}"
if [[ -z "$HE_DIR" ]]; then
  HE_DIR="$(find "$PWD" "$HOME" /home -maxdepth 4 -type f -path '*/homelab-engineering/setup/install-claude-config.sh' \
    2>/dev/null | head -n1 | xargs -r dirname | xargs -r dirname || true)"
fi
if [[ -z "$HE_DIR" ]]; then
  HE_DIR="$HOME/homelab-engineering"
  git clone --depth 1 https://github.com/TheRealArthurDent/homelab-engineering "$HE_DIR"
fi

# 2. Guard, skills, agents, user-level CLAUDE.md. Not best effort: without the guard, fail the setup.
bash "$HE_DIR/setup/install-claude-config.sh"

# 3. Tooling per repo, the same commands as in each repo's CLAUDE.md, so a session starts ready.
REPOS_DIR="${HOMELAB_REPOS_DIR:-$(dirname "$HE_DIR")}"
for repo in infrastructure smart-home private-cloud; do
  dir="$REPOS_DIR/$repo"
  [[ -f "$dir/requirements.txt" ]] || { warn "$repo not found in $REPOS_DIR, skipping its tooling"; continue; }
  (
    cd "$dir"
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt || warn "$repo: pip install failed"
    .venv/bin/pre-commit install >/dev/null 2>&1 || warn "$repo: pre-commit install failed"
    if [[ -f ansible/requirements.yaml ]]; then
      (cd ansible && ../.venv/bin/ansible-galaxy collection install -r requirements.yaml >/dev/null) \
        || warn "$repo: Galaxy unreachable; ansible-lint and the --limit guard tests will miss collections"
    fi
  )
done

# 4. Superpowers (brainstorming, plans, TDD, debugging). Optional; drop this block if you don't want it.
if command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add obra/superpowers-marketplace >/dev/null 2>&1 || warn "Superpowers marketplace not added"
  claude plugin install superpowers@superpowers-marketplace >/dev/null 2>&1 || warn "Superpowers not installed"
else
  warn "claude CLI not on PATH, Superpowers not installed"
fi

echo "homelab cloud environment ready (homelab-engineering at $HE_DIR)"
